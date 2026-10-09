import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from career_agent.api import schemas as out
from career_agent.application import services as svc
from career_agent.config import Settings
from career_agent.domain import schemas as inp
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.db import make_engine
from career_agent.security.logging import SafeCode, SafeEvent, safe_log

logger = logging.getLogger("career_agent.api")


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session, session.begin():
        yield session


DB = Annotated[AsyncSession, Depends(db, scope="function")]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "v0.1a"}


@router.get("/profile", response_model=out.ProfileOut)
async def profile(session: DB) -> e.PersonalProfile:
    return await svc.get_profile(session)


@router.put("/profile", response_model=out.ProfileOut)
async def put_profile(payload: inp.ProfileWrite, session: DB) -> e.PersonalProfile:
    return await svc.put_profile(session, payload)


@router.get("/facts", response_model=list[out.FactOut])
async def facts(session: DB, limit: Limit = 50, offset: Offset = 0) -> list[e.PersonalFact]:
    return list(
        await session.scalars(
            select(e.PersonalFact)
            .order_by(e.PersonalFact.created_at, e.PersonalFact.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/facts", response_model=out.FactOut, status_code=201)
async def create_fact(payload: inp.FactCreate, session: DB) -> e.PersonalFact:
    return await svc.create_fact(session, payload)


@router.post("/facts/{row_id}/verify", response_model=out.FactOut)
async def verify_fact(row_id: UUID, session: DB) -> e.PersonalFact:
    return await svc.verify_user_fact(session, row_id)


@router.post("/facts/{row_id}/reject", response_model=out.FactOut)
async def reject_fact(row_id: UUID, session: DB) -> e.PersonalFact:
    return await svc.reject_user_fact(session, row_id)


@router.post("/facts/{row_id}/supersede", response_model=out.FactOut, status_code=201)
async def supersede_fact(row_id: UUID, payload: inp.FactReplacement, session: DB) -> e.PersonalFact:
    return await svc.supersede_fact(session, row_id, payload)


@router.post("/jobs", response_model=out.JobOut, status_code=201)
async def create_job(payload: inp.JobCreate, session: DB) -> dict[str, Any]:
    return await svc.job_view(session, await svc.create_job(session, payload))


@router.get("/jobs", response_model=list[out.JobOut])
async def jobs(session: DB, limit: Limit = 50, offset: Offset = 0) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(e.JobPosting)
        .order_by(e.JobPosting.created_at, e.JobPosting.id)
        .limit(limit)
        .offset(offset)
    )
    return [await svc.job_view(session, row) for row in rows]


@router.get("/jobs/{row_id}", response_model=out.JobOut)
async def get_job(row_id: UUID, session: DB) -> dict[str, Any]:
    return await svc.job_view(session, await svc.require(session, e.JobPosting, row_id))


@router.post("/jobs/{row_id}/revisions", response_model=out.JobOut, status_code=201)
async def revise_job(row_id: UUID, payload: inp.JobRevisionWrite, session: DB) -> dict[str, Any]:
    return await svc.job_view(session, await svc.revise_job(session, row_id, payload))


async def application_view(session: AsyncSession, application: e.Application) -> dict[str, Any]:
    return {
        "id": application.id,
        "created_at": application.created_at,
        "job_id": application.job_id,
        "revision": application.revision,
        "status": application.status,
        "events": await svc.application_events(session, application.id),
    }


@router.get("/applications/{row_id}", response_model=out.ApplicationOut)
async def get_application(row_id: UUID, session: DB) -> dict[str, Any]:
    return await application_view(session, await svc.require(session, e.Application, row_id))


@router.patch("/applications/{row_id}", response_model=out.ApplicationOut)
async def change_application(
    row_id: UUID, payload: inp.ApplicationChange, session: DB
) -> dict[str, Any]:
    return await application_view(session, await svc.change_application(session, row_id, payload))


@router.post("/applications/{row_id}/notes", response_model=out.EventOut, status_code=201)
async def application_note(
    row_id: UUID, payload: inp.NoteCreate, session: DB
) -> e.ApplicationEvent:
    return await svc.application_note(session, row_id, payload)


@router.post("/interviews", response_model=out.InterviewOut, status_code=201)
async def create_interview(payload: inp.InterviewCreate, session: DB) -> e.InterviewSession:
    return await svc.create_interview(session, payload)


@router.post("/interviews/{row_id}/notes", response_model=out.InterviewOut, status_code=201)
async def interview_note(row_id: UUID, payload: inp.NoteCreate, session: DB) -> e.InterviewSession:
    return await svc.interview_note(session, row_id, payload)


@router.get("/knowledge-notes", response_model=list[out.KnowledgeOut])
async def knowledge(session: DB, limit: Limit = 50, offset: Offset = 0) -> list[e.KnowledgeNote]:
    return list(
        await session.scalars(
            select(e.KnowledgeNote)
            .order_by(e.KnowledgeNote.created_at, e.KnowledgeNote.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/knowledge-notes", response_model=out.KnowledgeOut, status_code=201)
async def create_knowledge(payload: inp.KnowledgeCreate, session: DB) -> e.KnowledgeNote:
    return await svc.create_knowledge(session, payload)


@router.get("/runs/{row_id}", response_model=out.RunOut)
async def get_run(row_id: UUID, session: DB) -> e.AgentRun:
    return await svc.require(session, e.AgentRun, row_id)


@router.get("/runs/{row_id}/steps", response_model=list[out.StepOut])
async def get_steps(
    row_id: UUID, session: DB, limit: Limit = 50, offset: Offset = 0
) -> list[e.AgentStep]:
    await svc.require(session, e.AgentRun, row_id)
    return list(
        await session.scalars(
            select(e.AgentStep)
            .where(e.AgentStep.run_id == row_id)
            .order_by(e.AgentStep.sequence)
            .limit(limit)
            .offset(offset)
        )
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="Career Agent", version="0.1.0a1", lifespan=lifespan)
    app.state.engine = engine
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
    app.include_router(router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": codes.get(exc.status_code, "http_error")}},
        )

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic errors contain original inputs and context: never reflect them.
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request"}})

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": {"code": "integrity_conflict"}})

    @app.middleware("http")
    async def safe_errors(request: Request, call_next: Any) -> Any:
        # Catch before the ASGI server can log an unsanitized exception traceback.
        try:
            return await call_next(request)
        except Exception:
            safe_log(logger, SafeEvent.REQUEST_FAILED, code=SafeCode.INTERNAL_ERROR)
            return JSONResponse(status_code=500, content={"error": {"code": "internal_error"}})

    return app


app = create_app()
