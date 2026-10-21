"""Finite target dependency execution. No model-selected plan, recovery or hidden work."""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from career_agent.application import resumes
from career_agent.application.compatibility import compatible, execution_versions
from career_agent.application.services import require
from career_agent.domain.rules import DomainError, RunStatus
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.claims import claim
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.context import ContextLoader
from career_agent.preparation.contracts import (
    FitOutput,
    PlanNode,
    PrivateResult,
    ResumeBinding,
    Target,
    TargetArtifact,
    TargetOutcome,
    TaskType,
    WorkflowOutcome,
    WorkflowState,
)
from career_agent.preparation.observation_store import ReuseDecision
from career_agent.preparation.prompts import PROMPTS
from career_agent.resume.renderer import CompileError
from career_agent.resume.schemas import RenderReport, ResumeDocument
from career_agent.runtime.contracts import Budget, Usage

if TYPE_CHECKING:
    from career_agent.preparation.workflows import PreparationWorkflow

ERRORS = (ModelGatewayError, DomainError, CompileError, ValidationError)


def error_code(exc: Exception) -> str:
    return str(getattr(exc, "code", "invalid_context"))


def fit_gate(fit: FitOutput, requirements: list[e.JobRequirement]) -> str | None:
    must = {r.id for r in requirements if r.importance == "must"}
    if not must:
        return None
    gaps = sum(x.status == "explicit_gap" for x in fit.items if x.requirement_ref in must)
    missing = sum(x.status == "no_evidence" for x in fit.items if x.requirement_ref in must)
    if gaps >= 2 or gaps * 2 >= len(must):
        return "low_fit"
    if missing * 2 >= len(must):
        return "insufficient_evidence"
    return None


class Orchestrator:
    def __init__(self, runner: "PreparationWorkflow") -> None:
        self.r = runner
        self.loader = ContextLoader(runner)
        self.nodes: list[PlanNode] = []
        self.results: dict[Target, TargetOutcome] = {}
        self.special: Literal["needs_input", "decision_required"] | None = None
        self.reason: str | None = None
        self.bindings: dict[str, ResumeBinding] = {}
        self.gate_used = False
        self.claim_contended = False

    def record(
        self,
        name: str,
        status: Literal["executed", "reused", "skipped", "failed", "blocked"],
        reason: str | None = None,
    ) -> None:
        self.nodes.append(PlanNode(name=name, status=status, reason=reason))
        if status in {"executed", "reused"} and name in {
            "fit_analysis",
            "resume_tailoring",
            "greeting_generation",
            "interview_preparation",
            "requirements",
            "extract_requirements",
            "research_company",
        }:
            self.r.session.add(
                ReuseDecision(
                    run_id=self.r.run.id,
                    category="business_artifact",
                    operation=name,
                    disposition=status,
                )
            )

    async def node(self, name: str) -> None:
        self.r.state.stop_reason = None
        await self.r.node(name)
        if self.r.state.stop_reason:
            self.record(name, "failed", self.r.state.stop_reason)
            raise ModelGatewayError(self.r.state.stop_reason)
        self.record(name, "executed")

    async def prerequisites(self) -> None:
        r = self.r
        self.claim_contended = await claim(
            r.session,
            "requirements:" + str(r.job.id),
            wait_seconds=min(
                r.settings.reuse_claim_wait_seconds, r.runtime_budget.remaining_seconds()
            )
            if r.runtime_budget
            else r.settings.reuse_claim_wait_seconds,
        )
        r.requirements = await self.loader.requirements()
        if r.requirements:
            r.state.requirement_refs = [x.id for x in r.requirements]
            self.record("requirements", "reused")
        else:
            if self.claim_contended:
                raise ModelGatewayError("reuse_result_unavailable")
            await self.node("extract_requirements")
            r.requirements = await self.loader.requirements(r.state.requirement_refs)
        # Research is opportunistic existing context only, never a hidden paid prerequisite.
        candidates = await r.session.scalars(
            select(e.CompanyResearch)
            .where(
                e.CompanyResearch.company_id == r.company.id,
                e.CompanyResearch.expires_at > e.utcnow(),
                e.CompanyResearch.data["mode"].astext == r.request.mode,
            )
            .order_by(e.CompanyResearch.research_version.desc())
        )
        for cached in candidates:
            if not compatible(
                cached.data.get("compatibility_versions"), execution_versions("company_research")
            ).reusable_for_current_execution:
                continue
            data = await self.loader.research(cached.id)
            r.research_output = data.report
            r.state.research_report_id = cached.id
            r.state.evidence_refs = [x.id for x in data.evidence]
            self.record("research_company", "reused")
            return
        self.record("research_company", "skipped", "no_compatible_research")

    def fingerprint(self, target: Target, source: UUID | None) -> str:
        r = self.r
        payload = {
            "workflow": "preparation-v2",
            "task": PROMPTS[TaskType(target)].prompt_hash,
            "mode": r.request.mode,
            "profile": str(r.profile.id),
            "revision": r.profile.revision,
            "job": str(r.job.id),
            "requirements": sorted(str(x) for x in r.state.requirement_refs),
            "facts": sorted((str(x.id), x.revision, x.status.value) for x in r.fact_rows.values()),
            "source": str(source) if source else None,
            "research": str(r.state.research_report_id)
            if target in {"greeting_generation", "interview_preparation"}
            else None,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    async def restore(self, artifact: TargetArtifact) -> None:
        r = self.r
        if artifact.target == "resume_tailoring":
            if not artifact.resume_revision_id or not artifact.render_artifact_id:
                raise ModelGatewayError("context_revision_mismatch")
            r.variant = await self.loader.resume(artifact.resume_revision_id, target_job=True)
            rendered = await self.loader.render(artifact.render_artifact_id, r.variant)
            r.state.resume_variant_id = r.variant.resume_variant_id
            r.state.resume_variant_revision = r.variant.revision
            r.state.render_report_id = rendered.id
            r.report = RenderReport.model_validate(rendered.report)
        else:
            if not artifact.result_id:
                raise ModelGatewayError("context_revision_mismatch")
            row = await require(r.session, e.PreparationArtifact, artifact.result_id)
            if row.profile_id != r.profile.id or row.job_revision_id != r.job.id:
                raise ModelGatewayError("context_revision_mismatch")
            if artifact.target == "fit_analysis":
                r.fit = await self.loader.fit(row.id)
                r.state.fit_analysis_id = row.id
            elif artifact.target == "greeting_generation":
                from career_agent.preparation.contracts import GreetingOutput
                from career_agent.preparation.guardrails import validate_greeting

                value = PrivateResult.model_validate(row.data)
                if not isinstance(value.output, GreetingOutput):
                    raise ModelGatewayError("context_revision_mismatch")
                validate_greeting(value.output, set(r.state.requirement_refs), r.facts)
                r.state.greeting_id = row.id
            else:
                from career_agent.preparation.contracts import InterviewOutput
                from career_agent.preparation.guardrails import validate_interview

                value = PrivateResult.model_validate(row.data)
                if not isinstance(value.output, InterviewOutput):
                    raise ModelGatewayError("context_revision_mismatch")
                validate_interview(
                    value.output,
                    set(r.state.requirement_refs),
                    set(r.facts),
                    {x["project_ref"] for x in r.profile_refs["projects"]},
                )
                r.state.interview_prep_id = row.id

    async def target(self, target: Target, source: UUID | None = None) -> UUID:
        r = self.r
        key = self.fingerprint(target, source)
        if target == "interview_preparation":
            # Interview inputs include exact package and explicitly selected notes/stories.
            selected_context = []
            for id in r.request.star_story_ids[:10]:
                story = await require(r.session, e.StarStory, id)
                selected_context.append({"id": str(id), "data": story.data})
            for id in r.request.knowledge_note_ids[:10]:
                note = await require(r.session, e.KnowledgeNote, id)
                selected_context.append({"id": str(id), "content": note.content})
            key = hashlib.sha256(
                (
                    key
                    + str(r.request.application_package_id)
                    + json.dumps(selected_context, sort_keys=True)
                ).encode()
            ).hexdigest()
        contended = await claim(
            r.session,
            "artifact:" + key,
            wait_seconds=min(
                r.settings.reuse_claim_wait_seconds, r.runtime_budget.remaining_seconds()
            )
            if r.runtime_budget
            else r.settings.reuse_claim_wait_seconds,
        )
        candidates = await r.session.scalars(
            select(e.PreparationArtifact)
            .where(
                e.PreparationArtifact.profile_id == r.profile.id,
                e.PreparationArtifact.job_revision_id == r.job.id,
                e.PreparationArtifact.data["kind"].astext == "target",
                e.PreparationArtifact.data["output"]["fingerprint"].astext == key,
            )
            .order_by(e.PreparationArtifact.created_at.desc())
        )
        for row in candidates:
            stored = PrivateResult.model_validate(row.data).output
            if not isinstance(stored, TargetArtifact) or stored.target != target:
                continue
            if not compatible(
                stored.compatibility_versions, execution_versions(target)
            ).reusable_for_current_execution:
                continue
            await self.restore(stored)
            self.record(target, "reused")
            return row.id
        # A waiter may consume committed compatible output, but may not automatically retry
        # the same failed/rolled-back generation. A later explicit request can retry normally.
        started_peer = (
            await r.session.scalar(
                select(ReuseDecision.id).where(
                    ReuseDecision.identity_hash == key,
                    ReuseDecision.category == "business_claim",
                    ReuseDecision.disposition == "started",
                )
            )
            if self.claim_contended
            else None
        )
        if contended or started_peer:
            raise ModelGatewayError("reuse_result_unavailable")
        # Independent metadata-only intent survives business rollback. It is not proof of
        # dispatch/usage (the attempt journal owns that). A contending request with no
        # authoritative result must fail conservatively; a later explicit request may retry.
        sessions = async_sessionmaker(r.session.bind, expire_on_commit=False)
        async with sessions.begin() as intent_session:
            intent_session.add(
                ReuseDecision(
                    run_id=r.run.id,
                    category="business_claim",
                    operation=target,
                    disposition="started",
                    identity_hash=key,
                )
            )
        try:
            if target == "fit_analysis":
                # Old outputs remain readable; missing validator/source provenance is not reusable.
                await self.node("analyze_fit")
                output = TargetArtifact(
                    target=target, fingerprint=key, result_id=r.state.fit_analysis_id
                )
            elif target == "resume_tailoring":
                assert source is not None
                selected = await self.loader.resume(source)
                r.base_document = ResumeDocument.model_validate(selected.document)
                # Keep the explicit immutable base; append at the current head without replacing it.
                r.variant = await resumes.get_revision(r.session, selected.resume_variant_id)
                saved_fit = r.fit
                r.fit = None  # Optional Fit never creates an implicit dependency/cache input.
                try:
                    await self.node("tailor_resume")
                finally:
                    r.fit = saved_fit
                await self.node("compile_resume")
                assert r.report is not None
                if (
                    r.report.error_code == "layout_failed"
                    and r.state.limits.max_semantic_resume_compressions
                ):
                    await self.node("compress_resume")
                    await self.node("recompile_resume")
                if r.report.render_status != "accepted":
                    raise ModelGatewayError(r.report.error_code or "layout_failed")
                assert r.variant is not None
                output = TargetArtifact(
                    target=target,
                    fingerprint=key,
                    resume_revision_id=r.variant.id,
                    render_artifact_id=r.state.render_report_id,
                    source_resume_revision_id=source,
                )
            elif target == "greeting_generation":
                assert source is not None
                selected = await self.loader.resume(source)
                saved_variant, saved_fit = r.variant, r.fit
                r.variant, r.fit = selected, None
                try:
                    await self.node("generate_greeting")
                finally:
                    r.variant, r.fit = saved_variant, saved_fit
                output = TargetArtifact(
                    target=target,
                    fingerprint=key,
                    result_id=r.state.greeting_id,
                    source_resume_revision_id=source,
                )
            else:
                await self.node("generate_interview_prep")
                output = TargetArtifact(
                    target=target,
                    fingerprint=key,
                    result_id=r.state.interview_prep_id,
                    source_resume_revision_id=source,
                )
        except ERRORS:
            r.session.add(
                ReuseDecision(
                    run_id=r.run.id,
                    category="business_artifact",
                    operation=target,
                    disposition="failed",
                    identity_hash=key,
                )
            )
            raise
        output.compatibility_versions = execution_versions(target)
        row = e.PreparationArtifact(
            run_id=r.run.id,
            job_revision_id=r.job.id,
            profile_id=r.profile.id,
            data=PrivateResult(kind="target", output=output).model_dump(mode="json"),
        )
        r.session.add(row)
        await r.session.flush()
        self.record(target, "executed")
        return row.id

    async def application(self) -> None:
        r = self.r
        self.results = {cast(Target, t): TargetOutcome() for t in r.request.targets}
        for t in r.request.targets:
            if t == "fit_analysis":
                continue
            binding = r.request.bindings.get(t)
            if binding is None and r.request.resume_revision_id:
                binding = ResumeBinding(resume_revision_id=r.request.resume_revision_id)
            if binding is None:
                self.special, self.reason = "needs_input", "resume_selection_required"
                self.record(t, "blocked", self.reason)
            else:
                self.bindings[t] = binding
        r.state.bindings = self.bindings
        if self.special:
            return  # all required user input resolved before any paid prerequisite
        # Validate every explicit selection before executing any model task.
        for binding in self.bindings.values():
            if binding.resume_revision_id:
                await self.loader.resume(binding.resume_revision_id)
        if r.request.force_research_refresh:
            raise ModelGatewayError("research_refresh_not_a_target")
        await self.prerequisites()
        gate = r.request.fit_gate == "gate_downstream" and any(
            t != "fit_analysis" for t in self.results
        )
        fit_failed: str | None = None
        if "fit_analysis" in self.results or gate:
            try:
                id = await self.target("fit_analysis")
                if "fit_analysis" in self.results:
                    self.results["fit_analysis"] = TargetOutcome(status="completed", artifact_id=id)
            except ERRORS as exc:
                fit_failed = error_code(exc)
                if "fit_analysis" in self.results:
                    self.results["fit_analysis"] = TargetOutcome(status="failed", reason=fit_failed)
        else:
            self.record("fit_analysis", "skipped", "not_requested")
        if gate:
            self.gate_used = True
            if fit_failed:
                for result_target, v in self.results.items():
                    if v.status == "pending":
                        self.results[result_target] = TargetOutcome(
                            status="blocked", reason=fit_failed
                        )
                return
            assert r.fit is not None
            decision = fit_gate(r.fit, r.requirements)
            self.record("fit_gate", "executed", decision)
            if decision:
                self.special, self.reason = "decision_required", decision
                for result_target in self.results:
                    if result_target != "fit_analysis":
                        self.record(result_target, "blocked", decision)
                return
        for target in ("resume_tailoring", "greeting_generation"):
            if target not in self.results:
                self.record(target, "skipped", "not_requested")
                continue
            binding = self.bindings[target]
            source = binding.resume_revision_id
            if binding.output_of:
                if self.results["resume_tailoring"].status != "completed" or r.variant is None:
                    self.results[target] = TargetOutcome(
                        status="blocked", reason="dependency_failed"
                    )
                    self.record(target, "blocked", "dependency_failed")
                    continue
                source = r.variant.id
            try:
                id = await self.target(target, source)
                self.results[target] = TargetOutcome(status="completed", artifact_id=id)
            except ERRORS as exc:
                code = error_code(exc)
                self.results[target] = TargetOutcome(status="failed", reason=code)
                self.record(target, "failed", code)

    async def finish(self) -> dict[str, Any]:
        r = self.r
        completed = sum(v.status == "completed" for v in self.results.values())
        status = self.special or (
            "completed" if completed == len(self.results) else "partial" if completed else "failed"
        )
        reason = self.reason or next((v.reason for v in self.results.values() if v.reason), None)
        outcome = WorkflowOutcome(
            status=status,
            reason=reason,
            targets=self.results,
            nodes=self.nodes,
            gate_policy_version="fit_gate_policy_v1" if self.gate_used else None,
        )
        r.state.outcome = outcome
        r.state.status = outcome.status
        r.state.stop_reason = outcome.reason
        r.state.current_node = "finish"
        r.run.outcome = outcome.model_dump(mode="json")
        r.run.status = {
            "completed": RunStatus.SUCCEEDED,
            "partial": RunStatus.PARTIAL,
            "failed": RunStatus.FAILED,
            "needs_input": RunStatus.NEEDS_INPUT,
            "decision_required": RunStatus.DECISION_REQUIRED,
        }[outcome.status]
        r.run.stop_reason = outcome.reason or outcome.status
        r.run.finished_at = e.utcnow()
        u = r.state.usage
        r.run.consumed_usage = Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            estimated_cost=u.estimated_cost,
            budget_reserved_usd=u.budget_reserved_usd,
            reserved_input_tokens=u.reserved_input_tokens,
            reserved_output_tokens=u.reserved_output_tokens,
            search_calls=u.search_calls,
            measurement="unknown" if u.unknown_usage_attempts else "reported",
            pricing_version=r.settings.pricing_version,
        ).model_dump(mode="json")
        package_id = await r.persist("package", r.state)
        return {
            "state": r.state.model_dump(mode="json"),
            "package_id": str(package_id),
            "outcome": outcome.model_dump(mode="json"),
        }


async def execute(
    r: "PreparationWorkflow", workflow: Literal["prepare_application", "prepare_interview"]
) -> dict[str, Any]:
    await require(r.session, e.JobRevision, r.request.job_revision_id)
    await require(r.session, e.PersonalProfile, r.request.profile_id)
    limits = r.request.limits.model_copy(deep=True)
    limits.max_estimated_cost = min(limits.max_estimated_cost, r.settings.max_run_cost)
    requested = (
        list(r.request.targets) if workflow == "prepare_application" else ["interview_preparation"]
    )
    r.run = e.AgentRun(
        workflow=workflow,
        workflow_version="preparation-v2",
        status=RunStatus.RUNNING,
        started_at=e.utcnow(),
        requested_outputs=requested,
        budget=Budget(
            token_limit=limits.max_input_tokens + limits.max_output_tokens,
            cost_limit=limits.max_estimated_cost,
        ).model_dump(mode="json"),
    )
    r.session.add(r.run)
    await r.session.flush()
    r.state = WorkflowState(
        run_id=r.run.id,
        workflow=workflow,
        mode=r.request.mode,
        job_revision_id=r.request.job_revision_id,
        profile_id=r.request.profile_id,
        requested_outputs=requested,
        limits=limits,
    )
    o = Orchestrator(r)
    o.results = {cast(Target, t): TargetOutcome() for t in requested}
    try:
        await o.node("validate_inputs")
        if workflow == "prepare_application":
            await o.application()
        else:
            await o.node("load_interview_context")
            assert r.variant is not None
            id = await o.target("interview_preparation", r.variant.id)
            o.results["interview_preparation"] = TargetOutcome(status="completed", artifact_id=id)
    except ERRORS as exc:
        code = error_code(exc)
        for t, v in o.results.items():
            if v.status == "pending":
                o.results[t] = TargetOutcome(status="failed", reason=code)
        o.reason = code
    return await o.finish()
