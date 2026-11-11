"""Body-free, read-only task status for the persistent Product shell."""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.interview.execution import available
from career_agent.models.contracts import ModelGatewayError
from career_agent.product.entities import ProductDraft, ProductOperation
from career_agent.product.results import package_view

Family = Literal["operations", "product-drafts", "mock-interviews", "interview-debriefs"]


async def _status(
    session: AsyncSession, family: Family, id: UUID, request_id: UUID | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {"id": str(id), "state": "unknown", "reason": None, "selection": {}}
    if family == "operations":
        op = await require(session, ProductOperation, id)
        result.update(state=op.status, reason=op.reason)
        if op.status == "running":
            free = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 4302))"),
                {"key": str(id)},
            )
            if free:
                result["state"] = "unknown"
        if op.status == "success":
            if op.research_report_id:
                result["selection"] = {"research": str(op.research_report_id)}
            elif op.package_id:
                view = await package_view(session, op.package_id)
                targets = [r for r in view.results if r.status == "success"]
                if len(targets) == 1:
                    result["selection"] = {"result": str(targets[0].target_artifact_id)}
                    if targets[0].reused:
                        result["state"] = "reused"
    elif family == "product-drafts":
        draft = await require(session, ProductDraft, id)
        result.update(state=draft.status, reason=draft.reason)
        if draft.status == "completed":
            result["state"] = "success" if draft.adopted else "awaiting_save"
            saved = draft.adopted or {}
            if saved.get("target_artifact_id"):
                result["selection"] = {"result": saved["target_artifact_id"]}
            elif saved.get("resume_revision_id"):
                result["selection"] = {"revision": saved["resume_revision_id"]}
            elif saved.get("resume_workspace_id"):
                result["selection"] = {"workspace": saved["resume_workspace_id"]}
        if draft.status == "running":
            free = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 4308))"),
                {"key": str(id)},
            )
            if free:
                result["state"] = "unknown"
    elif family == "mock-interviews":
        mock = await require(session, e.MockInterviewSession, id)
        if request_id is not None:
            receipt = await session.scalar(
                select(e.MockRequestReceipt).where(
                    e.MockRequestReceipt.session_id == id,
                    e.MockRequestReceipt.request_id == request_id,
                )
            )
            outcome = receipt.outcome if receipt else None
            if (
                outcome
                and outcome.get("state") in {"running", "unknown"}
                and outcome.get("logical_operation_id")
            ):
                recovered = await session.scalar(
                    select(e.MockInterviewTurn).where(
                        e.MockInterviewTurn.session_id == id,
                        e.MockInterviewTurn.logical_operation_id
                        == UUID(outcome["logical_operation_id"]),
                    )
                )
                if recovered is not None:
                    outcome = {
                        **outcome,
                        "state": "success",
                        "reason": None,
                        "question_id": str(recovered.id),
                    }
            if outcome and (
                outcome.get("state") in {"running", "unknown"}
                or outcome.get("accepted_model_call_id")
            ):
                # Finish has no turn. Only an exact committed decision receipt proves recovery.
                key = (
                    "accepted_model_call_id"
                    if outcome.get("accepted_model_call_id")
                    else "logical_operation_id"
                )
                if outcome.get(key):
                    finished = await session.scalar(
                        select(e.MockRequestReceipt)
                        .where(
                            e.MockRequestReceipt.session_id == id,
                            e.MockRequestReceipt.outcome["state"].astext == "success",
                            e.MockRequestReceipt.outcome["decision"]["action"].astext == "finish",
                            e.MockRequestReceipt.outcome[key].astext == outcome[key],
                        )
                        .order_by(e.MockRequestReceipt.created_at.desc())
                        .limit(1)
                    )
                    if finished is not None and finished.outcome is not None:
                        outcome = {
                            **outcome,
                            "state": "success",
                            "reason": None,
                            "decision": finished.outcome["decision"],
                            "question_id": None,
                            "completion_type": finished.outcome.get("completion_type"),
                        }
            if outcome and outcome.get("state") == "running" and await available(session, id):
                outcome = {**outcome, "state": "unknown", "reason": "execution_outcome_unknown"}
            # A save failure can later publish the very same accepted output. Read that
            # exact relationship; a later paid retry must not erase a different failure.
            if outcome and outcome.get("accepted_model_call_id"):
                turn = await session.scalar(
                    select(e.MockInterviewTurn).where(
                        e.MockInterviewTurn.session_id == id,
                        e.MockInterviewTurn.accepted_model_call_id
                        == UUID(outcome["accepted_model_call_id"]),
                    )
                )
                if turn is not None:
                    outcome = {
                        **outcome,
                        "state": "success",
                        "reason": None,
                        "question_id": str(turn.id),
                    }
            return {
                **result,
                **(
                    outcome
                    or {
                        "state": "unknown" if receipt else "pending",
                        "revision": mock.revision,
                    }
                ),
                "selection": {
                    "session": str(id),
                    **(
                        {"question": outcome["question_id"]}
                        if outcome and outcome.get("question_id")
                        else {}
                    ),
                },
            }
        orphaned = mock.generation_active and await available(session, id)
        result.update(
            state="running"
            if mock.generation_active and not orphaned
            else "unknown"
            if orphaned
            or mock.stop_reason in {"recovery_decision_required", "execution_outcome_unknown"}
            else "failure"
            if mock.stop_reason
            else "success"
            if mock.status in {"waiting_answer", "completed"}
            else "ready",
            reason="execution_outcome_unknown" if orphaned else mock.stop_reason,
            revision=mock.revision,
            selection={"session": str(id)},
        )
    else:
        debrief = await require(session, e.DebriefRun, id)
        if debrief.deleted_at:
            result.update(state="removed", reason="debrief_removed", selection={})
            return result
        result.update(
            state=debrief.status,
            selection={"debrief": str(id)},
            execution_revision=debrief.execution_revision,
        )
        if debrief.status == "running":
            if await available(session, id):
                result.update(state="unknown", reason="execution_outcome_unknown")
        if debrief.status in {"failed", "partial"}:
            from career_agent.interview.review_state import disposition

            artifacts = list(
                await session.scalars(
                    select(e.DebriefArtifact)
                    .where(
                        e.DebriefArtifact.debrief_id == id,
                        e.DebriefArtifact.status == "failed",
                    )
                    .order_by(e.DebriefArtifact.display_order)
                )
            )
            codes = [a.error_code for a in artifacts]
            recovery = []
            for artifact in artifacts:
                try:
                    recovery.append((await disposition(session, debrief, artifact))[0])
                except (ValueError, ModelGatewayError, DomainError):
                    # Match the exact view's conservative legacy-output projection.
                    recovery.append("incompatible")
            if codes:
                result["reason"] = next(
                    (code for code in codes if code != "execution_cancelled"), codes[0]
                )
                if "unknown" in recovery:
                    result["reason"] = "execution_outcome_unknown"
                    if debrief.status == "failed":
                        result["state"] = "unknown"
                elif "recoverable" in recovery:
                    result["reason"] = "artifact_save_failed"
                elif debrief.status == "failed" and all(
                    code == "execution_cancelled" for code in codes
                ):
                    result["state"] = "cancelled"

    result["state"] = {
        "completed": "success",
        "failed": "failure",
        "recovery_required": "unknown",
    }.get(result["state"], result["state"])
    if result["reason"] == "execution_cancelled" and result["state"] != "partial":
        result["state"] = "cancelled"
    return result


async def status(
    session: AsyncSession, family: Family, id: UUID, request_id: UUID | None = None
) -> dict[str, Any]:
    from career_agent.product.workspace_availability import task_workspace

    result = await _status(session, family, id, request_id)
    result["workspace"] = await task_workspace(session, family, id)
    return result
