"""Deterministic current-state intake. No model calls or per-edit content history."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import check_revision, require
from career_agent.domain import schemas as s
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e


def validate_entries(entries: list[s.InterviewEntry]) -> None:
    ids = {v.entry_id: v for v in entries}
    if len(ids) != len(entries) or len({v.order for v in entries}) != len(entries):
        raise DomainError("duplicate_interview_entry", 422)
    for entry in entries:
        if entry.kind == "follow_up":
            parent = ids.get(entry.primary_entry_id) if entry.primary_entry_id else None
            if parent is None or parent.kind != "primary" or parent.order >= entry.order:
                raise DomainError("invalid_primary_reference", 422)


async def update(session: AsyncSession, id: UUID, payload: s.InterviewUpdate) -> e.InterviewSession:
    row = await require(session, e.InterviewSession, id, lock=True)
    check_revision(row.content_revision, payload.expected_revision)
    if payload.round_name is not None:
        row.round_name = payload.round_name
    if "occurred_at" in payload.model_fields_set:
        row.occurred_at = payload.occurred_at
    if payload.entries is not None:
        validate_entries(payload.entries)
        row.entries = [
            x.model_dump(mode="json") for x in sorted(payload.entries, key=lambda x: x.order)
        ]
    row.content_revision += 1
    await session.flush()
    return row


async def append(
    session: AsyncSession, id: UUID, payload: s.InterviewEntryCreate
) -> e.InterviewSession:
    row = await require(session, e.InterviewSession, id, lock=True)
    check_revision(row.content_revision, payload.expected_revision)
    entries = [s.InterviewEntry.model_validate(v) for v in row.entries] + [payload.entry]
    if len(entries) > 500:
        raise DomainError("interview_entry_limit", 422)
    return await update(
        session, id, s.InterviewUpdate(expected_revision=payload.expected_revision, entries=entries)
    )
