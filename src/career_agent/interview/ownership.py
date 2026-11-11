"""Read-only legacy ownership resolution from exact persisted source relationships."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.infrastructure import entities as e


async def legacy_owner(
    session: AsyncSession,
    binding: dict[str, Any],
    job_id: str | None = None,
    *,
    created_at: datetime | None = None,
) -> UUID | None:
    try:
        jd_id = UUID(binding["job_revision_id"])
        profile_id = UUID(binding["profile_id"])
        resume_id = (
            UUID(binding["resume_revision_id"]) if binding.get("resume_revision_id") else None
        )
    except (KeyError, ValueError, TypeError):
        return None
    jd = await session.get(e.JobRevision, jd_id)
    if jd is None or (job_id is not None and str(jd.job_id) != job_id):
        return None
    if resume_id:
        resume = await session.get(e.ResumeVariantRevision, resume_id)
        if resume is None or resume.profile_id != profile_id:
            return None
    elif await session.get(e.PersonalProfile, profile_id) is None:
        return None
    # This is the existing unique relational Job owner, never a company/title match.
    owners = list(
        await session.scalars(select(e.Application).where(e.Application.job_id == jd.job_id))
    )
    if len(owners) != 1 or (created_at is not None and owners[0].created_at > created_at):
        return None
    return owners[0].id


async def mock_owner(session: AsyncSession, row: e.MockInterviewSession) -> UUID | None:
    if row.application_id is not None:
        return row.application_id
    binding = row.context.get("binding", {})
    owner = await legacy_owner(
        session, binding, row.context.get("job_id"), created_at=row.created_at
    )
    if owner is None:
        return None
    profile = await session.get(e.PersonalProfile, UUID(binding["profile_id"]))
    jd = await session.get(e.JobRevision, UUID(binding["job_revision_id"]))
    if (
        profile is None
        or jd is None
        or row.context.get("profile_revision") != profile.revision
        or row.context.get("job_revision") != jd.revision
    ):
        return None
    return owner
