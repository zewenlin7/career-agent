"""Explicit local operator API. Never returns private invocation or provider payloads."""

import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from career_agent.domain.rules import DomainError
from career_agent.models.control.controller import operational_view
from career_agent.models.control.durable import DurableControl
from career_agent.models.control.recovery_contracts import OperatorRequest, ReconcileRequest
from career_agent.ops import query
from career_agent.ops.discovery import AttentionSource
from career_agent.ops.discovery import attention as attention_query
from career_agent.product.contracts import Page

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


def authorize_operator(
    request: Request, x_ops_token: Annotated[str | None, Header()] = None
) -> None:
    token = request.app.state.settings.ops_token
    if (
        token is None
        or not x_ops_token
        or not secrets.compare_digest(token.get_secret_value(), x_ops_token)
    ):
        raise DomainError("operator_authorization_required", 403)


def owner(request: Request, _: Annotated[None, Depends(authorize_operator)]) -> DurableControl:
    value: DurableControl | None = getattr(request.app.state, "control_owner", None)
    if value is None:
        raise DomainError("controller_not_ready", 503)
    return value


Owner = Annotated[DurableControl, Depends(owner)]


@router.get("/controller")
async def controller(control: Owner) -> dict[str, Any]:
    return {
        **operational_view(control.controller),
        "scope": control.scope,
        "base_policy": control.controller.policy.model_dump(mode="json"),
        "effective": control.controller.effective.model_dump(mode="json"),
        "circuits": {
            route: {"phase": c.phase, "disabled": c.disabled, "probes": c.probes}
            for route, c in control.controller.circuits.items()
        },
    }


@router.get("/metrics")
async def metrics(
    control: Owner, window_seconds: Annotated[int, Query(ge=1, le=86400)] = 3600
) -> dict[str, Any]:
    async with control.sessions() as session:
        return await query.metrics(session, control.scope, window_seconds)


@router.get("/events")
async def events(
    control: Owner,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    async with control.sessions() as session:
        return await query.events(session, control.scope, after, limit)


@router.get("/recovery-incidents")
async def incidents(
    control: Owner, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[dict[str, Any]]:
    async with control.sessions() as session:
        return await query.incidents(session, control.scope, limit)


@router.post("/controls")
async def controls(payload: OperatorRequest, control: Owner) -> dict[str, Any]:
    return await control.operate(payload)


@router.post("/attempts/{attempt_id}/reconcile")
async def reconcile(attempt_id: UUID, payload: ReconcileRequest, control: Owner) -> dict[str, Any]:
    return await control.reconcile(attempt_id, payload)


@router.get("/attention")
async def attention(
    control: Owner,
    source: AttentionSource | None = None,
    status: str | None = None,
    include_resolved: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[dict[str, Any]]:
    async with control.sessions() as session:
        return await attention_query(
            session, control.scope, source, status, limit, offset, include_resolved
        )


@router.get("/attempts/{attempt_id}")
async def attempt(attempt_id: UUID, control: Owner) -> dict[str, Any]:
    from sqlalchemy import select

    from career_agent.models.control.recovery_contracts import JournalData
    from career_agent.ops.entities import AttemptJournal

    async with control.sessions() as session:
        row = await session.scalar(
            select(AttemptJournal).where(
                AttemptJournal.scope == control.scope, AttemptJournal.attempt_id == attempt_id
            )
        )
        if row is None:
            raise DomainError("not_found", 404)
        data = JournalData.model_validate(row.data)
        return {
            "id": row.id,
            "attempt_id": row.attempt_id,
            "operation_id": row.operation_id,
            "status": row.status,
            "created_at": row.created_at,
            "model_call_id": data.model_call_id,
            "artifact_ref": data.artifact_ref,
            "budget_owner_refs": data.budget_owner_refs,
            "provider_outcome": data.provider_outcome,
            "dispatch_confirmed": data.dispatch_confirmed,
            "dispatched_at": data.dispatched_at,
            "settled_at": data.settled_at,
            "financial_reservation": data.financial_reservation.model_dump(mode="json"),
            "usage": data.usage.model_dump(mode="json") if data.usage else None,
            "latency_ms": data.latency_ms,
        }
