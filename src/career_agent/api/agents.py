"""Agent API owns action-boundary transactions; it does not use request-wide DB dependency."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from career_agent.api.dependencies import DB
from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.providers import dependencies
from career_agent.runtime.agent_contracts import AgentCreate, AgentResume
from career_agent.runtime.engine import AgentEngine

router = APIRouter(prefix="/api/v1/agent-runs")


@router.post("", status_code=201)
async def create(payload: AgentCreate, request: Request) -> dict[str, Any]:
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    try:
        async with factory(request.app.state.settings, payload.mode) as (gateway, research):
            return await AgentEngine(
                request.app.state.sessions, request.app.state.settings, gateway, research
            ).create(payload)
    except ModelGatewayError as exc:
        raise DomainError(exc.code) from None


@router.get("/{id}")
async def read(id: UUID, session: DB) -> dict[str, Any]:
    run = await require(session, e.AgentRun, id)
    if run.run_kind != "agent":
        raise DomainError("not_agent_run", 404)
    checkpoint = await session.scalar(
        select(e.AgentCheckpoint)
        .where(e.AgentCheckpoint.run_id == id)
        .order_by(e.AgentCheckpoint.revision.desc())
    )
    if checkpoint is None:
        raise DomainError("checkpoint_missing")
    return {"run_id": id, "state": checkpoint.state, "outcome": run.outcome}


@router.get("/{id}/plans")
async def plans(id: UUID, session: DB) -> list[dict[str, Any]]:
    await require(session, e.AgentRun, id)
    return [
        {"id": r.id, "revision": r.revision, "plan": r.data}
        for r in await session.scalars(
            select(e.AgentPlan).where(e.AgentPlan.run_id == id).order_by(e.AgentPlan.revision)
        )
    ]


@router.get("/{id}/observations")
async def observations(id: UUID, session: DB) -> list[dict[str, Any]]:
    await require(session, e.AgentRun, id)
    rows = await session.scalars(
        select(e.Observation)
        .join(e.AgentStep, e.Observation.action_step_id == e.AgentStep.id)
        .where(e.AgentStep.run_id == id)
        .order_by(e.AgentStep.sequence)
    )
    return [{"id": r.id, "observation": r.action_data} for r in rows]


@router.post("/{id}/resume")
async def resume(id: UUID, payload: AgentResume, request: Request) -> dict[str, Any]:
    async with request.app.state.sessions() as session:
        run = await require(session, e.AgentRun, id)
        goal = await session.scalar(select(e.AgentGoal).where(e.AgentGoal.run_id == run.id))
        if goal is None:
            raise DomainError("not_agent_run", 404)
        mode = goal.data["mode"]
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    try:
        async with factory(request.app.state.settings, mode) as (gateway, research):
            return await AgentEngine(
                request.app.state.sessions, request.app.state.settings, gateway, research
            ).resume(id, payload)
    except ModelGatewayError as exc:
        raise DomainError(exc.code) from None
