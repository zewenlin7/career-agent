"""Explicit synchronous workflows; no background worker, automatic application or messaging."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from career_agent.api.dependencies import DB
from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import WorkflowRequest
from career_agent.preparation.providers import dependencies
from career_agent.preparation.workflows import PreparationWorkflow

router = APIRouter(prefix="/api/v1")


@router.post("/workflows/{workflow}", status_code=201)
async def prepare(
    workflow: Literal["prepare_application", "prepare_interview"],
    payload: WorkflowRequest,
    request: Request,
    session: DB,
) -> dict[str, Any]:
    try:
        factory = getattr(request.app.state, "preparation_dependencies", dependencies)
        async with factory(request.app.state.settings, payload.mode) as (gateway, research):
            runner = PreparationWorkflow(
                session, request.app.state.settings, gateway, research, payload
            )
            return await runner.execute(workflow)
    except ModelGatewayError as exc:
        raise DomainError(exc.code, 409) from None


@router.get("/preparation-artifacts/{id}")
async def artifact(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, e.PreparationArtifact, id)
    return {
        "id": row.id,
        "run_id": row.run_id,
        "job_revision_id": row.job_revision_id,
        "profile_id": row.profile_id,
        "data": row.data,
    }


@router.get("/company-research/{id}")
async def research(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, e.CompanyResearch, id)
    return {
        "id": row.id,
        "company_id": row.company_id,
        "research_version": row.research_version,
        "fetched_at": row.fetched_at,
        "expires_at": row.expires_at,
        "data": row.data,
    }


@router.get("/runs/{id}/calls")
async def calls(id: UUID, session: DB) -> dict[str, Any]:
    await require(session, e.AgentRun, id)
    step_ids = select(e.AgentStep.id).where(e.AgentStep.run_id == id)
    models = list(
        await session.scalars(
            select(e.ModelCall)
            .where(e.ModelCall.step_id.in_(step_ids))
            .order_by(e.ModelCall.created_at)
        )
    )
    tools = list(
        await session.scalars(
            select(e.ToolCall)
            .where(e.ToolCall.step_id.in_(step_ids))
            .order_by(e.ToolCall.created_at)
        )
    )
    return {
        "model_calls": [
            {
                k: getattr(r, k)
                for k in [
                    "id",
                    "step_id",
                    "task_type",
                    "provider",
                    "model",
                    "status",
                    "versions",
                    "usage",
                    "latency_ms",
                    "attempts",
                    "estimated_cost",
                    "error_code",
                    "schema_validation_state",
                ]
            }
            for r in models
        ],
        "tool_calls": [
            {
                k: getattr(r, k)
                for k in [
                    "id",
                    "step_id",
                    "tool_name",
                    "tool_version",
                    "usage",
                    "attempt",
                    "status",
                    "latency_ms",
                    "error_code",
                ]
            }
            for r in tools
        ],
    }
