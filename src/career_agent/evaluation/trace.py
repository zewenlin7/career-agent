"""Persist replay model-call metadata while keeping bodies in private invocation snapshots."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.domain.rules import CallStatus, RunStatus
from career_agent.evaluation.contracts import OperationSnapshot
from career_agent.infrastructure import entities as e
from career_agent.runtime.contracts import Usage, VersionMetadata


async def persist_operation(session: AsyncSession, op: OperationSnapshot) -> UUID | None:
    if op.kind != "model_task":
        return None
    run_id = op.parent_run_id or uuid4()
    step_id = op.parent_step_id or uuid4()
    raw_call_id = op.provenance.get("attempt_model_call_id")
    call_id = UUID(raw_call_id) if raw_call_id else op.accepted_model_call_id or uuid4()
    if await session.get(e.AgentRun, run_id) is None:
        session.add(
            e.AgentRun(
                id=run_id,
                workflow="eval_replay",
                workflow_version="eval-v1",
                status=RunStatus.COMPLETED,
            )
        )
        await session.flush()
    versions = VersionMetadata.model_validate(
        {k: v for k, v in op.provenance.items() if k in VersionMetadata.model_fields}
    )
    versions.injected_fault = op.injected_fault
    versions.execution_origin = "evaluation"
    if await session.get(e.AgentStep, step_id) is None:
        from sqlalchemy import func, select

        sequence = 1 + (
            await session.scalar(
                select(func.max(e.AgentStep.sequence)).where(e.AgentStep.run_id == run_id)
            )
            or 0
        )
        session.add(
            e.AgentStep(
                id=step_id,
                run_id=run_id,
                sequence=sequence,
                node=op.name,
                status=CallStatus.FAILED if op.reason_codes else CallStatus.SUCCEEDED,
                versions=versions.model_dump(mode="json"),
            )
        )
        await session.flush()
    usage = Usage.model_validate(op.provenance.get("usage", {}))
    call = e.ModelCall(
        id=call_id,
        step_id=step_id,
        task_type=op.name,
        provider=op.provenance["provider"],
        model=op.provenance["model"],
        versions=versions.model_dump(mode="json"),
        usage=usage.model_dump(mode="json"),
        status=CallStatus.FAILED if op.reason_codes else CallStatus.SUCCEEDED,
        logical_operation_id=op.logical_operation_id,
        attempts=op.provenance.get("attempt", 1),
        estimated_cost=usage.estimated_cost,
        latency_ms=op.provenance.get("latency_ms"),
        finish_reason=op.provenance.get("finish_reason"),
        error_code=op.reason_codes[0] if op.reason_codes else None,
    )
    session.add(call)
    await session.flush()
    op.parent_run_id = run_id
    op.parent_step_id = step_id
    op.accepted_model_call_id = call_id if not op.reason_codes else None
    return call_id
