"""Exact review identity, frozen content comparisons and safe failed-target disposition."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.domain.rules import CallStatus, DomainError
from career_agent.infrastructure import entities as e
from career_agent.interview.calls import AcceptedCall, validate_accepted_call
from career_agent.interview.contracts import SourceSnapshot
from career_agent.interview.ownership import mock_owner


async def owner(session: AsyncSession, row: e.DebriefRun) -> UUID | None:
    source = row.snapshot
    id = UUID(source["interview_id"])
    if source["source_kind"] == "actual":
        actual = await session.get(e.InterviewSession, id)
        return actual.application_id if actual else None
    mock = await session.get(e.MockInterviewSession, id)
    return await mock_owner(session, mock) if mock else None


async def source_name(session: AsyncSession, snapshot: dict[str, Any]) -> str:
    id = UUID(snapshot["interview_id"])
    if snapshot["source_kind"] == "mock":
        from zoneinfo import ZoneInfo

        mock = await session.get(e.MockInterviewSession, id)
        if mock is None:
            return "模拟面试"
        if mock.display_number:
            return f"模拟面试 · 第 {mock.display_number} 场"
        saved = mock.created_at.astimezone(ZoneInfo("Asia/Shanghai"))
        return f"模拟面试 · {saved:%Y-%m-%d %H:%M}"
    actual = await session.get(e.InterviewSession, id)
    if actual is None:
        return "真实面试"
    app = await session.get(e.Application, actual.application_id)
    job = await session.get(e.JobPosting, app.job_id) if app else None
    company = await session.get(e.Company, job.company_id) if job else None
    jd = (
        await session.scalar(
            select(e.JobRevision)
            .where(e.JobRevision.job_id == job.id)
            .order_by(e.JobRevision.revision.desc())
            .limit(1)
        )
        if job
        else None
    )
    name = actual.round_name.strip()
    if not name or name.isdigit():
        kind = {"technical": "技术", "hr": "人力资源", "mixed": "综合", "other": "其他"}.get(
            actual.interview_type or "", ""
        )
        name = " · ".join(
            x
            for x in [
                company.name if company else "",
                jd.title if jd else "",
                f"第{actual.round_number}轮"
                if actual.round_number
                else (f"记录 {name}" if name else "面试记录"),
                kind,
            ]
            if x
        )
    return "真实面试 · " + name


def content(entries: list[dict[str, Any]], notes: list[dict[str, Any]]) -> Any:
    # Presentation anchors, timestamps and record metadata do not change answer content.
    return (
        [
            {k: x.get(k) for k in ("entry_id", "kind", "primary_entry_id", "question", "answer")}
            for x in sorted(entries, key=lambda x: x["order"])
        ],
        [x["text"] for x in notes],
    )


async def source_changed(session: AsyncSession, snapshot: dict[str, Any]) -> bool | None:
    try:
        if snapshot["source_kind"] == "mock":
            mock = await session.get(e.MockInterviewSession, UUID(snapshot["interview_id"]))
            if mock is None:
                return None
            turns = list(
                await session.scalars(
                    select(e.MockInterviewTurn)
                    .where(e.MockInterviewTurn.session_id == mock.id)
                    .order_by(e.MockInterviewTurn.sequence)
                )
            )
            current = [
                {
                    "entry_id": str(t.id),
                    "order": t.sequence,
                    "answer": t.answer,
                    **{k: t.data[k] for k in ("kind", "primary_entry_id", "question")},
                }
                for t in turns
            ]
            notes: list[dict[str, Any]] = []
        else:
            actual = await session.get(e.InterviewSession, UUID(snapshot["interview_id"]))
            if actual is None:
                return None
            current, notes = actual.entries, actual.notes
        return bool(content(current, notes) != content(snapshot["entries"], snapshot["notes"]))
    except (KeyError, TypeError, ValueError):
        return None


async def disposition(
    session: AsyncSession, run: e.DebriefRun, artifact: e.DebriefArtifact
) -> tuple[str, AcceptedCall | None]:
    from career_agent.evaluation.contracts import OperationSnapshot
    from career_agent.evaluation.entities import InvocationRow
    from career_agent.interview.compact import (
        CompactGroup,
        CompactOverall,
        CompactOverallV3,
        canonical,
    )
    from career_agent.interview.debrief import inputs_for, task_type
    from career_agent.interview.prompts import PROMPTS
    from career_agent.interview.validation import validate_evaluation

    calls = (
        list(
            await session.scalars(
                select(e.ModelCall)
                .where(e.ModelCall.logical_operation_id == artifact.logical_operation_id)
                .order_by(e.ModelCall.attempts.desc())
            )
        )
        if artifact.logical_operation_id
        else []
    )
    source = SourceSnapshot.model_validate(run.snapshot)
    for call in calls:
        record = await session.scalar(
            select(InvocationRow).where(InvocationRow.model_call_id == call.id)
        )
        if record is None or not record.data.get("accepted_model_call_id"):
            continue
        snap = OperationSnapshot.model_validate(record.data)
        spec = PROMPTS[task_type(artifact.kind)]
        output_version = snap.provenance.get("output_schema_version")
        legacy = (
            artifact.kind == "overall" and output_version == "interview_overall_debrief-output-v2"
        )
        expected = inputs_for(source, artifact.group_ref, legacy_overall=legacy)
        saved = dict(snap.input_snapshot)
        saved.pop("repair_reason", None)
        if (
            saved != expected
            or (output_version != spec.output_schema_version and not legacy)
            or snap.provenance.get("input_schema_version")
            != ("interview_overall_debrief-input-v4" if legacy else spec.input_schema_version)
        ):
            return "incompatible", None
        parsed = (
            CompactGroup
            if artifact.kind == "group"
            else CompactOverall
            if legacy
            else CompactOverallV3
        ).model_validate(snap.output)
        validate_evaluation(
            canonical(parsed, source, artifact.group_ref), source, artifact.group_ref
        )
        assert artifact.logical_operation_id is not None
        accepted = AcceptedCall(parsed, call.id, artifact.logical_operation_id)
        await validate_accepted_call(session, accepted, run.run_id, artifact.logical_operation_id)
        return "recoverable", accepted
    if calls:
        latest = calls[0]
        if (
            latest.status != CallStatus.FAILED
            or latest.error_code
            in {
                "execution_outcome_unknown",
                "recovery_decision_required",
                "provider_timeout",
                "execution_cancelled",
            }
            or latest.usage.get("measurement") == "unknown"
        ):
            return "unknown", None
        if latest.retryable or latest.error_code in {
            "structured_output_invalid",
            "output_validation_failed",
            "invalid_evidence_reference",
        }:
            return "retryable", None
        return "blocked", None
    if artifact.error_code in {
        "call_budget_exhausted",
        "budget_exhausted",
        "insufficient_token_budget",
        "session_budget_exhausted",
        "context_too_large",
        "debrief_input_too_large",
        "operation_attempt_limit",
        "model_attempt_limit",
    }:
        # A recorded pre-dispatch rejection is a known limit, not an unknown provider outcome.
        return "blocked", None
    if (
        artifact.status == "pending"
        or artifact.error_code == "execution_cancelled"
        or artifact.attempts == 0
    ):
        return "retryable", None
    return "unknown", None


async def remove(session: AsyncSession, id: UUID) -> dict[str, Any]:
    from career_agent.interview.execution import available
    from career_agent.product.result_lifecycle import consumers

    if not await available(session, id):
        raise DomainError("debrief_running", 409)
    row = await require(session, e.DebriefRun, id)
    application = await owner(session, row)
    if application is None:
        raise DomainError("historical_reference_unavailable", 409)
    await require(session, e.Application, application, lock=True)
    # Serialize a whole history chain before locking individual generations. Otherwise a
    # child deletion can hold Application while a root deletion holds the root row.
    await session.refresh(row, with_for_update=True)
    if row.deleted_at:
        return {"deleted": True, "used_by": []}
    if row.status == "running":
        raise DomainError("debrief_running", 409)
    artifacts = list(
        await session.scalars(select(e.DebriefArtifact).where(e.DebriefArtifact.debrief_id == id))
    )
    # Audit rows and the generation chain are not downstream business inputs.
    used = await consumers(session, {str(id), *(str(a.id) for a in artifacts)}, {row.run_id}, set())
    if used:
        return {"deleted": False, "used_by": used}
    row.deleted_at = e.utcnow()
    root = await require(session, e.DebriefRun, row.root_run_id or row.id, lock=True)
    if (root.selected_run_id or root.id) == id:
        root.selected_run_id = await session.scalar(
            select(e.DebriefRun.id)
            .where(
                (e.DebriefRun.root_run_id == root.id) | (e.DebriefRun.id == root.id),
                e.DebriefRun.id != id,
                e.DebriefRun.deleted_at.is_(None),
                e.DebriefRun.status.in_(["completed", "partial"]),
            )
            .order_by(e.DebriefRun.created_at.desc(), e.DebriefRun.id)
            .limit(1)
        )
    return {"deleted": True, "used_by": []}
