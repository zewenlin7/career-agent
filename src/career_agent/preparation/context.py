"""Exact context loading shared by orchestration, reuse and interview preparation."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from career_agent.application.resumes import profile_fact_ids
from career_agent.application.services import require
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import FitOutput, PrivateResult, ResearchData, WorkflowState
from career_agent.preparation.guardrails import validate_fit, validate_research
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.schemas import InputSnapshot, RenderReport, ResumeDocument
from career_agent.resume.store import ArtifactStore

if TYPE_CHECKING:
    from career_agent.preparation.workflows import PreparationWorkflow


class ContextLoader:
    def __init__(self, runner: "PreparationWorkflow") -> None:
        self.r = runner

    async def requirements(self, ids: list[UUID] | None = None) -> list[e.JobRequirement]:
        query = select(e.JobRequirement).where(e.JobRequirement.job_revision_id == self.r.job.id)
        if ids is not None:
            query = query.where(e.JobRequirement.id.in_(ids))
        rows = list(await self.r.session.scalars(query.order_by(e.JobRequirement.id)))
        if ids is not None and (len(ids) != len(set(ids)) or {x.id for x in rows} != set(ids)):
            raise ModelGatewayError("context_revision_mismatch")
        if any(not x.source_quote or x.source_quote not in self.r.job.jd_text for x in rows):
            raise ModelGatewayError("requirement_evidence_missing")
        return rows

    async def fit(self, id: UUID) -> FitOutput:
        row = await require(self.r.session, e.PreparationArtifact, id)
        if row.profile_id != self.r.profile.id or row.job_revision_id != self.r.job.id:
            raise ModelGatewayError("context_revision_mismatch")
        value = PrivateResult.model_validate(row.data)
        if value.kind != "fit" or not isinstance(value.output, FitOutput):
            raise ModelGatewayError("context_revision_mismatch")
        validate_fit(value.output, set(self.r.state.requirement_refs), self.r.facts)
        return value.output

    async def compatible_legacy_fit(self, prompt_hash: str) -> UUID | None:
        """Reuse older Fit only when its input/trace provenance can still be established."""
        r = self.r
        facts = list(
            await r.session.scalars(
                select(e.PersonalFact).where(e.PersonalFact.id.in_(profile_fact_ids(r.profile)))
            )
        )
        candidates = await r.session.scalars(
            select(e.PreparationArtifact)
            .where(
                e.PreparationArtifact.profile_id == r.profile.id,
                e.PreparationArtifact.job_revision_id == r.job.id,
                e.PreparationArtifact.data["kind"].astext == "fit",
            )
            .order_by(e.PreparationArtifact.created_at.desc())
        )
        for row in candidates:
            # Legacy runs did not capture a complete fact-input hash. Do not infer it if any
            # profile fact is unverified now, or was verified after this result was produced.
            if any(
                f.status.value != "verified"
                or f.verified_at is None
                or f.verified_at > row.created_at
                for f in facts
            ):
                continue
            package = await r.session.scalar(
                select(e.PreparationArtifact).where(
                    e.PreparationArtifact.run_id == row.run_id,
                    e.PreparationArtifact.data["kind"].astext == "package",
                    e.PreparationArtifact.data["output"]["mode"].astext == r.request.mode,
                )
            )
            if package is None:
                continue
            old = PrivateResult.model_validate(package.data).output
            if not isinstance(old, WorkflowState) or old.fit_analysis_id != row.id:
                continue
            if set(old.requirement_refs) != set(r.state.requirement_refs):
                continue
            call = await r.session.scalar(
                select(e.ModelCall.id)
                .join(e.AgentStep)
                .where(
                    e.AgentStep.run_id == row.run_id,
                    e.ModelCall.task_type == "fit_analysis",
                    e.ModelCall.versions["prompt_hash"].astext == prompt_hash,
                )
            )
            if call is None:
                continue
            try:
                await self.fit(row.id)
            except ModelGatewayError:
                continue
            return row.id
        return None

    async def research(self, id: UUID, *, allow_stale: bool = False) -> ResearchData:
        row = await require(self.r.session, e.CompanyResearch, id)
        data = ResearchData.model_validate(row.data)
        if row.company_id != self.r.company.id or data.mode != self.r.request.mode:
            raise ModelGatewayError("context_revision_mismatch")
        if row.expires_at <= e.utcnow():
            if not allow_stale:
                raise ModelGatewayError("research_expired")
            self.r.state.warnings.append("research_context_stale")
        validate_research(data.report, {v.id for v in data.evidence})
        return data

    async def resume(self, id: UUID, *, target_job: bool = False) -> e.ResumeVariantRevision:
        row = await require(self.r.session, e.ResumeVariantRevision, id)
        doc = ResumeDocument.model_validate(row.document)
        if (
            row.profile_id != self.r.profile.id
            or doc.profile_id != row.profile_id
            or doc.profile_revision != self.r.profile.revision
            or doc.job_revision_id != row.job_revision_id
            or (target_job and row.job_revision_id != self.r.job.id)
        ):
            raise ModelGatewayError("context_revision_mismatch")
        requirements = (
            set(
                await self.r.session.scalars(
                    select(e.JobRequirement.id).where(
                        e.JobRequirement.job_revision_id == row.job_revision_id
                    )
                )
            )
            if row.job_revision_id
            else set()
        )
        findings = validate_grounding(
            doc,
            InputSnapshot.model_validate(row.input_snapshot),
            profile_fact_ids(self.r.profile),
            {
                f.id: FactEvidence(f.id, f.revision, f.status, f.statement)
                for f in self.r.fact_rows.values()
            },
            requirements,
        )
        if findings:
            raise ModelGatewayError("grounding_failed")
        return row

    async def render(self, id: UUID, variant: e.ResumeVariantRevision) -> e.RenderArtifact:
        row = await require(self.r.session, e.RenderArtifact, id)
        report = RenderReport.model_validate(row.report)
        if (
            row.resume_variant_id != variant.resume_variant_id
            or row.resume_variant_revision != variant.revision
            or report.render_status != "accepted"
            or not row.artifact_ref
            or not row.file_hash
        ):
            raise ModelGatewayError("accepted_resume_required")
        # Metadata alone cannot establish availability of the file used by the package.
        ArtifactStore(self.r.settings.data_dir).read(row.artifact_ref, row.file_hash)
        return row

    async def interview(self) -> None:
        if not self.r.request.application_package_id:
            if self.r.request.resume_revision_id is None:
                raise ModelGatewayError("resume_selection_required")
            base_variant = await self.resume(self.r.request.resume_revision_id, target_job=False)
            if base_variant.job_revision_id:
                source_job = await require(
                    self.r.session, e.JobRevision, base_variant.job_revision_id
                )
                if source_job.job_id != self.r.job.job_id:
                    raise ModelGatewayError("context_revision_mismatch")
            self.r.variant = base_variant
            self.r.state.resume_variant_id = base_variant.resume_variant_id
            self.r.state.resume_variant_revision = base_variant.revision
            return
        row = await require(
            self.r.session, e.PreparationArtifact, self.r.request.application_package_id
        )
        data = PrivateResult.model_validate(row.data)
        if data.kind != "package" or not isinstance(data.output, WorkflowState):
            raise ModelGatewayError("invalid_application_package")
        st = data.output
        if (
            row.profile_id != self.r.profile.id
            or row.job_revision_id != self.r.job.id
            or st.profile_id != row.profile_id
            or st.job_revision_id != row.job_revision_id
            or st.workflow != "prepare_application"
            or st.mode != self.r.request.mode
        ):
            raise ModelGatewayError("context_revision_mismatch")
        self.r.requirements = await self.requirements(st.requirement_refs)
        self.r.state.requirement_refs = st.requirement_refs
        if st.fit_analysis_id:
            self.r.fit = await self.fit(st.fit_analysis_id)
            self.r.state.fit_analysis_id = st.fit_analysis_id
        if not st.resume_variant_id or not st.resume_variant_revision or not st.render_report_id:
            raise ModelGatewayError("accepted_resume_required")
        variant = await self.r.session.scalar(
            select(e.ResumeVariantRevision).where(
                e.ResumeVariantRevision.resume_variant_id == st.resume_variant_id,
                e.ResumeVariantRevision.revision == st.resume_variant_revision,
            )
        )
        if variant is None:
            raise ModelGatewayError("context_revision_mismatch")
        self.r.variant = await self.resume(variant.id, target_job=True)
        await self.render(st.render_report_id, self.r.variant)
        self.r.state.resume_variant_id = st.resume_variant_id
        self.r.state.resume_variant_revision = st.resume_variant_revision
        self.r.state.render_report_id = st.render_report_id
        if st.research_report_id:
            research_data = await self.research(st.research_report_id, allow_stale=True)
            self.r.research_output = research_data.report
            self.r.state.research_report_id = st.research_report_id
