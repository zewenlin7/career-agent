"""Actual intake and explicit interview workflows; no planner, worker or paid default."""

import json
from functools import partial
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from career_agent.api.dependencies import DB
from career_agent.api.schemas import InterviewOut
from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.domain.schemas import InterviewEntryCreate, InterviewUpdate
from career_agent.infrastructure import entities as e
from career_agent.interview import actual
from career_agent.interview.contracts import (
    AnswerSubmit,
    Continuation,
    DebriefCreate,
    DebriefRegenerate,
    MockCreate,
)
from career_agent.interview.debrief import DebriefService
from career_agent.interview.mock import MockService
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.providers import dependencies as preparation_dependencies

# Interview workflows have no search capability and need no research-provider secret.
dependencies = partial(preparation_dependencies, require_research=False)

router = APIRouter(prefix="/api/v1")


@router.get("/interviews", response_model=list[InterviewOut])
async def list_actual(
    application_id: UUID,
    session: DB,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[e.InterviewSession]:
    await require(session, e.Application, application_id)
    return list(
        await session.scalars(
            select(e.InterviewSession)
            .where(e.InterviewSession.application_id == application_id)
            .order_by(e.InterviewSession.created_at, e.InterviewSession.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/interviews/{id}", response_model=InterviewOut)
async def actual_view(id: UUID, session: DB) -> e.InterviewSession:
    return await require(session, e.InterviewSession, id)


@router.patch("/interviews/{id}", response_model=InterviewOut)
async def update_actual(id: UUID, payload: InterviewUpdate, session: DB) -> e.InterviewSession:
    return await actual.update(session, id, payload)


@router.post("/interviews/{id}/entries", response_model=InterviewOut, status_code=201)
async def append_actual(id: UUID, payload: InterviewEntryCreate, session: DB) -> e.InterviewSession:
    return await actual.append(session, id, payload)


@router.post("/mock-interviews", status_code=201)
async def mock_create(payload: MockCreate, request: Request) -> dict[str, Any]:
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    try:
        async with factory(request.app.state.settings, payload.mode) as (gateway, _):
            return await MockService(
                request.app.state.sessions, request.app.state.settings, gateway
            ).create(payload)
    except ModelGatewayError as exc:
        raise DomainError(exc.code, 422) from None


@router.get("/mock-interviews/{id}")
async def mock_get(id: UUID, request: Request) -> dict[str, Any]:
    async with dependencies(request.app.state.settings, "fixture") as (gateway, _):
        return await MockService(
            request.app.state.sessions, request.app.state.settings, gateway
        ).view(id)


async def mock_continue(
    id: UUID,
    payload: Continuation,
    request: Request,
    operation: Literal["answer", "generate", "end"],
) -> dict[str, Any]:
    async with request.app.state.sessions() as session:
        row = await require(session, e.MockInterviewSession, id)
        mode = row.mode
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    try:
        async with factory(request.app.state.settings, mode) as (gateway, _):
            return await MockService(
                request.app.state.sessions, request.app.state.settings, gateway
            ).continue_(id, payload, operation)
    except ModelGatewayError as exc:
        raise DomainError(exc.code, 422) from None


@router.post("/mock-interviews/{id}/answers")
async def mock_answer(id: UUID, payload: AnswerSubmit, request: Request) -> dict[str, Any]:
    return await mock_continue(id, payload, request, "answer")


@router.post("/mock-interviews/{id}/generate")
async def mock_generate(id: UUID, payload: Continuation, request: Request) -> dict[str, Any]:
    return await mock_continue(id, payload, request, "generate")


@router.post("/mock-interviews/{id}/end")
async def mock_end(id: UUID, payload: Continuation, request: Request) -> dict[str, Any]:
    return await mock_continue(id, payload, request, "end")


@router.post("/interview-debriefs", status_code=201)
async def debrief_create(payload: DebriefCreate, request: Request) -> dict[str, Any]:
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    try:
        async with factory(request.app.state.settings, payload.mode) as (gateway, _):
            return await DebriefService(
                request.app.state.sessions, request.app.state.settings, gateway
            ).create(payload)
    except ModelGatewayError as exc:
        raise DomainError(exc.code, 422) from None


@router.get("/interview-debriefs/{id}")
async def debrief_get(id: UUID, request: Request, historical: bool = False) -> dict[str, Any]:
    async with dependencies(request.app.state.settings, "fixture") as (gateway, _):
        return await DebriefService(
            request.app.state.sessions, request.app.state.settings, gateway
        ).view(id, historical=historical)


@router.get("/interview-debriefs/{id}/events")
async def debrief_events(
    id: UUID, request: Request, after: int = Query(0, ge=0)
) -> list[dict[str, Any]]:
    async with dependencies(request.app.state.settings, "fixture") as (gateway, _):
        return await DebriefService(
            request.app.state.sessions, request.app.state.settings, gateway
        ).events(id, after)


@router.post("/interview-debriefs/{id}/execute")
async def execute_debrief(id: UUID, request: Request) -> StreamingResponse:
    from collections.abc import AsyncIterator

    async with request.app.state.sessions() as session:
        run = await require(session, e.DebriefRun, id)
        if run.status != "ready":
            raise DomainError("debrief_already_started")
        mode = run.mode
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)

    async def stream() -> AsyncIterator[str]:
        try:
            async with factory(request.app.state.settings, mode) as (gateway, _):
                service = DebriefService(
                    request.app.state.sessions, request.app.state.settings, gateway
                )
                iterator = service.execute(id)
                try:
                    async for event in iterator:
                        yield (
                            f"id: {event['sequence']}\nevent: {event['event']}\n"
                            f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        )
                finally:
                    await iterator.aclose()
        except (DomainError, ModelGatewayError) as exc:
            yield f"event: error\ndata: {json.dumps({'error_code': exc.code})}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.post("/interview-debriefs/{id}/regenerate", status_code=201)
async def debrief_regenerate(
    id: UUID, payload: DebriefRegenerate, request: Request
) -> dict[str, Any]:
    async with request.app.state.sessions() as session:
        old = await require(session, e.DebriefRun, id)
        mode = old.mode
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    async with factory(request.app.state.settings, mode) as (gateway, _):
        return await DebriefService(
            request.app.state.sessions, request.app.state.settings, gateway
        ).regenerate(id, payload)
