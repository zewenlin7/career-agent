"""Project owner reachability without changing historical execution outcomes."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.infrastructure import entities as e
from career_agent.interview.ownership import mock_owner
from career_agent.product.entities import ProductDraft, ProductOperation


def identifier(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


async def task_workspace(session: AsyncSession, family: str, id: UUID) -> dict[str, Any] | None:
    owner = None
    jd_id = None
    if family == "operations":
        operation = await session.get(ProductOperation, id)
        if operation:
            owner = identifier(operation.payload.get("application_id"))
            binding = operation.payload.get("application_binding") or {}
            owner = owner or identifier(binding.get("application_id"))
            jd_id = identifier(operation.payload.get("request", {}).get("job_revision_id"))
    elif family == "product-drafts":
        draft = await session.get(ProductDraft, id)
        if draft:
            owner = identifier(draft.request.get("application_id"))
            context = draft.context.get("context", {})
            jd_id = identifier(context.get("job_revision_id"))
    elif family == "mock-interviews":
        mock = await session.get(e.MockInterviewSession, id)
        if mock:
            owner = await mock_owner(session, mock)
    elif family == "interview-debriefs":
        review = await session.get(e.DebriefRun, id)
        if review:
            source = identifier(review.snapshot.get("interview_id"))
            if source and review.snapshot.get("source_kind") == "actual":
                interview = await session.get(e.InterviewSession, source)
                owner = interview.application_id if interview else None
            elif source:
                mock = await session.get(e.MockInterviewSession, source)
                if mock:
                    owner = await mock_owner(session, mock)
    if owner is None and jd_id:
        # Job has a unique Application relation; this is not a title/name inference.
        owner = await session.scalar(
            select(e.Application.id)
            .join(e.JobRevision, e.JobRevision.job_id == e.Application.job_id)
            .where(e.JobRevision.id == jd_id)
        )
    if owner is None:
        return None
    application = await session.get(e.Application, owner)
    available = application is not None and application.deleted_at is None
    return {
        "application_id": str(owner),
        "available": available,
        "reason": None if available else "application_deleted",
    }
