"""Archive protection applies to active owners; historical bindings remain intact."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.infrastructure import entities as e
from career_agent.product.entities import ApplicationBinding


async def in_use(
    session: AsyncSession, *, profiles: list[UUID] | None = None, resume: UUID | None = None
) -> bool:
    condition = (
        ApplicationBinding.profile_id.in_(profiles)
        if profiles is not None
        else ApplicationBinding.resume_revision_id == resume
    )
    return (
        await session.scalar(
            select(ApplicationBinding.application_id)
            .join(e.Application, e.Application.id == ApplicationBinding.application_id)
            .where(e.Application.deleted_at.is_(None), condition)
            .limit(1)
        )
        is not None
    )
