"""Two fixed graphs. Model outputs are data; only deterministic code selects edges."""

import asyncio
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application import resumes
from career_agent.application.services import require
from career_agent.config import Settings
from career_agent.domain.rules import (
    CallStatus,
    DomainError,
    FactStatus,
    ObservationStatus,
    RunStatus,
)
from career_agent.domain.schemas import ProfileData
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, PrivacyClass
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.budget import BudgetLedger, input_bound
from career_agent.preparation.contracts import (
    FitOutput,
    GreetingOutput,
    InterviewOutput,
    LayoutBudget,
    PrivateResult,
    RequirementsOutput,
    ResearchData,
    ResearchOutput,
    TaskType,
    WorkflowRequest,
    WorkflowState,
)
from career_agent.preparation.guardrails import (
    chinese,
    minimize,
    validate_compression,
    validate_extraction,
    validate_fit,
    validate_greeting,
    validate_interview,
    validate_research,
)
from career_agent.preparation.prompts import OUTPUTS, PromptSpec
from career_agent.preparation.research import ResearchAdapter, SearchInput, SearchToolMetadata
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.schemas import RenderReport, ResumeDocument
from career_agent.runtime.contracts import Budget, OutputDiagnostic, Usage, VersionMetadata


class GraphState(TypedDict, total=False):
    state: dict[str, Any]
    package_id: str


class PreparationWorkflow:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        gateway: ModelGateway,
        research: ResearchAdapter,
        request: WorkflowRequest,
    ) -> None:
        self.session, self.settings, self.gateway, self.research, self.request = (
            session,
            settings,
            gateway,
            research,
            request,
        )
        self.state: WorkflowState
        self.run: e.AgentRun
        self.step: e.AgentStep
        self.facts: dict[UUID, dict[str, Any]] = {}
        self.fact_rows: dict[UUID, e.PersonalFact] = {}
        self.profile_refs: dict[str, Any] = {}
        self.requirements: list[e.JobRequirement] = []
        self.variant: e.ResumeVariantRevision | None = None
        self.fit: FitOutput | None = None
        self.research_output: ResearchOutput | None = None
        self.report: RenderReport | None = None
        self.protected_fields: list[str] = []

    async def call(self, task_type: TaskType, blocks: dict[str, Any]) -> BaseModel:
        spec = PromptSpec(task_type)
        transport_retries = repairs = 0
        attempt = 0
        previous: str | None = None
        while True:
            task = spec.task(blocks, schema_repair=repairs > 0)
            u, b = self.state.usage, self.state.limits
            context = ModelRequestContext(
                task_type=task_type.value,
                workflow=self.state.workflow,
                privacy_class=PrivacyClass.SYNTHETIC
                if self.request.mode == "fixture"
                else PrivacyClass.PRIVATE,
                output_schema=OUTPUTS[task_type],
                max_output_tokens=6000
                if task_type in {TaskType.TAILOR, TaskType.COMPRESS, TaskType.INTERVIEW}
                else 3000,
                prompt_version=spec.version,
                input_schema_version=task.input_schema_version,
                output_schema_version=task.output_schema_version,
                budget_remaining=Budget(
                    token_limit=max(
                        0,
                        b.max_input_tokens
                        + b.max_output_tokens
                        - u.input_tokens
                        - u.output_tokens
                        - u.reserved_input_tokens
                        - u.reserved_output_tokens,
                    ),
                    cost_limit=max(0, b.max_estimated_cost - u.budget_consumed_usd),
                ),
            )
            candidate = self.gateway.policy.select(context, self.gateway.registry)
            ledger = BudgetLedger(b, u)
            reservation = ledger.reserve_model(
                candidate, input_bound(context, task), context.max_output_tokens
            )
            attempt += 1
            versions = VersionMetadata(
                workflow_version=self.state.workflow_version,
                prompt_version=spec.version,
                prompt_hash=spec.digest,
                input_schema_version=task.input_schema_version,
                output_schema_version=task.output_schema_version,
                model_policy_version=self.gateway.policy.version,
                provider=candidate.provider,
                model=candidate.model,
                retry_reason=previous if transport_retries else None,
                repair_reason="schema_invalid" if repairs else None,
            )
            row = e.ModelCall(
                step_id=self.step.id,
                task_type=task_type.value,
                provider=candidate.provider,
                model=candidate.model,
                attempts=attempt,
                versions=versions.model_dump(mode="json"),
                status=CallStatus.RUNNING,
            )
            self.session.add(row)
            await self.session.flush()
            started = time.perf_counter()
            error: ModelGatewayError | None = None
            result = None
            try:
                result = await self.gateway.generate(context, task)
            except ModelGatewayError as exc:
                error = exc
            actual = result.usage if result else error.usage if error else None
            usage = ledger.settle(reservation, actual)
            if result and result.versions.output_diagnostic:
                versions.output_diagnostic = result.versions.output_diagnostic
                row.versions = versions.model_dump(mode="json")
            if error and error.diagnostic:
                versions.output_diagnostic = error.diagnostic
                row.versions = versions.model_dump(mode="json")
            row.usage = usage.model_dump(mode="json")
            row.estimated_cost = usage.estimated_cost
            row.latency_ms = int((time.perf_counter() - started) * 1000)
            row.status = CallStatus.FAILED if error else CallStatus.SUCCEEDED
            row.schema_validation_state = (
                "invalid"
                if error
                and error.code
                in {"invalid_model_output", "structured_output_invalid", "output_validation_failed"}
                else "not_validated"
                if error
                else "valid"
            )
            row.error_code = error.code if error else None
            row.retryable = error.retryable if error else False
            row.finish_reason = result.finish_reason if result else None
            self.session.add(
                e.Observation(
                    model_call_id=row.id,
                    status=ObservationStatus.ERROR if error else ObservationStatus.OK,
                    error_code=row.error_code,
                    retryable=row.retryable,
                )
            )
            await self.session.flush()
            if result is not None:
                return result.validated_output
            assert error is not None
            if task_type == TaskType.COMPRESS:
                raise error  # exactly one semantic compression network attempt
            previous = error.code
            if (
                error.code
                in {"invalid_model_output", "structured_output_invalid", "output_validation_failed"}
                and repairs < self.settings.schema_repair_limit
            ):
                repairs += 1
                continue
            if error.retryable and transport_retries < self.settings.model_retry_limit:
                transport_retries += 1
                await asyncio.sleep(min(0.1 * 2**transport_retries, 1))
                continue
            raise error

    async def persist(
        self,
        kind: Literal["fit", "greeting", "interview", "package"],
        output: FitOutput | GreetingOutput | InterviewOutput | WorkflowState,
    ) -> UUID:
        row = e.PreparationArtifact(
            run_id=self.run.id,
            job_revision_id=self.request.job_revision_id,
            profile_id=self.request.profile_id,
            data=PrivateResult(kind=kind, output=output).model_dump(mode="json"),
        )
        self.session.add(row)
        await self.session.flush()
        return row.id

    async def validate_inputs(self) -> None:
        self.job = await require(self.session, e.JobRevision, self.request.job_revision_id)
        posting = await require(self.session, e.JobPosting, self.job.job_id)
        self.company = await require(self.session, e.Company, posting.company_id)
        self.profile = await require(self.session, e.PersonalProfile, self.request.profile_id)
        self.state.profile_revision = self.profile.revision
        self.state.job_id, self.state.job_revision = self.job.job_id, self.job.revision
        data = ProfileData.model_validate(self.profile.data)
        members = resumes.profile_fact_ids(self.profile)
        # Bounded verified-fact selection, stable ordering; never a full profile dump.
        rows = list(
            await self.session.scalars(
                select(e.PersonalFact)
                .where(e.PersonalFact.id.in_(members), e.PersonalFact.status == FactStatus.VERIFIED)
                .order_by(e.PersonalFact.id)
                .limit(61)
            )
        )
        if not rows:
            raise ModelGatewayError("missing_verified_fact")
        if len(rows) > 60:
            self.state.warnings.append("fact_context_limited")
            rows = rows[:60]
        self.fact_rows = {f.id: f for f in rows}
        self.facts = {
            f.id: {
                "id": str(f.id),
                "revision": f.revision,
                "statement": minimize(f.statement, data.display_name),
                "category": f.category,
                "trust_level": "user_verified",
            }
            for f in rows
        }
        if any(len(f["statement"]) > 12000 for f in self.facts.values()):
            raise ModelGatewayError("context_too_large")
        self.profile_refs = {
            "projects": [
                {"project_ref": i, "fact_refs": [str(f) for f in x.fact_ids if f in self.facts]}
                for i, x in enumerate(data.projects)
            ][:10]
        }
        self.protected_fields = [
            value
            for x in data.education + data.experiences + data.projects
            for value in [x.organization, x.role]
            if value
        ]
        if len(self.job.jd_text) > 20000:
            raise ModelGatewayError("context_too_large")

    def job_context(self) -> dict[str, Any]:
        return {
            "id": str(self.job.id),
            "title": minimize(self.job.title),
            "jd_text": minimize(self.job.jd_text),
            "trust_level": "untrusted_external",
        }

    def requirements_context(self) -> list[dict[str, Any]]:
        return [
            {
                "id": str(r.id),
                "text": r.text,
                "evidence_span": r.source_quote,
                "trust_level": "untrusted_external",
            }
            for r in self.requirements
        ]

    async def extract_requirements(self) -> None:
        output = cast(
            RequirementsOutput, await self.call(TaskType.EXTRACTION, {"job": self.job_context()})
        )
        output = validate_extraction(output, self.job.jd_text)
        # Never mutate old requirements that may support an existing variant.
        existing = list(
            await self.session.scalars(
                select(e.JobRequirement).where(e.JobRequirement.job_revision_id == self.job.id)
            )
        )
        for item in output.requirements:
            row = next(
                (
                    r
                    for r in existing
                    if r.text == item.normalized_requirement
                    and r.source_quote == item.evidence_span
                ),
                None,
            )
            if row is None:
                row = e.JobRequirement(
                    job_revision_id=self.job.id,
                    text=item.normalized_requirement,
                    category=item.category,
                    importance=item.requirement_kind
                    if item.requirement_kind in {"must", "nice_to_have"}
                    else "unknown",
                    source_quote=item.evidence_span,
                    extraction_metadata=item.model_dump(mode="json"),
                )
                self.session.add(row)
                await self.session.flush()
            self.requirements.append(row)
        self.state.requirement_refs = [r.id for r in self.requirements]

    async def research_company(self) -> None:
        now = e.utcnow()
        # Company lock serializes cache version allocation; no cross-company bottleneck.
        await require(self.session, e.Company, self.company.id, lock=True)
        cached = await self.session.scalar(
            select(e.CompanyResearch)
            .where(
                e.CompanyResearch.company_id == self.company.id,
                e.CompanyResearch.expires_at > now,
                e.CompanyResearch.data["mode"].astext == self.request.mode,
            )
            .order_by(e.CompanyResearch.research_version.desc())
        )
        if cached and not self.request.force_research_refresh:
            data = ResearchData.model_validate(cached.data)
            self.research_output = data.report
            self.state.research_report_id = cached.id
            self.state.evidence_refs = [x.id for x in data.evidence]
            return
        evidence = []
        for suffix in ["主营业务 产品 技术方向", "工程团队 AI Agent 技术方向"]:
            cost = self.settings.search_cost_per_call if self.request.mode == "live" else Decimal(0)
            ledger = BudgetLedger(self.state.limits, self.state.usage)
            reservation = ledger.reserve_search(cost)
            meta = SearchToolMetadata()
            row = e.ToolCall(
                step_id=self.step.id,
                tool_name=meta.tool_name,
                tool_version=meta.tool_version,
                usage=reservation.model_dump(mode="json"),
                attempt=self.state.usage.search_calls,
                status=CallStatus.RUNNING,
            )
            self.session.add(row)
            await self.session.flush()
            start = time.perf_counter()
            try:
                result = await self.research.search(
                    SearchInput(query=f"{minimize(self.company.name)} {suffix}")
                )
                evidence.extend(result.evidence)
                row.status = CallStatus.SUCCEEDED
                self.session.add(
                    e.Observation(
                        tool_call_id=row.id,
                        status=ObservationStatus.OK,
                        evidence_refs=[str(x.id) for x in result.evidence],
                    )
                )
            except ModelGatewayError:
                row.status, row.error_code = CallStatus.FAILED, "research_failed"
                self.session.add(
                    e.Observation(
                        tool_call_id=row.id,
                        status=ObservationStatus.ERROR,
                        error_code="research_failed",
                    )
                )
            row.latency_ms = int((time.perf_counter() - start) * 1000)
            row.usage = ledger.settle_search(
                reservation, succeeded=row.status == CallStatus.SUCCEEDED
            ).model_dump(mode="json")
            await self.session.flush()
            if row.status == CallStatus.FAILED and self.settings.research_fail_fast:
                raise ModelGatewayError("research_failed")
            # Deterministic sufficiency baseline, not a model deciding to research indefinitely.
            if sum(len(x.content) for x in evidence) >= 60:
                break
        if not evidence:
            raise ModelGatewayError("research_failed")
        output = cast(
            ResearchOutput,
            await self.call(
                TaskType.RESEARCH,
                {
                    "company": {"name": self.company.name, "trust_level": "untrusted_external"},
                    "evidence": [
                        x.model_dump(mode="json") | {"content": minimize(x.content)}
                        for x in evidence
                    ],
                },
            ),
        )
        validate_research(output, {x.id for x in evidence})
        version = await self.session.scalar(
            select(func.max(e.CompanyResearch.research_version)).where(
                e.CompanyResearch.company_id == self.company.id
            )
        )
        row_report = e.CompanyResearch(
            company_id=self.company.id,
            research_version=(version or 0) + 1,
            fetched_at=now,
            expires_at=now + timedelta(hours=self.settings.company_research_ttl_hours),
            data=ResearchData(evidence=evidence, report=output, mode=self.request.mode).model_dump(
                mode="json"
            ),
        )
        self.session.add(row_report)
        await self.session.flush()
        self.research_output = output
        self.state.research_report_id = row_report.id
        self.state.evidence_refs = [x.id for x in evidence]

    async def analyze_fit(self) -> None:
        self.fit = cast(
            FitOutput,
            await self.call(
                TaskType.FIT,
                {
                    "requirements": self.requirements_context(),
                    "facts": list(self.facts.values()),
                    "profile_refs": self.profile_refs,
                },
            ),
        )
        validate_fit(self.fit, set(self.state.requirement_refs), self.facts)
        self.state.fit_analysis_id = await self.persist("fit", self.fit)

    async def validate_variant(self, document: ResumeDocument, *, persist: bool = True) -> None:
        if (
            document.profile_id != self.profile.id
            or document.profile_revision != self.profile.revision
            or document.job_revision_id != self.job.id
        ):
            raise ModelGatewayError("variant_identity_invalid")
        snapshot = await resumes.snapshot_for(self.session, document)
        # Recheck facts immediately before persistence; v0.1b also locks/rechecks at render.
        await self.session.refresh(self.profile)
        current = list(
            await self.session.scalars(
                select(e.PersonalFact)
                .where(e.PersonalFact.id.in_(self.facts))
                .execution_options(populate_existing=True)
            )
        )
        findings = validate_grounding(
            document,
            snapshot,
            resumes.profile_fact_ids(self.profile),
            {f.id: FactEvidence(f.id, f.revision, f.status, f.statement) for f in current},
            set(self.state.requirement_refs),
        )
        if findings:
            raise ModelGatewayError("grounding_failed")
        for section in document.sections:
            for item in section.items:
                if section.name != "skills":
                    chinese(item.text)
                if item.short_text and section.name != "skills":
                    chinese(item.short_text)
        if not persist:
            return
        if self.variant is None:
            self.variant = await resumes.create_variant(self.session, document)
        else:
            self.variant = await resumes.revise_variant(
                self.session, self.variant.resume_variant_id, self.variant.revision, document
            )
        self.state.resume_variant_id = self.variant.resume_variant_id
        self.state.resume_variant_revision = self.variant.revision

    async def tailor_resume(self) -> None:
        assert self.fit is not None
        doc = cast(
            ResumeDocument,
            await self.call(
                TaskType.TAILOR,
                {
                    "facts": list(self.facts.values()),
                    "profile_refs": self.profile_refs,
                    "requirements": self.requirements_context(),
                    "fit": self.fit.model_dump(mode="json"),
                    "layout_budget": LayoutBudget().model_dump(),
                    "identity": {
                        "profile_id": str(self.profile.id),
                        "profile_revision": self.profile.revision,
                        "job_revision_id": str(self.job.id),
                        "locale": "zh-CN",
                        "schema_version": "resume-v2",
                        "template": "resume_zh_cn_a4_single_v1",
                        "target_page_count": 1,
                    },
                },
            ),
        )
        budget = LayoutBudget()
        if (
            sum(len(i.text) for s in doc.sections for i in s.items) > budget.max_total_characters
            or any(len(i.text) > budget.max_bullet_length for s in doc.sections for i in s.items)
            or any(
                s.name == "experience"
                and sum(i.kind == "bullet" for i in s.items) > budget.max_experience_bullets
                for s in doc.sections
            )
            or any(
                s.name == "projects"
                and (
                    sum(i.kind == "entry" for i in s.items) > budget.max_projects
                    or sum(i.kind == "bullet" for i in s.items)
                    > budget.max_projects * budget.max_bullets_per_project
                )
                for s in doc.sections
            )
        ):
            raise ModelGatewayError("layout_budget_exceeded")
        await self.validate_variant(doc)

    async def compile_resume(self) -> None:
        assert self.variant is not None
        artifact = await resumes.render_variant(self.session, self.variant, self.settings)
        self.state.render_report_id = artifact.id
        self.report = RenderReport.model_validate(artifact.report)
        if self.report.render_status == "failed" and self.report.error_code != "layout_failed":
            raise ModelGatewayError(self.report.error_code or "compile_failed")

    async def compress_resume(self) -> None:
        assert self.variant is not None and self.report is not None
        self.state.usage.semantic_compressions += 1
        before = ResumeDocument.model_validate(self.variant.document)
        used = {f for s in before.sections for i in s.items for f in i.fact_refs}
        after = cast(
            ResumeDocument,
            await self.call(
                TaskType.COMPRESS,
                {
                    "variant": before.model_dump(mode="json"),
                    "facts": [v for k, v in self.facts.items() if k in used],
                    "layout_observation": {
                        "status": "layout_failed",
                        "page_count": self.report.page_count,
                    },
                    "layout_budget": LayoutBudget().model_dump(),
                    "protected_fields": self.protected_fields,
                },
            ),
        )
        validate_compression(before, after, self.protected_fields)
        await self.validate_variant(after)

    async def generate_greeting(self) -> None:
        assert self.fit is not None and self.variant is not None
        doc = ResumeDocument.model_validate(self.variant.document)
        ids = {f for s in doc.sections for i in s.items for f in i.fact_refs}
        output = cast(
            GreetingOutput,
            await self.call(
                TaskType.GREETING,
                {
                    "job": {"title": self.job.title, "trust_level": "untrusted_external"},
                    "research": self.research_output.model_dump(mode="json")
                    if self.research_output
                    else None,
                    "fit": self.fit.model_dump(mode="json"),
                    "facts": [v for k, v in self.facts.items() if k in ids],
                    "requirements": self.requirements_context(),
                },
            ),
        )
        validate_greeting(
            output,
            set(self.state.requirement_refs),
            {k: v for k, v in self.facts.items() if k in ids},
        )
        self.state.greeting_id = await self.persist("greeting", output)

    async def load_interview_context(self) -> None:
        if not self.request.application_package_id:
            raise ModelGatewayError("application_package_required")
        row = await require(
            self.session, e.PreparationArtifact, self.request.application_package_id
        )
        data = PrivateResult.model_validate(row.data)
        if data.kind != "package" or not isinstance(data.output, WorkflowState):
            raise ModelGatewayError("invalid_application_package")
        state = data.output
        if (
            state.workflow != "prepare_application"
            or state.mode != self.request.mode
            or row.job_revision_id != self.job.id
            or row.profile_id != self.profile.id
        ):
            raise ModelGatewayError("context_revision_mismatch")
        if (
            not state.fit_analysis_id
            or not state.resume_variant_id
            or not state.resume_variant_revision
        ):
            raise ModelGatewayError("preparation_context_missing")
        self.state.requirement_refs = state.requirement_refs
        self.requirements = list(
            await self.session.scalars(
                select(e.JobRequirement).where(e.JobRequirement.id.in_(state.requirement_refs))
            )
        )
        self.fit = FitOutput.model_validate(
            (await require(self.session, e.PreparationArtifact, state.fit_analysis_id)).data[
                "output"
            ]
        )
        validate_fit(self.fit, set(state.requirement_refs), self.facts)
        self.state.fit_analysis_id = state.fit_analysis_id
        self.variant = await resumes.get_revision(
            self.session, state.resume_variant_id, state.resume_variant_revision
        )
        await self.validate_variant(
            ResumeDocument.model_validate(self.variant.document), persist=False
        )
        self.state.resume_variant_id, self.state.resume_variant_revision = (
            state.resume_variant_id,
            state.resume_variant_revision,
        )
        self.state.render_report_id = state.render_report_id
        if not state.render_report_id:
            raise ModelGatewayError("accepted_resume_required")
        rendered = await require(self.session, e.RenderArtifact, state.render_report_id)
        if (
            rendered.resume_variant_id != state.resume_variant_id
            or rendered.resume_variant_revision != state.resume_variant_revision
            or RenderReport.model_validate(rendered.report).render_status != "accepted"
        ):
            raise ModelGatewayError("accepted_resume_required")
        if state.research_report_id:
            research = await require(self.session, e.CompanyResearch, state.research_report_id)
            if research.company_id != self.company.id:
                raise ModelGatewayError("context_revision_mismatch")
            self.research_output = ResearchData.model_validate(research.data).report
            self.state.research_report_id = research.id
            if research.expires_at <= e.utcnow():
                self.state.warnings.append("research_context_stale")

    async def generate_interview_prep(self) -> None:
        assert self.fit is not None and self.variant is not None
        data = ProfileData.model_validate(self.profile.data)
        stories = []
        for id in self.request.star_story_ids[:10]:
            story = await require(self.session, e.StarStory, id)
            if not {UUID(x) for x in story.data.get("fact_ids", [])} <= set(self.facts):
                raise ModelGatewayError("invalid_story_reference")
            stories.append(
                {
                    "id": str(id),
                    "trust_level": "user_context_not_verified",
                    "text": minimize(str(story.data), data.display_name)[:4000],
                }
            )
        notes = []
        for id in self.request.knowledge_note_ids[:10]:
            note = await require(self.session, e.KnowledgeNote, id)
            notes.append(
                {
                    "id": str(id),
                    "trust_level": "user_context_not_verified",
                    "text": minimize(note.content, data.display_name)[:2000],
                }
            )
        output = cast(
            InterviewOutput,
            await self.call(
                TaskType.INTERVIEW,
                {
                    "job": self.job_context(),
                    "research": self.research_output.model_dump(mode="json")
                    if self.research_output
                    else None,
                    "fit": self.fit.model_dump(mode="json"),
                    "variant": self.variant.document,
                    "facts": list(self.facts.values()),
                    "requirements": self.requirements_context(),
                    "profile_refs": self.profile_refs,
                    "stories": stories,
                    "notes": notes,
                },
            ),
        )
        validate_interview(
            output,
            set(self.state.requirement_refs),
            set(self.facts),
            {x["project_ref"] for x in self.profile_refs["projects"]},
        )
        self.state.interview_prep_id = await self.persist("interview", output)

    async def node(self, name: str) -> GraphState:
        self.state.step_count += 1
        self.state.current_node = name
        self.step = e.AgentStep(
            run_id=self.run.id,
            sequence=self.state.step_count,
            node=name,
            status=CallStatus.RUNNING,
            versions={"workflow_version": "preparation-v1"},
        )
        self.session.add(self.step)
        await self.session.flush()
        started = time.perf_counter()
        try:
            method = self.compile_resume if name == "recompile_resume" else getattr(self, name)
            await method()
            self.step.status = CallStatus.SUCCEEDED
        except (ModelGatewayError, DomainError, ValidationError) as exc:
            code = (
                exc.code if isinstance(exc, (ModelGatewayError, DomainError)) else "invalid_output"
            )
            self.step.status, self.step.reason_code = CallStatus.FAILED, code
            if code in {
                "grounding_failed",
                "invalid_reference",
                "hard_field_mismatch",
                "locale_invalid",
                "layout_budget_exceeded",
                "variant_identity_invalid",
                "compression_required_changed",
                "compression_facts_changed",
                "compression_hard_field_changed",
                "compression_not_shorter",
            }:
                diagnostic = OutputDiagnostic(
                    failure_kind="output_guardrail_failed", guardrail_code=code
                )
                self.step.versions = VersionMetadata(
                    workflow_version=self.state.workflow_version, output_diagnostic=diagnostic
                ).model_dump(mode="json")
            if (
                name == "research_company"
                and not self.settings.research_fail_fast
                and code
                not in {
                    "budget_exhausted",
                    "insufficient_token_budget",
                    "no_eligible_model",
                }
            ):
                self.state.warnings.append("research_unavailable")
            else:
                self.state.errors.append(code)
                self.state.stop_reason = (
                    "budget_exhausted"
                    if code in {"insufficient_token_budget", "no_eligible_model"}
                    else code
                )
        self.step.latency_ms = int((time.perf_counter() - started) * 1000)
        await self.session.flush()
        return {"state": self.state.model_dump(mode="json")}

    def after_compile(self, _: GraphState) -> str:
        if self.state.stop_reason:
            return "persist_package"
        assert self.report is not None
        if self.report.render_status == "accepted":
            return "generate_greeting"
        if (
            self.report.error_code == "layout_failed"
            and self.state.usage.semantic_compressions
            < self.state.limits.max_semantic_resume_compressions
        ):
            return "compress_resume"
        self.state.stop_reason = "layout_failed"
        self.state.errors.append("layout_failed")
        return "persist_package"

    async def persist_package(self, state: GraphState) -> GraphState:
        st = self.state
        complete = (
            bool(st.interview_prep_id)
            if st.workflow == "prepare_interview"
            else bool(st.greeting_id)
        )
        st.status = (
            "completed"
            if complete and not st.warnings
            else "partial"
            if (complete or st.requirement_refs or st.stop_reason == "budget_exhausted")
            else "failed"
        )
        st.current_node = "finish"
        self.run.status = {
            "completed": RunStatus.SUCCEEDED,
            "partial": RunStatus.PARTIAL,
            "failed": RunStatus.FAILED,
        }[st.status]
        self.run.stop_reason = st.stop_reason or (
            "completed" if st.status == "completed" else "partial_results"
        )
        self.run.finished_at = e.utcnow()
        self.run.consumed_usage = Usage(
            input_tokens=st.usage.input_tokens,
            output_tokens=st.usage.output_tokens,
            estimated_cost=st.usage.estimated_cost,
            budget_reserved_usd=st.usage.budget_reserved_usd,
            reserved_input_tokens=st.usage.reserved_input_tokens,
            reserved_output_tokens=st.usage.reserved_output_tokens,
            search_calls=st.usage.search_calls,
            measurement="unknown" if st.usage.unknown_usage_attempts else "reported",
            pricing_version=self.settings.pricing_version,
        ).model_dump(mode="json")
        id = await self.persist("package", st)
        return {"state": st.model_dump(mode="json"), "package_id": str(id)}

    async def execute(
        self, workflow: Literal["prepare_application", "prepare_interview"]
    ) -> dict[str, Any]:
        # Validate source identities before creating FK-bearing artifacts, no external calls.
        await require(self.session, e.JobRevision, self.request.job_revision_id)
        await require(self.session, e.PersonalProfile, self.request.profile_id)
        limits = self.request.limits.model_copy(deep=True)
        limits.max_estimated_cost = min(limits.max_estimated_cost, self.settings.max_run_cost)
        self.run = e.AgentRun(
            workflow=workflow,
            workflow_version="preparation-v1",
            status=RunStatus.RUNNING,
            started_at=e.utcnow(),
            requested_outputs=["application_package"]
            if workflow == "prepare_application"
            else ["interview_prep"],
            budget=Budget(
                token_limit=limits.max_input_tokens + limits.max_output_tokens,
                cost_limit=limits.max_estimated_cost,
            ).model_dump(mode="json"),
        )
        self.session.add(self.run)
        await self.session.flush()
        self.state = WorkflowState(
            run_id=self.run.id,
            workflow=workflow,
            mode=self.request.mode,
            job_revision_id=self.request.job_revision_id,
            profile_id=self.request.profile_id,
            requested_outputs=self.run.requested_outputs,
            limits=limits,
        )
        graph = StateGraph(GraphState)
        names = (
            [
                "validate_inputs",
                "extract_requirements",
                "research_company",
                "analyze_fit",
                "tailor_resume",
                "compile_resume",
                "compress_resume",
                "recompile_resume",
                "generate_greeting",
            ]
            if workflow == "prepare_application"
            else ["validate_inputs", "load_interview_context", "generate_interview_prep"]
        )
        for name in names:

            async def action(state: GraphState, node_name: str = name) -> GraphState:
                return await self.node(node_name)

            graph.add_node(name, action)
        graph.add_node("persist_package", self.persist_package, input_schema=GraphState)
        graph.add_edge(START, names[0])
        for index, name in enumerate(names):
            if name in {"compile_resume", "recompile_resume"}:
                graph.add_conditional_edges(
                    name,
                    self.after_compile,
                    {x: x for x in ["generate_greeting", "compress_resume", "persist_package"]},
                )
            else:
                next_name = names[index + 1] if index + 1 < len(names) else "persist_package"

                def edge(state: GraphState, target: str = next_name) -> str:
                    return "persist_package" if self.state.stop_reason else target

                graph.add_conditional_edges(
                    name, edge, {x: x for x in {next_name, "persist_package"}}
                )
        graph.add_edge("persist_package", END)
        # Disable environment-enabled LangSmith export; private payloads never leave via traces.
        with tracing_context(enabled=False):
            result = await graph.compile().ainvoke(
                {"state": self.state.model_dump(mode="json")},
                config={"recursion_limit": 20, "callbacks": []},
            )
        return cast(dict[str, Any], result)
