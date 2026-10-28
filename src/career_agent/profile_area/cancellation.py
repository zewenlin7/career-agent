"""Request-lifetime cancellation, not a background worker or crash recovery mechanism."""

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import require
from career_agent.domain.rules import DomainError, RunStatus
from career_agent.infrastructure import entities as e
from career_agent.product.drafts import DraftService
from career_agent.product.entities import ProductDraft

active: dict[UUID, asyncio.Task[dict[str, Any]]] = {}


async def execute(service: DraftService, id: UUID) -> dict[str, Any]:
    if id in active:
        raise DomainError("operation_in_progress")
    task = asyncio.create_task(service.execute(id))
    active[id] = task
    try:
        return await task
    except asyncio.CancelledError:
        # Gateway/InterviewCalls finish conservative usage settlement before this point.
        return await mark_cancelled(service.sessions, id)
    finally:
        if active.get(id) is task:
            del active[id]


async def mark_cancelled(sessions: async_sessionmaker[AsyncSession], id: UUID) -> dict[str, Any]:
    async with sessions.begin() as session:
        row = await require(session, ProductDraft, id, lock=True)
        if row.status in {"pending", "running"}:
            row.status, row.reason, row.output = "cancelled", None, None
            run = await require(session, e.AgentRun, row.run_id)
            run.status, run.finished_at = RunStatus.CANCELLED, e.utcnow()
        return DraftService.view(row)


async def cancel(sessions: async_sessionmaker[AsyncSession], id: UUID) -> dict[str, Any]:
    task = active.get(id)
    if task:
        task.cancel()
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass
        return await mark_cancelled(sessions, id)
    async with sessions.begin() as session:
        row = await require(session, ProductDraft, id, lock=True)
        if row.status == "running":
            # A different process/unrecoverable request is not falsely reported as stopped.
            raise DomainError("recovery_decision_required")
    return await mark_cancelled(sessions, id)
