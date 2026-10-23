"""Read-only attention index: related records are not interchangeable incidents."""

from typing import Any, Literal

from sqlalchemy import Integer, String, cast, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.infrastructure import entities as e
from career_agent.ops.entities import AttemptJournal, RecoveryIncident
from career_agent.product.contracts import Page
from career_agent.product.entities import ProductOperation

AttentionSource = Literal["product_operation", "run", "attempt", "recovery_incident"]


async def attention(
    session: AsyncSession,
    scope: str,
    source: AttentionSource | None,
    status: str | None,
    limit: int,
    offset: int,
    include_resolved: bool,
) -> Page[dict[str, Any]]:
    def projection(model: Any, kind: str, reason: Any, run: Any, attempt: Any) -> Any:
        return select(
            literal(kind).label("source"),
            model.id.label("id"),
            model.created_at,
            cast(model.status, String).label("status"),
            reason.label("reason_code"),
            run.label("run_id"),
            attempt.label("attempt_id"),
            (model.revision if model is RecoveryIncident else cast(literal(None), Integer)).label(
                "revision"
            ),
            (model.resolution if model is RecoveryIncident else cast(literal(None), String)).label(
                "resolution"
            ),
        )

    # Scope applies only to controller-owned records. Product operations and runs are
    # single-user application-wide; explicit IDs link related entries without merging them.
    empty = cast(literal(None), String)
    operations = projection(
        ProductOperation,
        "product_operation",
        ProductOperation.reason,
        cast(ProductOperation.run_id, String),
        empty,
    ).where(
        ProductOperation.status.in_(
            ["failure", "partial", "recovery_required", "needs_input", "decision_required"]
        )
    )
    runs = projection(
        e.AgentRun, "run", e.AgentRun.stop_reason, cast(e.AgentRun.id, String), empty
    ).where(
        e.AgentRun.status.in_(
            [
                "failed",
                "partial",
                "interrupted",
                "waiting_input",
                "waiting_decision",
                "needs_input",
                "decision_required",
            ]
        )
    )
    attempts = projection(
        AttemptJournal,
        "attempt",
        AttemptJournal.data["provider_outcome"].astext,
        empty,
        cast(AttemptJournal.attempt_id, String),
    ).where(
        AttemptJournal.scope == scope,
        AttemptJournal.status.in_(["unknown", "settled"]),
    )
    incidents = projection(
        RecoveryIncident,
        "recovery_incident",
        RecoveryIncident.reason,
        empty,
        cast(RecoveryIncident.attempt_id, String),
    ).where(RecoveryIncident.scope == scope)
    if not include_resolved:
        incidents = incidents.where(RecoveryIncident.status == "open")
    combined = union_all(operations, runs, attempts, incidents).subquery()
    stmt = select(combined).order_by(combined.c.created_at.desc(), combined.c.source, combined.c.id)
    if source is not None:
        stmt = stmt.where(combined.c.source == source)
    if status is not None:
        stmt = stmt.where(combined.c.status == status)
    found = list((await session.execute(stmt.limit(limit + 1).offset(offset))).mappings())
    items = []
    for row in found[:limit]:
        item = dict(row)
        kind, state = item["source"], item["status"]
        if kind == "recovery_incident":
            category = "recovery_incident"
        elif kind == "attempt":
            category = "unknown_outcome" if state == "unknown" else "business_commit_unconfirmed"
        elif state == "recovery_required":
            category = "recovery_required"
        elif state in {"waiting_input", "waiting_decision", "needs_input", "decision_required"}:
            category = "user_input_or_decision"
        else:
            category = "execution_failure"  # Not automatically a recovery incident.
        item.update(category=category, allowed_actions=["inspect"])
        # Reconciliation writes retain their existing revision/idempotency requirements.
        if kind == "recovery_incident" and state == "open":
            item["allowed_actions"] = ["inspect", "reconcile"]
        items.append(item)
    return Page(items=items, limit=limit, offset=offset, has_more=len(found) > limit)
