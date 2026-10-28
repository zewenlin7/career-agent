"""Metadata-only Internal discovery. Private payloads remain on explicit detail paths."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from career_agent.api.dependencies import DB
from career_agent.api.ops import authorize_operator
from career_agent.api.product import Limit, Offset, rows
from career_agent.evaluation import entities as q
from career_agent.product.contracts import Page

router = APIRouter(prefix="/api/v1/evaluation", dependencies=[Depends(authorize_operator)])


def identity(row: Any) -> dict[str, Any]:
    return {"id": row.id, "created_at": row.created_at}


async def page(
    session: AsyncSession, stmt: Select[Any], limit: int, offset: int, fields: tuple[str, ...]
) -> Page[dict[str, Any]]:
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[{**identity(r), **{k: getattr(r, k) for k in fields}} for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/suites", response_model=Page[dict[str, Any]])
async def suites(
    session: DB, suite_key: str | None = None, limit: Limit = 50, offset: Offset = 0
) -> Any:
    stmt = select(q.EvalSuiteRow).order_by(q.EvalSuiteRow.created_at.desc(), q.EvalSuiteRow.id)
    if suite_key is not None:
        stmt = stmt.where(q.EvalSuiteRow.suite_key == suite_key)
    return await page(session, stmt, limit, offset, ("suite_key", "version"))


@router.get("/runs", response_model=Page[dict[str, Any]])
async def runs(
    session: DB,
    suite_id: UUID | None = None,
    status: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.EvalRunRow).order_by(q.EvalRunRow.created_at.desc(), q.EvalRunRow.id)
    if suite_id is not None:
        stmt = stmt.where(q.EvalRunRow.suite_id == suite_id)
    if status is not None:
        stmt = stmt.where(q.EvalRunRow.status == status)
    return await page(
        session,
        stmt,
        limit,
        offset,
        ("suite_id", "status", "started_at", "finished_at", "reason_code"),
    )


@router.get("/comparisons", response_model=Page[dict[str, Any]])
async def comparisons(
    session: DB,
    baseline_run_id: UUID | None = None,
    candidate_run_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.ComparisonRow).order_by(q.ComparisonRow.created_at.desc(), q.ComparisonRow.id)
    if baseline_run_id is not None:
        stmt = stmt.where(q.ComparisonRow.baseline_id == baseline_run_id)
    if candidate_run_id is not None:
        stmt = stmt.where(q.ComparisonRow.candidate_id == candidate_run_id)
    return await page(
        session, stmt, limit, offset, ("baseline_id", "candidate_id", "policy_version")
    )


@router.get("/judges", response_model=Page[dict[str, Any]])
async def judges(
    session: DB,
    subject_id: UUID | None = None,
    task_type: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    population: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = (
        select(q.JudgeRow, q.SamplingRow)
        .join(q.SamplingRow, q.JudgeRow.sampling_id == q.SamplingRow.id)
        .order_by(q.JudgeRow.created_at.desc(), q.JudgeRow.id)
    )
    for value, column in (
        (subject_id, q.SamplingRow.subject_id),
        (task_type, q.SamplingRow.data["subject"]["task_type"].astext),
        (population, q.SamplingRow.data["population"].astext),
        (status, q.JudgeRow.status),
        (severity, q.JudgeRow.severity),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    found = list((await session.execute(stmt.limit(limit + 1).offset(offset))).all())
    return Page(
        items=[
            {
                **identity(j),
                "sampling_id": j.sampling_id,
                "subject_id": s.subject_id,
                "task_type": s.data["subject"]["task_type"],
                "population": s.data["population"],
                "status": j.status,
                "severity": j.severity,
                "model_call_id": j.model_call_id,
                "reason_code": j.reason_code,
            }
            for j, s in found[:limit]
        ],
        limit=limit,
        offset=offset,
        has_more=len(found) > limit,
    )


@router.get("/captures", response_model=Page[dict[str, Any]])
async def captures(
    session: DB,
    status: str | None = None,
    subject_id: UUID | None = None,
    task_type: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.CaptureRow).order_by(q.CaptureRow.created_at.desc(), q.CaptureRow.id)
    for value, column in (
        (status, q.CaptureRow.status),
        (subject_id, q.CaptureRow.subject_id),
        (task_type, q.CaptureRow.payload["subject"]["task_type"].astext),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return await page(session, stmt, limit, offset, ("subject_id", "status", "content_hash"))


@router.get("/trials", response_model=Page[dict[str, Any]])
async def trials(
    session: DB,
    run_id: UUID | None = None,
    case_id: UUID | None = None,
    status: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.EvalTrialRow).order_by(q.EvalTrialRow.created_at.desc(), q.EvalTrialRow.id)
    for value, column in (
        (run_id, q.EvalTrialRow.run_id),
        (case_id, q.EvalTrialRow.case_id),
        (status, q.EvalTrialRow.status),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return await page(session, stmt, limit, offset, ("run_id", "case_id", "trial_index", "status"))


@router.get("/sampling-records", response_model=Page[dict[str, Any]])
async def sampling_records(
    session: DB,
    subject_id: UUID | None = None,
    task_type: str | None = None,
    sampled: bool | None = None,
    population: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.SamplingRow).order_by(q.SamplingRow.created_at.desc(), q.SamplingRow.id)
    for value, column in (
        (subject_id, q.SamplingRow.subject_id),
        (task_type, q.SamplingRow.data["subject"]["task_type"].astext),
        (population, q.SamplingRow.data["population"].astext),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if sampled is not None:
        stmt = stmt.where(q.SamplingRow.data["sampled"].as_boolean() == sampled)
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[{**identity(r), "subject_id": r.subject_id, **r.data} for r in found],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/suites/{id}")
async def suite(id: UUID, session: DB) -> dict[str, Any]:
    from career_agent.application.services import require

    row = await require(session, q.EvalSuiteRow, id)
    return {**identity(row), "suite": row.data}


@router.get("/case-index", response_model=Page[dict[str, Any]])
async def case_index(
    session: DB,
    tag: str | None = None,
    task_type: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.EvalCaseRow).order_by(q.EvalCaseRow.created_at.desc(), q.EvalCaseRow.id)
    if tag is not None:
        stmt = stmt.where(cast(q.EvalCaseRow.data["tags"], JSONB).contains([tag]))
    if task_type is not None:
        stmt = stmt.where(
            q.EvalCaseRow.data["entrypoint"]["name"].astext == task_type,
            q.EvalCaseRow.data["entrypoint"]["component_kind"].astext == "model_task",
        )
    return await page(session, stmt, limit, offset, ("case_key", "version", "content_hash"))


@router.get("/feedback", response_model=Page[dict[str, Any]])
async def feedback(
    session: DB,
    subject_id: UUID | None = None,
    application_id: UUID | None = None,
    task_type: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    stmt = select(q.FeedbackRow).order_by(q.FeedbackRow.created_at.desc(), q.FeedbackRow.id)
    if subject_id is not None:
        stmt = stmt.where(q.FeedbackRow.subject_id == subject_id)
    if application_id:
        stmt = stmt.where(q.FeedbackRow.data["application_id"].astext == str(application_id))
    if task_type:
        stmt = stmt.where(q.FeedbackRow.data["subject"]["task_type"].astext == task_type)
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[
            {
                **identity(r),
                "subject_id": r.subject_id,
                "vote": r.data["vote"],
                "reason": r.data.get("reason"),
                "comment": r.data.get("comment"),
                "application_id": r.data.get("application_id"),
                "artifact_type": r.data.get("artifact_type"),
                "task_type": r.data["subject"]["task_type"],
                "generation_provenance": r.data.get("generation_provenance", {}),
            }
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )


@router.get("/refinements", response_model=Page[dict[str, Any]])
async def refinements(
    session: DB,
    feedback_id: UUID | None = None,
    source_artifact_id: UUID | None = None,
    source_resume_revision_id: UUID | None = None,
    source_workspace_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Any:
    from career_agent.product.entities import ProductDraft

    stmt = (
        select(ProductDraft)
        .where(
            ProductDraft.task.in_(
                ["resume_refinement", "greeting_refinement", "interview_preparation_refinement"]
            )
        )
        .order_by(ProductDraft.created_at.desc(), ProductDraft.id)
    )
    if feedback_id:
        stmt = stmt.where(ProductDraft.request["feedback_id"].astext == str(feedback_id))
    if source_artifact_id:
        stmt = stmt.where(
            ProductDraft.request["source_artifact_id"].astext == str(source_artifact_id)
        )
    if source_resume_revision_id:
        stmt = stmt.where(
            ProductDraft.context["context"]["source_resume_revision_id"].astext
            == str(source_resume_revision_id)
        )
    if source_workspace_id:
        stmt = stmt.where(
            ProductDraft.request["source_workspace_id"].astext == str(source_workspace_id)
        )
    found, more = await rows(session, stmt, limit, offset)
    return Page(
        items=[
            {
                **identity(r),
                "task": r.task,
                "status": r.status,
                "source_artifact_id": r.request.get("source_artifact_id"),
                "source_resume_revision_id": r.context.get("context", {}).get(
                    "source_resume_revision_id"
                ),
                "source_workspace_id": r.request.get("source_workspace_id"),
                "feedback_id": r.request.get("feedback_id"),
                "application_id": r.request.get("application_id"),
                "intent": r.request.get("intent", "refine"),
                "adopted": r.adopted,
                "run_id": r.run_id,
                "accepted_model_call_id": r.accepted_model_call_id,
            }
            for r in found
        ],
        limit=limit,
        offset=offset,
        has_more=more,
    )
