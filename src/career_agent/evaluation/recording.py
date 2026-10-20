"""Private operation provenance. Operational ModelCall/AgentStep traces stay body-free."""

import asyncio
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.compatibility import execution_versions
from career_agent.evaluation.contracts import JudgeSamplingPolicy, OperationSnapshot, Subject
from career_agent.evaluation.identity import code_identity, digest
from career_agent.models.contracts import ModelRequestContext, TaskSpec

EVALUATION_ORIGIN: ContextVar[bool] = ContextVar("evaluation_origin", default=False)


async def record_model(
    session: AsyncSession,
    *,
    call_id: UUID,
    run_id: UUID,
    step_id: UUID,
    context: ModelRequestContext,
    task: TaskSpec,
    output: dict[str, Any] | None,
    versions: dict[str, Any],
    operation_id: UUID | None,
    source: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    from career_agent.application.services import require
    from career_agent.evaluation.entities import InvocationRow
    from career_agent.infrastructure import entities as e

    call = await require(session, e.ModelCall, call_id)
    data = OperationSnapshot(
        kind="model_task",
        name=context.task_type,
        version=context.prompt_version or "unknown",
        input_snapshot=task.inputs,
        input_hash=digest(task.inputs),
        output=output,
        parent_run_id=run_id,
        parent_step_id=step_id,
        accepted_model_call_id=call_id if output is not None and reason is None else None,
        logical_operation_id=operation_id,
        provenance={
            **versions,
            "control_contract": context.control_snapshot,
            **await asyncio.to_thread(code_identity),
            "execution_versions": execution_versions("resume_tailoring"),
            "external_observations": {
                "evidence": task.inputs.get("context", {}).get("evidence", [])
            },
            "source_snapshot": source or {},
            "attempt_model_call_id": str(call_id),
            "attempt": call.attempts,
            "usage": call.usage,
            "latency_ms": call.latency_ms,
            "finish_reason": call.finish_reason,
            "generation_parameters": {"max_output_tokens": context.max_output_tokens},
            "origin": "evaluation" if EVALUATION_ORIGIN.get() else "business",
        },
        reason_codes=[reason] if reason else [],
    )
    session.add(InvocationRow(model_call_id=call_id, data=data.model_dump(mode="json")))
    await session.flush()


async def bind_artifact(
    session: AsyncSession, call_id: UUID, artifact_id: UUID, policy: JudgeSamplingPolicy
) -> None:
    from career_agent.evaluation.entities import InvocationRow
    from career_agent.evaluation.monitoring import enqueue

    row = await session.scalar(select(InvocationRow).where(InvocationRow.model_call_id == call_id))
    if row is None:
        return  # Legacy operation without private snapshot: readable, not evaluable by guessing.
    if row.data.get("output_ref") is not None and row.data["output_ref"] != str(artifact_id):
        from career_agent.domain.rules import DomainError

        raise DomainError("immutable_invocation_artifact")
    row.data = {**row.data, "output_ref": str(artifact_id)}
    await session.flush()
    await enqueue(
        session,
        Subject(
            subject_id=artifact_id,
            accepted_model_call_id=call_id,
            operation_id=row.id,
            task_type=row.data["name"],
            origin="evaluation" if EVALUATION_ORIGIN.get() else "business",
        ),
        policy,
    )
