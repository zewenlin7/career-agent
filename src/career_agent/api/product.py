"""Single-user product discovery and explicit operations; no background execution."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from career_agent.api.dependencies import DB
from career_agent.api.schemas import ApplicationOut, KnowledgeOut, ProfileOut
from career_agent.application.compatibility import compatible, execution_versions
from career_agent.application.services import (
    application_events,
    check_revision,
    read_application,
    require,
)
from career_agent.domain.rules import ApplicationStatus, DomainError, RunStatus, application_status
from career_agent.domain.schemas import ApplicationEntryWrite, KnowledgeUpdate
from career_agent.infrastructure import entities as e
from career_agent.preparation.providers import dependencies
from career_agent.product import bindings, materials, operations
from career_agent.product.contracts import (
    ApplicationBindingOut,
    ApplicationBindingWrite,
    OperationCreate,
    OperationOut,
    PackageView,
    Page,
    ResultDelete,
    SubmissionCreate,
    SubmissionEdit,
    SubmissionOut,
    TaskHistoryItem,
)
from career_agent.product.draft_contracts import DraftAdopt, DraftCreate
from career_agent.product.drafts import DraftService, ensure_active_task
from career_agent.product.entities import MaterialSubmission, ProductDraft, ProductOperation
from career_agent.product.results import package_view

router = APIRouter(prefix="/api/v1", tags=["product"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/task-status/{family}/{id}")
async def task_status(
    family: Literal["operations", "product-drafts", "mock-interviews", "interview-debriefs"],
    id: UUID,
    session: DB,
    request_id: UUID | None = None,
) -> dict[str, Any]:
    from career_agent.product.task_status import status

    return await status(session, family, id, request_id)


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
        "compatible_for_interview": compatible(
            row.data.get("compatibility_versions"), execution_versions("company_research")
        ).reusable_for_current_execution,
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
        .where(e.CompanyResearch.deleted_at.is_(None))
        .where(e.CompanyResearch.company_id == id)
        .order_by(e.CompanyResearch.fetched_at.desc(), e.CompanyResearch.id)
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
        .where(e.CompanyResearch.deleted_at.is_(None))
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
    company_ids: Annotated[list[UUID] | None, Query(max_length=50)] = None,
    company_q: Annotated[str | None, Query(max_length=200)] = None,
    status: ApplicationStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = (
        select(e.Application)
        .where(e.Application.deleted_at.is_(None))
        .join(e.JobPosting)
        .order_by(e.Application.created_at.desc(), e.Application.id)
    )
    if job_id:
        stmt = stmt.where(e.Application.job_id == job_id)
    selected_companies = set(company_ids or [])
    if company_id:
        selected_companies.add(company_id)
    if selected_companies:
        stmt = stmt.where(e.JobPosting.company_id.in_(selected_companies))
    if company_q and company_q.strip():
        stmt = stmt.join(e.Company).where(
            e.Company.name.contains(company_q.strip(), autoescape=True)
        )
    if status:
        canonical = application_status(status)
        aliases = [s for s in ApplicationStatus if application_status(s) == canonical]
        stmt = stmt.where(e.Application.status.in_(aliases))
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
    await read_application(session, id)
    found, more = await rows(
        session,
        select(MaterialSubmission)
        .where(MaterialSubmission.application_id == id, MaterialSubmission.deleted_at.is_(None))
        .order_by(MaterialSubmission.created_at.desc(), MaterialSubmission.id),
        limit,
        offset,
    )
    return Page(
        items=[await materials.view(session, r) for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.patch("/applications/{id}/submissions/{submission_id}", response_model=SubmissionOut)
async def edit_submission(
    id: UUID, submission_id: UUID, payload: SubmissionEdit, session: DB
) -> SubmissionOut:
    return await materials.edit(session, id, submission_id, payload)


@router.delete("/applications/{id}/submissions/{submission_id}", response_model=SubmissionOut)
async def delete_submission(
    id: UUID, submission_id: UUID, payload: SubmissionEdit, session: DB
) -> SubmissionOut:
    return await materials.edit(session, id, submission_id, payload, remove=True)


@router.get("/profile/revisions", response_model=Page[ProfileOut])
async def profiles(session: DB, limit: Limit = 50, offset: Offset = 0) -> Any:
    found, more = await rows(
        session,
        select(e.PersonalProfile)
        .where(e.PersonalProfile.archived_at.is_(None))
        .order_by(e.PersonalProfile.revision.desc(), e.PersonalProfile.id),
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
            {
                "id": r.id,
                "text": r.text,
                "source_quote": r.source_quote,
                "category": r.category,
                "importance": r.importance,
            }
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
        app = await read_application(session, application_id)
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
    if application_id:
        # NULL legacy owners must also pass exact frozen-source verification below.
        stmt = stmt.where(
            (e.MockInterviewSession.application_id == application_id)
            | e.MockInterviewSession.application_id.is_(None)
        )
    if job_id:
        stmt = stmt.where(e.MockInterviewSession.context["job_id"].astext == str(job_id))
    from career_agent.interview.ownership import mock_owner

    candidates = list(await session.scalars(stmt))
    owned = [(r, await mock_owner(session, r)) for r in candidates]
    owned = [(r, owner) for r, owner in owned if not application_id or owner == application_id]
    more = len(owned) > offset + limit
    from career_agent.interview.execution import available

    orphaned = {
        r.id: r.generation_active and await available(session, r.id)
        for r, _ in owned[offset : offset + limit]
    }
    return Page(
        items=[
            {
                "id": r.id,
                "run_id": r.run_id,
                "application_id": owner,
                "display_number": r.display_number,
                "status": r.status,
                "revision": r.revision,
                "job_id": r.context["job_id"],
                "created_at": r.created_at,
                "pending_question_id": r.pending_question_id,
                "creation_request_id": r.request_id,
                "focus": r.focus,
                "policy": r.policy,
                "primary_question_count": r.primary_question_count,
                "followup_count": r.followup_count,
                "generation_active": r.generation_active and not orphaned[r.id],
                "stop_reason": "execution_outcome_unknown" if orphaned[r.id] else r.stop_reason,
            }
            for r, owner in owned[offset : offset + limit]
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
    stmt = (
        select(e.DebriefRun)
        .where(e.DebriefRun.deleted_at.is_(None))
        .order_by(e.DebriefRun.created_at.desc(), e.DebriefRun.id)
    )
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
    from career_agent.interview.review_state import owner, source_name

    candidates = list(await session.scalars(stmt))
    found_all = [
        r for r in candidates if not application_id or await owner(session, r) == application_id
    ]
    found, more = found_all[offset : offset + limit], len(found_all) > offset + limit
    names = {r.id: await source_name(session, r.snapshot) for r in found}
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
                "source_name": names[r.id],
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
    await read_application(session, id)
    # Include legacy notes through their authoritative actual-interview association.
    stmt = (
        select(e.KnowledgeNote)
        .where(e.KnowledgeNote.deleted_at.is_(None))
        .where(
            or_(
                e.KnowledgeNote.application_id == id,
                e.KnowledgeNote.interview_id.in_(
                    select(e.InterviewSession.id).where(e.InterviewSession.application_id == id)
                ),
            )
        )
        .order_by(
            func.coalesce(e.KnowledgeNote.updated_at, e.KnowledgeNote.created_at).desc(),
            e.KnowledgeNote.id,
        )
    )
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[KnowledgeOut.model_validate(r) for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.post("/resume-revisions/{id}/save")
async def save_resume_to_library(id: UUID, session: DB) -> dict[str, Any]:
    revision = await require(session, e.ResumeVariantRevision, id)
    variant = await require(session, e.ResumeVariant, revision.resume_variant_id, lock=True)
    variant.library_visible = True
    return {"resume_revision_id": revision.id, "saved": True}


@router.get("/resume-revisions/{id}/renders")
async def resume_renders(id: UUID, session: DB) -> list[dict[str, Any]]:
    revision = await require(session, e.ResumeVariantRevision, id)
    artifacts = await session.scalars(
        select(e.RenderArtifact)
        .where(
            e.RenderArtifact.resume_variant_id == revision.resume_variant_id,
            e.RenderArtifact.resume_variant_revision == revision.revision,
            e.RenderArtifact.report["render_status"].astext == "accepted",
        )
        .order_by(e.RenderArtifact.created_at.desc(), e.RenderArtifact.id)
        .limit(100)
    )
    return [
        {
            "id": artifact.id,
            "created_at": artifact.created_at,
            "download_url": f"/api/v1/artifacts/{artifact.id}/download",
        }
        for artifact in artifacts
    ]


@router.get("/applications/{id}/context", response_model=ApplicationBindingOut)
async def application_binding(id: UUID, session: DB) -> ApplicationBindingOut:
    return await bindings.view(session, await bindings.read(session, id, readonly=True))


@router.put("/applications/{id}/context", response_model=ApplicationBindingOut)
async def update_application_binding(
    id: UUID, payload: ApplicationBindingWrite, session: DB
) -> ApplicationBindingOut:
    return await bindings.view(session, await bindings.update(session, id, payload))


@router.get("/applications/{id}/results", response_model=Page[TaskHistoryItem])
async def task_history(
    id: UUID,
    target: Literal[
        "fit_analysis", "resume_tailoring", "greeting_generation", "interview_preparation"
    ],
    session: DB,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[TaskHistoryItem]:
    from career_agent.product.results import history

    return await history(session, id, target, limit, offset)


@router.patch("/knowledge-notes/{id}", response_model=KnowledgeOut)
async def update_knowledge(id: UUID, payload: KnowledgeUpdate, session: DB) -> e.KnowledgeNote:
    note = await require(session, e.KnowledgeNote, id, lock=True)
    from career_agent.application.services import active_interview_target

    await active_interview_target(session, note)
    await knowledge_scope(session, note, payload.application_id)
    if note.deleted_at is not None:
        raise DomainError("not_found", 404)
    check_revision(note.revision, payload.expected_revision)
    if (note.title, note.content) != (payload.title, payload.content):
        note.title, note.content = payload.title, payload.content
        note.revision += 1
        note.updated_at = e.utcnow()
    return note


@router.delete("/knowledge-notes/{id}")
async def delete_knowledge(
    id: UUID, expected_revision: int, session: DB, application_id: UUID | None = None
) -> dict[str, bool]:
    note = await require(session, e.KnowledgeNote, id, lock=True)
    from career_agent.application.services import active_interview_target

    await active_interview_target(session, note)
    await knowledge_scope(session, note, application_id)
    check_revision(note.revision, expected_revision)
    note.deleted_at = note.deleted_at or e.utcnow()
    return {"deleted": True}


async def knowledge_scope(
    session: AsyncSession, note: e.KnowledgeNote, application_id: UUID | None
) -> None:
    if application_id is None:
        return
    owner = note.application_id
    if owner is None and note.interview_id:
        owner = (await require(session, e.InterviewSession, note.interview_id)).application_id
    if owner != application_id:
        raise DomainError("knowledge_application_mismatch", 409)


@router.post("/product-drafts", status_code=201)
async def create_product_draft(payload: DraftCreate, request: Request) -> dict[str, Any]:
    factory = getattr(request.app.state, "preparation_dependencies", None)
    context = (
        factory(request.app.state.settings, payload.mode)
        if factory
        else dependencies(request.app.state.settings, payload.mode, require_research=False)
    )
    async with context as (gateway, _):
        return await DraftService(
            request.app.state.sessions, request.app.state.settings, gateway
        ).create(payload)


@router.get("/product-drafts/{id}")
async def read_product_draft(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, ProductDraft, id, lock=True)
    if row.status == "running":
        free = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 4308))"), {"key": str(id)}
        )
        if free:
            row.status, row.reason = "recovery_required", "execution_interrupted"
    return DraftService.view(row)


@router.post("/product-drafts/{id}/execute")
async def execute_product_draft(id: UUID, request: Request) -> dict[str, Any]:
    async with request.app.state.sessions() as session:
        row = await require(session, ProductDraft, id)
        ensure_active_task(row.task)
        mode = row.mode
    factory = getattr(request.app.state, "preparation_dependencies", None)
    context = (
        factory(request.app.state.settings, mode)
        if factory
        else dependencies(request.app.state.settings, mode, require_research=False)
    )
    async with context as (gateway, _):
        from career_agent.profile_area.cancellation import execute

        return await execute(
            DraftService(request.app.state.sessions, request.app.state.settings, gateway), id
        )


@router.post("/product-drafts/{id}/adopt")
async def adopt_product_draft(id: UUID, payload: DraftAdopt, request: Request) -> dict[str, Any]:
    async with dependencies(request.app.state.settings, "fixture", require_research=False) as (
        gateway,
        _,
    ):
        return await DraftService(
            request.app.state.sessions, request.app.state.settings, gateway
        ).adopt(id, payload)


@router.get("/resume-library", response_model=Page[dict[str, Any]])
async def resume_library(
    session: DB, limit: Limit = 20, offset: Offset = 0
) -> Page[dict[str, Any]]:
    stmt = (
        select(e.ResumeVariantRevision)
        .join(e.ResumeVariant)
        .where(
            e.ResumeVariant.library_visible.is_(True),
            e.ResumeVariantRevision.archived_at.is_(None),
            e.ResumeVariantRevision.revision == e.ResumeVariant.current_revision,
        )
        .order_by(e.ResumeVariantRevision.created_at.desc(), e.ResumeVariantRevision.id)
    )
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[
            {
                "resume_variant_id": r.resume_variant_id,
                "resume_revision_id": r.id,
                "revision": r.revision,
                "label": r.document.get("metadata", {}).get("label"),
                "profile_id": r.profile_id,
                "created_at": r.created_at,
            }
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.post("/product-drafts/{id}/cancel")
async def cancel_product_draft(id: UUID, request: Request) -> dict[str, Any]:
    from career_agent.profile_area.cancellation import cancel

    return await cancel(request.app.state.sessions, id)


@router.get("/applications/{id}/summary")
async def application_summary(id: UUID, session: DB) -> dict[str, Any]:
    from career_agent.product.summary import read

    return await read(session, id)


@router.patch("/applications/{id}/entries/{entry_id}")
async def edit_application_entry(
    id: UUID, entry_id: UUID, payload: ApplicationEntryWrite, session: DB
) -> dict[str, Any]:
    from career_agent.product.summary import edit_entry

    return await edit_entry(session, id, entry_id, payload)


@router.delete("/applications/{id}/entries/{entry_id}")
async def remove_application_entry(
    id: UUID, entry_id: UUID, payload: ApplicationEntryWrite, session: DB
) -> dict[str, Any]:
    from career_agent.product.summary import edit_entry

    return await edit_entry(session, id, entry_id, payload, remove=True)


@router.get("/resume-revisions/{id}/snapshot")
async def resume_snapshot(id: UUID, session: DB, pdf: UUID | None = None) -> dict[str, Any]:
    row = await require(session, e.ResumeVariantRevision, id)
    artifact = await require(session, e.RenderArtifact, pdf) if pdf else None
    if artifact and (
        artifact.resume_variant_id != row.resume_variant_id
        or artifact.resume_variant_revision != row.revision
    ):
        raise DomainError("context_revision_mismatch", 422)
    return {
        "name": row.display_name or "简历",
        "document": row.document,
        "input_snapshot": row.input_snapshot,
        "created_at": row.created_at,
        "presentation": artifact.report.get("presentation") if artifact else row.presentation,
        "pdf_id": artifact.id if artifact else None,
    }


@router.get("/preparation-artifacts/{id}/result")
async def exact_target(id: UUID, session: DB, application_id: UUID) -> Any:
    from career_agent.product.results import exact

    return await exact(session, application_id, id)


@router.get("/companies/{id}/research/{research_id}")
async def exact_research(id: UUID, research_id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, e.CompanyResearch, research_id)
    if row.company_id != id:
        raise DomainError("not_found", 404)
    return research_view(row)


@router.get("/applications/{application_id}/greetings/{id}")
async def greeting_delete_check(application_id: UUID, id: UUID, session: DB) -> dict[str, object]:
    from career_agent.product.results import greeting_removal

    return await greeting_removal(session, application_id, id)


@router.delete("/applications/{application_id}/greetings/{id}")
async def greeting_delete(
    application_id: UUID, id: UUID, payload: ResultDelete, session: DB
) -> dict[str, object]:
    from career_agent.product.results import greeting_removal

    return await greeting_removal(session, application_id, id, payload.request_id)


@router.delete("/applications/{application_id}/results/{id}")
async def remove_preparation_result(
    application_id: UUID, id: UUID, payload: ResultDelete, session: DB
) -> dict[str, Any]:
    from career_agent.product.result_lifecycle import remove_target

    return await remove_target(session, application_id, id, payload.request_id)


@router.delete("/companies/{company_id}/research/{id}")
async def remove_research_result(company_id: UUID, id: UUID, session: DB) -> dict[str, Any]:
    from career_agent.product.result_lifecycle import remove_research

    return await remove_research(session, company_id, id)
