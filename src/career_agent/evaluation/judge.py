"""Explicit bounded drain of pending quality judgments; no production background worker."""

import asyncio
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import require
from career_agent.config import Settings
from career_agent.domain.rules import CallStatus, DomainError, RunStatus
from career_agent.evaluation import entities as q
from career_agent.evaluation.contracts import (
    EvalLimits,
    FaultPlan,
    JudgeOutput,
    JudgeSpec,
    OperationSnapshot,
    SamplingDecision,
)
from career_agent.evaluation.execution import ScopedProvider, SharedEvalBudget
from career_agent.evaluation.faults import FaultController
from career_agent.evaluation.monitoring import payload_from_invocation, resolve_subject
from career_agent.evaluation.prompts import PROMPT
from career_agent.evaluation.recording import EVALUATION_ORIGIN
from career_agent.evaluation.store import capture
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, PrivacyClass
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.contracts import RunLimits
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.runtime.contracts import Budget, Usage
from career_agent.security.model_view import model_view


def severity(output: JudgeOutput) -> str:
    ratings = {c.rating for c in output.criteria}
    return next(
        x for x in ["major_issue", "minor_issue", "insufficient_evidence", "pass"] if x in ratings
    )


def validate_judge(output: JudgeOutput, spec: JudgeSpec, evidence: set[str]) -> None:
    if sorted(c.criterion for c in output.criteria) != sorted(spec.criteria):
        raise ModelGatewayError("judge_criteria_invalid")
    if any(set(c.evidence_refs) - evidence for c in output.criteria):
        raise ModelGatewayError("judge_evidence_invalid")
    if any(not c.evidence_refs and c.rating != "insufficient_evidence" for c in output.criteria):
        raise ModelGatewayError("judge_evidence_required")


class JudgeRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        gateway: ModelGateway | None = None,
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.gateway = gateway or ModelGateway(
            registry(settings, False), POLICY, {"fixture": FixtureTaskProvider()}
        )

    async def drain(
        self, *, limit: int = 20, concurrency: int = 2, limits: EvalLimits | None = None
    ) -> dict[str, Any]:
        if not 1 <= limit <= 200 or not 1 <= concurrency <= 8:
            raise DomainError("invalid_judge_drain_limits")
        ceilings = limits or EvalLimits(max_model_calls=20)
        budget = SharedEvalBudget(ceilings, ceilings.max_active_seconds)
        async with self.sessions.begin() as session:
            run = e.AgentRun(
                workflow="quality_judge",
                workflow_version="judge-runner-v1",
                status=RunStatus.RUNNING,
                budget={
                    "cost_limit": str(ceilings.max_estimated_cost),
                    "token_limit": ceilings.max_input_tokens + ceilings.max_output_tokens,
                },
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            ids = list(
                await session.scalars(
                    select(q.JudgeRow.id)
                    .where(q.JudgeRow.status == "pending")
                    .order_by(q.JudgeRow.created_at)
                    .limit(limit)
                )
            )
        queue = asyncio.Queue[UUID]()
        for id in ids:
            queue.put_nowait(id)
        results: list[dict[str, Any]] = []

        async def worker() -> None:
            while not queue.empty():
                id = queue.get_nowait()
                if budget.exhausted:
                    break
                result = await self.one(id, run_id, budget)
                results.append(result)

        await asyncio.gather(*(worker() for _ in range(min(concurrency, len(ids)))))
        async with self.sessions.begin() as session:
            run = await require(session, e.AgentRun, run_id, lock=True)
            run.status = (
                RunStatus.PARTIAL
                if budget.exhausted or any(r["status"] != "completed" for r in results)
                else RunStatus.COMPLETED
            )
            run.finished_at = e.utcnow()
            run.consumed_usage = Usage(
                input_tokens=budget.usage.input_tokens,
                output_tokens=budget.usage.output_tokens,
                estimated_cost=budget.usage.estimated_cost,
                budget_reserved_usd=budget.usage.budget_reserved_usd,
            ).model_dump(mode="json")
        return {"run_id": run_id, "results": results, "usage": budget.usage.model_dump(mode="json")}

    async def one(self, id: UUID, run_id: UUID, budget: SharedEvalBudget) -> dict[str, Any]:
        operations: list[OperationSnapshot] = []
        gateway = ModelGateway(
            self.gateway.registry,
            self.gateway.policy,
            {
                name: ScopedProvider(
                    adapter, budget, RunLimits(), operations, FaultController(FaultPlan())
                )
                for name, adapter in self.gateway.adapters.items()
            },
            self.gateway.prompts,
            controller=self.gateway.controller,
            durable=self.gateway.durable,
        )
        context: ModelRequestContext | None = None
        try:
            async with self.sessions.begin() as session:
                row = await require(session, q.JudgeRow, id, lock=True)
                if row.status != "pending":
                    return {"id": id, "status": row.status}
                sampling = await require(session, q.SamplingRow, row.sampling_id)
                decision = SamplingDecision.model_validate(sampling.data)
                spec = JudgeSpec.model_validate(row.spec)
                if (
                    spec.prompt_hash != PROMPT.prompt_hash
                    or spec.model_policy_version != POLICY.version
                ):
                    row.status = "failed"
                    row.reason_code = "judge_config_incompatible"
                    return {"id": id, "status": row.status}
                invocation = await resolve_subject(session, decision.subject)
                data = invocation.data
                row.status = "running"
                row.started_at = e.utcnow()
                step = e.AgentStep(run_id=run_id, sequence=1, node="quality_judgement")
                # Step sequence is allocated under the authoritative run lock.
                await require(session, e.AgentRun, run_id, lock=True)
                from sqlalchemy import func

                step.sequence = 1 + (
                    await session.scalar(
                        select(func.max(e.AgentStep.sequence)).where(e.AgentStep.run_id == run_id)
                    )
                    or 0
                )
                session.add(step)
                await session.flush()
                inputs = model_view(
                    {
                        "subject": {"input": data["input_snapshot"], "output": data["output"]},
                        "rubric": {"version": spec.rubric_version, "criteria": spec.criteria},
                        "evidence": ["input", "output"],
                    }
                )
                context = ModelRequestContext(
                    budget_owner_refs=[run_id],
                    task_type="quality_judgement",
                    workflow="quality_judge",
                    workflow_version="judge-runner-v1",
                    output_schema=JudgeOutput,
                    privacy_class=PrivacyClass.SYNTHETIC,
                    traffic_class="evaluation",
                    budget_remaining=Budget(cost_limit=ceilings_cost(budget)),
                    max_output_tokens=3000,
                    **PROMPT.metadata,
                )
                try:
                    context = await gateway.prepare(context, PROMPT.task(inputs))
                    if gateway.durable and context.selection:
                        gateway.durable.watch(session, context.selection.attempt_id)
                    await gateway.admit_adapter(context, PROMPT.task(inputs))
                except ModelGatewayError as exc:
                    row.status = "failed"
                    row.reason_code = exc.code
                    row.finished_at = e.utcnow()
                    step.status, step.reason_code = CallStatus.FAILED, exc.code
                    step.versions = {"control_decisions": exc.control_decisions}
                    return {"id": id, "status": "failed", "reason_code": exc.code}
                candidate = gateway.candidate(context)
                call = e.ModelCall(
                    step_id=step.id,
                    task_type="quality_judgement",
                    provider=candidate.provider,
                    model=candidate.model,
                    logical_operation_id=context.logical_operation_id,
                    status=CallStatus.RUNNING,
                )
                session.add(call)
                await session.flush()
                call_id = call.id
                step_id = step.id
                row.model_call_id = call_id
        except BaseException:
            if context is not None:
                gateway.cancel_prepared(context)
            raise
        assert context is not None
        started = time.monotonic()
        error = None
        output = None
        result = None
        failure_usage = None
        token = EVALUATION_ORIGIN.set(True)
        try:
            result = await gateway.generate(context, PROMPT.task(inputs))
            output = JudgeOutput.model_validate(result.validated_output)
            validate_judge(output, spec, {"input", "output"})
        except ModelGatewayError as exc:
            error = exc.code
            failure_usage = exc.usage
        finally:
            EVALUATION_ORIGIN.reset(token)
        async with self.sessions.begin() as session:
            if gateway.durable and context.selection:
                gateway.durable.watch(session, context.selection.attempt_id)
            row = await require(session, q.JudgeRow, id, lock=True)
            call = await require(session, e.ModelCall, call_id)
            step = await require(session, e.AgentStep, step_id)
            if error and not gateway.was_dispatched(context):
                gateway.cancel_prepared(context)
                row.model_call_id = None
                await session.flush()
                await session.delete(call)
                step.status, step.reason_code = CallStatus.FAILED, error
                step.versions = gateway.trace_metadata(context, PROMPT.task(inputs)).model_dump(
                    mode="json"
                )
                row.status, row.reason_code = "failed", error
                row.finished_at = e.utcnow()
                return {"id": id, "status": "failed", "reason_code": error}
            call.status = step.status = CallStatus.FAILED if error else CallStatus.SUCCEEDED
            call.error_code = error
            call.latency_ms = int((time.monotonic() - started) * 1000)
            call.versions = gateway.trace_metadata(context, PROMPT.task(inputs)).model_dump(
                mode="json"
            )
            observed = result.usage if result else failure_usage
            if operations:
                observed = Usage.model_validate(operations[-1].provenance["usage"])
            call.usage = (observed or Usage()).model_dump(mode="json")
            call.provider = call.versions["provider"]
            call.model = call.versions["model"]
            call.estimated_cost = result.estimated_cost if result else None
            call.schema_validation_state = "valid" if output else "invalid"
            row.status = "failed" if error else "completed"
            row.reason_code = error
            row.finished_at = e.utcnow()
            if output is not None and not error:
                row.result = output.model_dump(mode="json")
                row.severity = severity(output)
                if row.severity in {"minor_issue", "major_issue"}:
                    invocation = await resolve_subject(session, decision.subject)
                    await capture(
                        session,
                        payload_from_invocation(decision.subject, invocation),
                        "judge_" + row.severity,
                        row.id,
                    )
        return {"id": id, "status": "failed" if error else "completed", "reason_code": error}


def ceilings_cost(budget: SharedEvalBudget) -> Any:
    return budget.ledger.limits.max_estimated_cost - budget.usage.budget_consumed_usd
