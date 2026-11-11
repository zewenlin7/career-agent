"""Live Mock execution ownership, independent of a durable in-progress flag."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def available(session: AsyncSession, id: UUID) -> bool:
    return bool(
        await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 4309))"),
            {"key": str(id)},
        )
    )
