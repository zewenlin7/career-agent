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

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


def owner(request: Request, x_ops_token: Annotated[str | None, Header()] = None) -> DurableControl:
    token = request.app.state.settings.ops_token
    if (
        token is None
        or not x_ops_token
        or not secrets.compare_digest(token.get_secret_value(), x_ops_token)
    ):
        raise DomainError("operator_authorization_required", 403)
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
