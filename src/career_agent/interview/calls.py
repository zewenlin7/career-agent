"""Shared model execution with per-owner row-locked reservation and isolated DB sessions."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import require
from career_agent.domain.rules import CallStatus, ObservationStatus
from career_agent.infrastructure import entities as e
from career_agent.interview.contracts import InterviewLimits, InterviewUsage
from career_agent.interview.policy import CallPolicy
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, PrivacyClass
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.budget import BudgetLedger, input_bound
from career_agent.runtime.contracts import Budget, OutputDiagnostic, Usage

OwnerKind = Literal["mock", "debrief"]
Owner = e.MockInterviewSession | e.DebriefRun


@dataclass(frozen=True)
class AcceptedCall:
    output: BaseModel
    model_call_id: UUID
    logical_operation_id: UUID


async def owner(session: AsyncSession, kind: OwnerKind, id: UUID, *, lock: bool = True) -> Owner:
    if kind == "mock":
        return await require(session, e.MockInterviewSession, id, lock=lock)
    return await require(session, e.DebriefRun, id, lock=lock)


def usage_projection(usage: InterviewUsage) -> dict[str, Any]:
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=None if usage.cached_unknown_calls else usage.cached_tokens,
        cache_write_tokens=None if usage.cache_write_unknown_calls else usage.cache_write_tokens,
        reasoning_tokens=None if usage.reasoning_unknown_calls else usage.reasoning_tokens,
        estimated_cost=usage.estimated_cost,
        budget_reserved_usd=usage.budget_reserved_usd,
        reserved_input_tokens=usage.reserved_input_tokens,
        reserved_output_tokens=usage.reserved_output_tokens,
        measurement="unknown" if usage.unknown_usage_attempts else "reported",
    ).model_dump(mode="json")


class InterviewCalls:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], gateway: ModelGateway) -> None:
        self.sessions, self.gateway = sessions, gateway

    def request(self, task: str, mode: str, policy: CallPolicy) -> ModelRequestContext:
        prompt = self.gateway.prompts.resolve(task)
        return ModelRequestContext(
            task_type=task,
            workflow="mock_interview"
            if task == "mock_interview_turn_generation"
            else "interview_debrief",
            workflow_version="interview-loop-v1",
            output_schema=prompt.output_schema,
            max_output_tokens=policy.max_output_tokens,
            privacy_class=PrivacyClass.SYNTHETIC if mode == "fixture" else PrivacyClass.PRIVATE,
            budget_remaining=Budget(cost_limit=policy.max_estimated_cost),
            **prompt.metadata,
        )

    def preflight(self, task: str, mode: str, inputs: dict[str, Any], policy: CallPolicy) -> int:
        context = self.request(task, mode, policy)
        spec = self.gateway.prompts.resolve(task).task(inputs)
        self.gateway.trace_metadata(context, spec)
        try:
            bound = input_bound(context, spec)
        except ModelGatewayError:
            raise ModelGatewayError(
                "debrief_input_too_large"
                if task != "mock_interview_turn_generation"
                else "mock_input_too_large"
            ) from None
        if bound > policy.max_input_tokens:
            raise ModelGatewayError(
                "debrief_input_too_large"
                if task != "mock_interview_turn_generation"
                else "mock_input_too_large"
            )
        candidate = self.gateway.policy.select(context, self.gateway.registry)
        cost = (
            bound * candidate.input_cost_per_million
            + policy.max_output_tokens * candidate.output_cost_per_million
        ) / 1000000
        if cost > policy.max_estimated_cost:
            raise ModelGatewayError("call_budget_exhausted")
        return bound

    async def generate(
        self,
        kind: OwnerKind,
        id: UUID,
        task: str,
        inputs: dict[str, Any],
        policy: CallPolicy,
        validate: Callable[[BaseModel], None],
        *,
        logical_operation_id: UUID,
        retry_reason: str | None = None,
        repair_reason: str | None = None,
    ) -> AcceptedCall:
        async with self.sessions.begin() as session:
            row = await owner(session, kind, id)
            attempt = 1 + (
                await session.scalar(
                    select(func.max(e.ModelCall.attempts)).where(
                        e.ModelCall.logical_operation_id == logical_operation_id
                    )
                )
                or 0
            )
            if attempt > 1 and not retry_reason and not repair_reason:
                retry_reason = "explicit_generation_retry"
            bound = self.preflight(task, row.mode, inputs, policy)
            context = self.request(task, row.mode, policy)
            spec = self.gateway.prompts.resolve(task).task(inputs)
            candidate = self.gateway.policy.select(context, self.gateway.registry)
            usage = InterviewUsage.model_validate(row.usage)
            limits = InterviewLimits.model_validate(row.limits)
            if (
                usage.active_seconds + usage.reserved_seconds + policy.max_seconds
                > limits.max_active_seconds
            ):
                raise ModelGatewayError("active_time_exhausted")
            reservation = BudgetLedger(limits, usage).reserve_model(
                candidate, bound, policy.max_output_tokens
            )
            usage.reserved_seconds += policy.max_seconds
            row.usage = usage.model_dump(mode="json")
            versions = self.gateway.trace_metadata(context, spec).model_copy(
                update={"retry_reason": retry_reason, "repair_reason": repair_reason}
            )
            step = e.AgentStep(
                run_id=row.run_id,
                sequence=usage.model_calls,
                node=task,
                attempt=attempt,
                status=CallStatus.RUNNING,
                versions=versions.model_dump(mode="json"),
            )
            session.add(step)
            await session.flush()
            call = e.ModelCall(
                step_id=step.id,
                logical_operation_id=logical_operation_id,
                task_type=task,
                provider=candidate.provider,
                model=candidate.model,
                versions=versions.model_dump(mode="json"),
                usage=reservation.model_dump(mode="json"),
                attempts=attempt,
                status=CallStatus.RUNNING,
            )
            session.add(call)
            run = await require(session, e.AgentRun, row.run_id)
            run.consumed_usage = usage_projection(usage)
            if run.started_at is None:
                run.started_at = e.utcnow()
            await session.flush()
            call_id, step_id = call.id, step.id
        start = time.monotonic()
        actual: Usage | None = None
        failure: ModelGatewayError | None = None
        result = None
        cancelled = False
        try:
            result = await asyncio.wait_for(
                self.gateway.generate(context, spec), timeout=policy.max_seconds
            )
            actual = result.usage
            validate(result.validated_output)
        except asyncio.CancelledError:
            cancelled = True
            failure = ModelGatewayError("execution_cancelled")
        except TimeoutError:
            failure = ModelGatewayError(
                "provider_timeout",
                retryable=True,
                diagnostic=OutputDiagnostic(
                    failure_kind="provider_timeout",
                    request_timeout_seconds=policy.max_seconds,
                    timeout_policy_version="interview-budget-v1",
                ),
            )
        except ModelGatewayError as exc:
            failure = exc
            actual = actual or exc.usage
            if result is not None and failure.diagnostic is None:
                failure.diagnostic = OutputDiagnostic(failure_kind="output_guardrail_failed")
        except Exception:
            failure = ModelGatewayError("interview_provider_error")
        elapsed = time.monotonic() - start
        async with self.sessions.begin() as session:
            row = await owner(session, kind, id)
            usage = InterviewUsage.model_validate(row.usage)
            settled = BudgetLedger(InterviewLimits.model_validate(row.limits), usage).settle(
                reservation, actual
            )
            usage.reserved_seconds = max(0, usage.reserved_seconds - policy.max_seconds)
            usage.active_seconds += elapsed
            for field, unknown in [
                ("cached_tokens", "cached_unknown_calls"),
                ("cache_write_tokens", "cache_write_unknown_calls"),
                ("reasoning_tokens", "reasoning_unknown_calls"),
            ]:
                value = getattr(settled, field)
                if value is None:
                    setattr(usage, unknown, getattr(usage, unknown) + 1)
                else:
                    setattr(usage, field, getattr(usage, field) + value)
            row.usage = usage.model_dump(mode="json")
            call = await require(session, e.ModelCall, call_id)
            step = await require(session, e.AgentStep, step_id)
            call.usage = settled.model_dump(mode="json")
            call.estimated_cost = settled.estimated_cost
            call.latency_ms = step.latency_ms = int(elapsed * 1000)
            call.finish_reason = result.finish_reason if result else None
            diagnostic = (
                failure.diagnostic
                if failure
                else result.versions.output_diagnostic
                if result
                else None
            )
            if diagnostic:
                call.versions = {
                    **call.versions,
                    "output_diagnostic": diagnostic.model_dump(mode="json"),
                }
            call.status = step.status = CallStatus.FAILED if failure else CallStatus.SUCCEEDED
            call.error_code = step.reason_code = failure.code if failure else None
            from career_agent.evaluation.recording import record_model

            await record_model(
                session,
                call_id=call.id,
                run_id=row.run_id,
                step_id=step.id,
                context=context,
                task=spec,
                output=result.validated_output.model_dump(mode="json")
                if result and not failure
                else None,
                versions=call.versions,
                operation_id=logical_operation_id,
                source=row.snapshot if isinstance(row, e.DebriefRun) else row.context,
                reason=failure.code if failure else None,
            )
            call.retryable = failure.retryable if failure else False
            call.schema_validation_state = "valid" if result else "not_validated"
            run = await require(session, e.AgentRun, row.run_id)
            run.consumed_usage = usage_projection(usage)
            session.add(
                e.Observation(
                    model_call_id=call.id,
                    status=ObservationStatus.ERROR if failure else ObservationStatus.OK,
                    error_code=call.error_code,
                    retryable=call.retryable,
                )
            )
        if cancelled:
            raise asyncio.CancelledError()
        if failure:
            raise failure
        assert result is not None
        return AcceptedCall(result.validated_output, call_id, logical_operation_id)


async def validate_accepted_call(
    session: AsyncSession, accepted: AcceptedCall, run_id: UUID, operation_id: UUID | None
) -> None:
    """Artifact writes must bind a successful attempt from their own run and operation."""
    from career_agent.domain.rules import DomainError

    call = await require(session, e.ModelCall, accepted.model_call_id)
    step = await require(session, e.AgentStep, call.step_id)
    if (
        operation_id is None
        or accepted.logical_operation_id != operation_id
        or call.logical_operation_id != operation_id
        or call.status != CallStatus.SUCCEEDED
        or step.run_id != run_id
    ):
        raise DomainError("model_call_provenance_mismatch")
