"""Single-user product discovery and explicit operations; no background execution."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from career_agent.api.dependencies import DB
from career_agent.api.schemas import ApplicationOut, KnowledgeOut, ProfileOut
from career_agent.application.compatibility import compatible, execution_versions
from career_agent.application.services import application_events, require
from career_agent.domain.rules import ApplicationStatus, DomainError, RunStatus
from career_agent.infrastructure import entities as e
from career_agent.preparation.providers import dependencies
from career_agent.product import materials, operations
from career_agent.product.contracts import (
    OperationCreate,
    OperationOut,
    PackageView,
    Page,
    SubmissionCreate,
    SubmissionOut,
)
from career_agent.product.entities import MaterialSubmission, ProductOperation
from career_agent.product.results import package_view

router = APIRouter(prefix="/api/v1", tags=["product"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


async def rows(
    session: AsyncSession, stmt: Select[Any], limit: int, offset: int
) -> tuple[list[Any], bool]:
    values = list(await session.scalars(stmt.limit(limit + 1).offset(offset)))
    return values[:limit], len(values) > limit


@router.get("/companies", response_model=Page[dict[str, Any]])
async def companies(
    session: DB, q: str | None = None, limit: Limit = 50, offset: Offset = 0
) -> Any:
    stmt = select(e.Company).order_by(e.Company.created_at.desc(), e.Company.id)
    if q:
        stmt = stmt.where(e.Company.name.contains(q, autoescape=True))
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[{"id": r.id, "name": r.name, "created_at": r.created_at} for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/companies/{id}")
async def company(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, e.Company, id)
    return {"id": row.id, "name": row.name, "created_at": row.created_at}


def research_view(row: e.CompanyResearch) -> dict[str, Any]:
    reusable = (
        row.expires_at > e.utcnow()
        and row.fetched_at <= e.utcnow()
        and compatible(
            row.data.get("compatibility_versions"), execution_versions("company_research")
        ).reusable_for_current_execution
    )
    return {
        "id": row.id,
        "company_id": row.company_id,
        "research_version": row.research_version,
        "fetched_at": row.fetched_at,
        "expires_at": row.expires_at,
        "historical_readable": True,
        "reusable_for_current_execution": reusable,
        "data": row.data,
    }


@router.get("/companies/{id}/research", response_model=Page[dict[str, Any]])
async def research_list(
    id: UUID,
    session: DB,
    mode: Literal["fixture", "live"] | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    await require(session, e.Company, id)
    stmt = (
        select(e.CompanyResearch)
        .where(e.CompanyResearch.company_id == id)
        .order_by(e.CompanyResearch.research_version.desc(), e.CompanyResearch.id)
    )
    if mode:
        stmt = stmt.where(e.CompanyResearch.data["mode"].astext == mode)
    found, more = await rows(session, stmt, limit, offset)
    return Page(items=[research_view(r) for r in found], limit=limit, offset=offset, has_more=more)


@router.get("/companies/{id}/research/current")
async def current_research(
    id: UUID, session: DB, mode: Literal["fixture", "live"] = "live"
) -> dict[str, Any]:
    await require(session, e.Company, id)
    candidates = await session.scalars(
        select(e.CompanyResearch)
        .where(
            e.CompanyResearch.company_id == id,
            e.CompanyResearch.data["mode"].astext == mode,
            e.CompanyResearch.expires_at > e.utcnow(),
        )
        .order_by(e.CompanyResearch.research_version.desc())
    )
    for row in candidates:
        result = research_view(row)
        if result["reusable_for_current_execution"]:
            return result
    raise DomainError("no_current_research", 404)


@router.post("/companies/{id}/research", response_model=OperationOut, status_code=201)
async def create_research(id: UUID, payload: OperationCreate, session: DB) -> OperationOut:
    await require(session, e.Company, id)
    jd = await require(session, e.JobRevision, payload.request.job_revision_id)
    job = await require(session, e.JobPosting, jd.job_id)
    if job.company_id != id or payload.kind != "company_research":
        raise DomainError("context_revision_mismatch", 422)
    return await operations.create(session, payload)


@router.post("/operations", response_model=OperationOut, status_code=201)
async def create_operation(payload: OperationCreate, session: DB) -> OperationOut:
    return await operations.create(session, payload)


@router.get("/operations", response_model=Page[OperationOut])
async def operation_list(
    session: DB,
    status: str | None = None,
    job_revision_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(ProductOperation).order_by(
        ProductOperation.created_at.desc(), ProductOperation.id
    )
    if status:
        stmt = stmt.where(ProductOperation.status == status)
    if job_revision_id:
        stmt = stmt.where(
            ProductOperation.payload["request"]["job_revision_id"].astext == str(job_revision_id)
        )
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[await operations.read(session, r.id) for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/operations/{id}", response_model=OperationOut)
async def operation_get(id: UUID, session: DB) -> OperationOut:
    return await operations.read(session, id)


@router.post("/operations/{id}/execute", response_model=OperationOut)
async def operation_execute(id: UUID, request: Request) -> OperationOut:
    factory = getattr(request.app.state, "preparation_dependencies", dependencies)
    return await operations.execute(
        request.app.state.sessions, request.app.state.settings, id, factory
    )


@router.get("/operations/{id}/result")
async def operation_result(id: UUID, session: DB) -> PackageView | dict[str, Any]:
    row = await operations.read(session, id)
    if row.package_id:
        return await package_view(session, row.package_id)
    if row.research_report_id:
        return research_view(await require(session, e.CompanyResearch, row.research_report_id))
    raise DomainError("result_not_available")


@router.get("/preparation-artifacts/{id}/product-view", response_model=PackageView)
async def result_view(id: UUID, session: DB) -> PackageView:
    return await package_view(session, id)


@router.get("/applications", response_model=Page[ApplicationOut])
async def applications(
    session: DB,
    job_id: UUID | None = None,
    company_id: UUID | None = None,
    status: ApplicationStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = (
        select(e.Application)
        .join(e.JobPosting)
        .order_by(e.Application.created_at.desc(), e.Application.id)
    )
    if job_id:
        stmt = stmt.where(e.Application.job_id == job_id)
    if company_id:
        stmt = stmt.where(e.JobPosting.company_id == company_id)
    if status:
        stmt = stmt.where(e.Application.status == status)
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[
            ApplicationOut(
                id=r.id,
                created_at=r.created_at,
                job_id=r.job_id,
                status=r.status,
                revision=r.revision,
                events=await application_events(session, r.id),
            )
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.post("/applications/{id}/submissions", response_model=SubmissionOut, status_code=201)
async def submit(
    id: UUID, payload: SubmissionCreate, request: Request, session: DB
) -> SubmissionOut:
    return await materials.submit(session, request.app.state.settings, id, payload)


@router.get("/applications/{id}/submissions", response_model=Page[SubmissionOut])
async def submissions(id: UUID, session: DB, limit: Limit = 50, offset: Offset = 0) -> Any:
    await require(session, e.Application, id)
    found, more = await rows(
        session,
        select(MaterialSubmission)
        .where(MaterialSubmission.application_id == id)
        .order_by(MaterialSubmission.created_at.desc(), MaterialSubmission.id),
        limit,
        offset,
    )
    return Page(items=[materials.view(r) for r in found], limit=limit, offset=offset, has_more=more)


@router.get("/profile/revisions", response_model=Page[ProfileOut])
async def profiles(session: DB, limit: Limit = 50, offset: Offset = 0) -> Any:
    found, more = await rows(
        session,
        select(e.PersonalProfile).order_by(e.PersonalProfile.revision.desc(), e.PersonalProfile.id),
        limit,
        offset,
    )
    return Page(
        items=[ProfileOut.model_validate(r) for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/profile/revisions/{id}", response_model=ProfileOut)
async def profile_revision(id: UUID, session: DB) -> e.PersonalProfile:
    return await require(session, e.PersonalProfile, id)


@router.get("/jobs/{id}/revisions", response_model=Page[dict[str, Any]])
async def job_revisions(id: UUID, session: DB, limit: Limit = 50, offset: Offset = 0) -> Any:
    await require(session, e.JobPosting, id)
    found, more = await rows(
        session,
        select(e.JobRevision)
        .where(e.JobRevision.job_id == id)
        .order_by(e.JobRevision.revision.desc(), e.JobRevision.id),
        limit,
        offset,
    )
    return Page(
        items=[await jd_view(session, r) for r in found], limit=limit, offset=offset, has_more=more
    )


async def jd_view(session: AsyncSession, row: e.JobRevision) -> dict[str, Any]:
    requirements = await session.scalars(
        select(e.JobRequirement)
        .where(e.JobRequirement.job_revision_id == row.id)
        .order_by(e.JobRequirement.created_at, e.JobRequirement.id)
    )
    return {
        "job_id": row.job_id,
        "job_revision_id": row.id,
        "revision": row.revision,
        "title": row.title,
        "jd_text": row.jd_text,
        "created_at": row.created_at,
        "requirements": [
            {"id": r.id, "text": r.text, "source_quote": r.source_quote, "category": r.category}
            for r in requirements
        ],
    }


@router.get("/job-revisions/{id}")
async def jd_detail(id: UUID, session: DB) -> dict[str, Any]:
    return await jd_view(session, await require(session, e.JobRevision, id))


async def selected_job(
    session: AsyncSession, job_id: UUID | None, application_id: UUID | None
) -> UUID | None:
    if application_id:
        app = await require(session, e.Application, application_id)
        if job_id and job_id != app.job_id:
            raise DomainError("context_revision_mismatch", 422)
        return app.job_id
    if job_id:
        await require(session, e.JobPosting, job_id)
    return job_id


@router.get("/mock-interviews", response_model=Page[dict[str, Any]])
async def mocks(
    session: DB,
    job_id: UUID | None = None,
    application_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    job_id = await selected_job(session, job_id, application_id)
    stmt = select(e.MockInterviewSession).order_by(
        e.MockInterviewSession.created_at.desc(), e.MockInterviewSession.id
    )
    if job_id:
        stmt = stmt.where(e.MockInterviewSession.context["job_id"].astext == str(job_id))
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[
            {
                "id": r.id,
                "run_id": r.run_id,
                "status": r.status,
                "revision": r.revision,
                "job_id": r.context["job_id"],
                "created_at": r.created_at,
                "pending_question_id": r.pending_question_id,
            }
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/interview-debriefs", response_model=Page[dict[str, Any]])
async def debriefs(
    session: DB,
    source_kind: Literal["actual", "mock"] | None = None,
    source_id: UUID | None = None,
    job_id: UUID | None = None,
    application_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    job_id = await selected_job(session, job_id, application_id)
    stmt = select(e.DebriefRun).order_by(e.DebriefRun.created_at.desc(), e.DebriefRun.id)
    if source_kind:
        stmt = stmt.where(e.DebriefRun.snapshot["source_kind"].astext == source_kind)
    if source_id:
        stmt = stmt.where(e.DebriefRun.snapshot["interview_id"].astext == str(source_id))
    if job_id:
        actual_ids = (
            select(cast(e.InterviewSession.id, String))
            .join(e.Application)
            .where(e.Application.job_id == job_id)
        )
        stmt = stmt.where(
            or_(
                e.DebriefRun.snapshot["context"]["job_id"].astext == str(job_id),
                (e.DebriefRun.snapshot["source_kind"].astext == "actual")
                & e.DebriefRun.snapshot["interview_id"].astext.in_(actual_ids),
            )
        )
    found, more = await rows(session, stmt, limit, offset)
    roots = {
        r.id: r
        for r in await session.scalars(
            select(e.DebriefRun).where(e.DebriefRun.id.in_([r.root_run_id or r.id for r in found]))
        )
    }
    selected = {
        r.id: roots[r.root_run_id or r.id].selected_run_id or r.root_run_id or r.id for r in found
    }
    return Page(
        items=[
            {
                "id": r.id,
                "generation_id": r.id,
                "is_selected": selected[r.id] == r.id,
                "detail_url": f"/api/v1/interview-debriefs/{r.root_run_id or r.id}",
                "historical_detail_url": f"/api/v1/interview-debriefs/{r.id}?historical=true",
                "run_id": r.run_id,
                "status": r.status,
                "source_kind": r.snapshot["source_kind"],
                "source_id": r.snapshot["interview_id"],
                "source_hash": r.source_hash,
                "root_run_id": r.root_run_id or r.id,
                "selected_run_id": selected[r.id],
                "supersedes_run_id": r.supersedes_run_id,
                "created_at": r.created_at,
            }
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/runs", response_model=Page[dict[str, Any]])
async def runs(
    session: DB,
    kind: Literal["agent", "workflow"] | None = None,
    workflow: str | None = None,
    status: RunStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(e.AgentRun).order_by(e.AgentRun.created_at.desc(), e.AgentRun.id)
    if kind:
        stmt = stmt.where(e.AgentRun.run_kind == kind)
    if workflow:
        stmt = stmt.where(e.AgentRun.workflow == workflow)
    if status:
        stmt = stmt.where(e.AgentRun.status == status)
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[
            {
                "id": r.id,
                "kind": r.run_kind,
                "workflow": r.workflow,
                "status": r.status,
                "reason": r.stop_reason,
                "created_at": r.created_at,
            }
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/applications/{id}/knowledge-notes", response_model=Page[KnowledgeOut])
async def application_knowledge(
    id: UUID, session: DB, limit: Limit = 50, offset: Offset = 0
) -> Any:
    await require(session, e.Application, id)
    # Include legacy notes through their authoritative actual-interview association.
    stmt = (
        select(e.KnowledgeNote)
        .where(
            or_(
                e.KnowledgeNote.application_id == id,
                e.KnowledgeNote.interview_id.in_(
                    select(e.InterviewSession.id).where(e.InterviewSession.application_id == id)
                ),
            )
        )
        .order_by(e.KnowledgeNote.created_at.desc(), e.KnowledgeNote.id)
    )
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[KnowledgeOut.model_validate(r) for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )
