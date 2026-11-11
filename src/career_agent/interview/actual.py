"""Deterministic current-state intake. No model calls or per-edit content history."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import active_interview_target, check_revision, require
from career_agent.domain import schemas as s
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.interview.numbering import numbered


def validate_entries(entries: list[s.InterviewEntry]) -> None:
    ids = {v.entry_id: v for v in entries}
    if len(ids) != len(entries) or len({v.order for v in entries}) != len(entries):
        raise DomainError("duplicate_interview_entry", 422)
    for entry in entries:
        if entry.kind == "follow_up":
            parent = ids.get(entry.primary_entry_id) if entry.primary_entry_id else None
            if parent is None or parent.kind != "primary" or parent.order >= entry.order:
                raise DomainError("invalid_primary_reference", 422)


async def check_round(
    session: AsyncSession,
    application_id: UUID,
    round_number: int | None,
    exclude: UUID | None = None,
) -> None:
    # All intake writers hold the Application lock. Legacy duplicates remain readable/editable
    # when their round is unchanged; new assignments cannot collide with them.
    if round_number is None:
        return
    query = select(e.InterviewSession.id).where(
        e.InterviewSession.application_id == application_id,
        e.InterviewSession.round_number == round_number,
    )
    if exclude is not None:
        query = query.where(e.InterviewSession.id != exclude)
    if await session.scalar(query.limit(1)):
        raise DomainError("interview_round_conflict")


async def update(session: AsyncSession, id: UUID, payload: s.InterviewUpdate) -> e.InterviewSession:
    row = await require(session, e.InterviewSession, id, lock=True)
    await active_interview_target(session, row)
    check_revision(row.content_revision, payload.expected_revision)
    if payload.round_number is not None and payload.round_number != row.round_number:
        await check_round(session, row.application_id, payload.round_number, row.id)
    before = {
        key: getattr(row, key)
        for key in (
            "round_name",
            "occurred_at",
            "entries",
            "status",
            "round_number",
            "interview_type",
            "notes",
        )
    }
    if payload.round_name is not None:
        row.round_name = payload.round_name
    if "occurred_at" in payload.model_fields_set:
        row.occurred_at = payload.occurred_at
    if payload.entries is not None:
        validate_entries(payload.entries)
        previous = [s.InterviewEntry.model_validate(v) for v in row.entries]
        if any(v.main_question_number is None for v in previous):
            previous = numbered(previous)
        row.entries = [
            x.model_dump(mode="json")
            for x in sorted(numbered(payload.entries, previous), key=lambda x: x.order)
        ]
    if (
        payload.status == "completed"
        or (payload.entries is not None and row.status == "completed" and payload.status != "draft")
    ) and not any(e["kind"] == "primary" for e in row.entries):
        raise DomainError("interview_questions_required", 422)
    for name in ("status", "round_number", "interview_type"):
        if getattr(payload, name) is not None:
            setattr(row, name, getattr(payload, name))
    if payload.notes_text is not None:
        text = payload.notes_text.strip()
        # A flattened editor value is not permission to erase historical note boundaries/times.
        if payload.notes_text != "\n".join(note["text"] for note in row.notes):
            row.notes = (
                [s.InterviewNoteData(text=text, recorded_at=e.utcnow().isoformat()).model_dump()]
                if text
                else []
            )
    if all(getattr(row, key) == value for key, value in before.items()):
        return row
    row.content_revision += 1
    row.saved_at = e.utcnow()
    await session.flush()
    return row


async def append(
    session: AsyncSession, id: UUID, payload: s.InterviewEntryCreate
) -> e.InterviewSession:
    row = await require(session, e.InterviewSession, id, lock=True)
    await active_interview_target(session, row)
    check_revision(row.content_revision, payload.expected_revision)
    entries = [s.InterviewEntry.model_validate(v) for v in row.entries] + [payload.entry]
    if len(entries) > 500:
        raise DomainError("interview_entry_limit", 422)
    return await update(
        session, id, s.InterviewUpdate(expected_revision=payload.expected_revision, entries=entries)
    )
