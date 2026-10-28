"""Product profile identity stays stable while execution snapshots remain immutable."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select, text

from career_agent.api.dependencies import DB
from career_agent.application.services import check_revision, require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.product.entities import ApplicationBinding
from career_agent.profile_area import contracts as c
from career_agent.profile_area import service as s
from career_agent.profile_area.entities import ProfileRecord, ProfileRecordSnapshot

router = APIRouter(prefix="/api/v1/profile-library")


def view(row: ProfileRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "revision": row.revision,
        "data": c.WorkspaceData.model_validate(row.data).model_dump(mode="json"),
        "profile_id": row.profile_id,
        "section_revisions": row.section_revisions,
        "created_at": row.created_at,
        "saved_at": row.saved_at,
    }


@router.get("")
async def list_records(session: DB) -> dict[str, Any]:
    rows = await session.scalars(
        select(ProfileRecord)
        .where(ProfileRecord.archived_at.is_(None))
        .order_by(ProfileRecord.number.desc())
    )
    return {"items": [view(r) for r in rows]}


@router.post("", status_code=201)
async def create(session: DB, payload: c.ProfileCreate | None = None) -> dict[str, Any]:
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    if payload and payload.request_id:
        existing = await session.scalar(
            select(ProfileRecord).where(ProfileRecord.request_id == payload.request_id)
        )
        if existing:
            return view(existing)
    number = (await session.scalar(select(func.max(ProfileRecord.number))) or 0) + 1
    row = ProfileRecord(
        request_id=payload.request_id if payload else None,
        number=number,
        name=f"个人资料 {number}",
        data=c.WorkspaceData().model_dump(mode="json"),
        section_revisions={section: 1 for section in s.SECTIONS},
    )
    session.add(row)
    await session.flush()
    return view(row)


async def record(session: DB, id: UUID) -> ProfileRecord:
    # Same global lock order as legacy publication; no owner/global lock inversion.
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    row = await require(session, ProfileRecord, id, lock=True)
    if row.archived_at:
        raise DomainError("not_found", 404)
    return row


@router.get("/{id}")
async def get(id: UUID, session: DB) -> dict[str, Any]:
    return view(await record(session, id))


@router.patch("/{id}")
async def rename(id: UUID, payload: c.Rename, session: DB) -> dict[str, Any]:
    row = await record(session, id)
    check_revision(row.revision, payload.expected_revision)
    if row.name != payload.name:
        row.name = payload.name
        row.revision += 1
        row.saved_at = e.utcnow()
    return view(row)


@router.patch("/{id}/sections/{section}")
async def save(
    id: UUID, section: c.Section, payload: c.SectionWrite, session: DB
) -> dict[str, Any]:
    from pydantic import ValidationError

    row = await record(session, id)
    previous_data = row.data
    if payload.record_name is not None and payload.record_name != row.name:
        if payload.expected_record_revision is None:
            raise DomainError("revision_conflict")
        check_revision(row.revision, payload.expected_record_revision)
        row.name = payload.record_name
        row.revision += 1
        row.saved_at = e.utcnow()
    try:
        await s.save_record_section(session, row, section, payload)
    except ValidationError:
        raise DomainError("invalid_profile_section", 422) from None
    if row.data != previous_data:
        row.saved_at = e.utcnow()
    if row.data != previous_data and row.data.get("display_name", "").strip():
        snapshot = await s.publish_data(session, row.data, update_current=False)
        row.profile_id = snapshot.id
        if await session.get(ProfileRecordSnapshot, (row.id, snapshot.id)) is None:
            session.add(ProfileRecordSnapshot(record_id=row.id, profile_id=snapshot.id))
    await session.flush()
    return view(row)


@router.get("/{id}/history")
async def history(id: UUID, session: DB) -> dict[str, Any]:
    await record(session, id)
    rows = await session.scalars(
        select(e.PersonalProfile)
        .join(ProfileRecordSnapshot, ProfileRecordSnapshot.profile_id == e.PersonalProfile.id)
        .where(ProfileRecordSnapshot.record_id == id)
        .order_by(e.PersonalProfile.revision.desc())
    )
    return {"items": [{"id": r.id, "created_at": r.created_at, "data": r.data} for r in rows]}


@router.delete("/{id}")
async def delete(id: UUID, payload: c.Publish, session: DB) -> dict[str, bool]:
    row = await record(session, id)
    check_revision(row.revision, payload.expected_revision)
    ids = select(ProfileRecordSnapshot.profile_id).where(ProfileRecordSnapshot.record_id == id)
    if await session.scalar(
        select(ApplicationBinding.application_id)
        .where(ApplicationBinding.profile_id.in_(ids))
        .limit(1)
    ):
        raise DomainError("profile_in_use")
    row.archived_at = e.utcnow()
    row.revision += 1
    return {"deleted": True}


@router.post("/{id}/editing")
async def begin_edit(id: UUID, payload: c.Publish, session: DB) -> dict[str, Any]:
    from uuid import uuid4

    row = await record(session, id)
    check_revision(row.revision, payload.expected_revision)
    if row.editing is None:
        row.editing = {
            "id": str(uuid4()),
            "revision": 1,
            "base": row.data,
            "data": row.data,
        }
    await session.flush()
    return row.editing


def checked_edit(row: ProfileRecord, payload: c.ProfileEditFinish) -> dict[str, Any]:
    state = row.editing
    if state is None or state["id"] != str(payload.edit_id):
        raise DomainError("revision_conflict")
    check_revision(state["revision"], payload.expected_revision)
    return state


@router.put("/{id}/editing")
async def save_edit(id: UUID, payload: c.ProfileEditWrite, session: DB) -> dict[str, Any]:
    from career_agent.profile_area.entities import ProfilePhoto

    row = await record(session, id)
    state = checked_edit(row, c.ProfileEditFinish(**payload.model_dump(exclude={"data"})))
    if payload.data.personal.photo_id:
        await require(session, ProfilePhoto, payload.data.personal.photo_id)
    from uuid import uuid4

    if payload.data.skills_text != state["data"].get("skills_text", ""):
        payload.data.skills = [
            line.strip() for line in payload.data.skills_text.splitlines() if line.strip()
        ]
    import re

    previous = {
        entry.get("entry_id"): entry
        for key in ["education", "experiences", "projects"]
        for entry in state["data"].get(key, [])
    }
    for entry in payload.data.education + payload.data.experiences + payload.data.projects:
        old = previous.get(str(entry.entry_id), {})
        for key in ["start_date", "end_date"]:
            value = getattr(entry, key).strip()
            if (
                value
                and value != old.get(key)
                and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value)
            ):
                raise DomainError("invalid_profile_date", 422)
            setattr(entry, key, value)
        entry.entry_id = entry.entry_id or uuid4()
    data = payload.data.model_dump(mode="json")
    if data != state["data"]:
        row.editing = {**state, "data": data, "revision": state["revision"] + 1}
    await session.flush()
    return row.editing or state


@router.post("/{id}/editing/commit")
async def commit_edit(id: UUID, payload: c.ProfileEditFinish, session: DB) -> dict[str, Any]:
    row = await record(session, id)
    state = checked_edit(row, payload)
    # A legacy section save or another writer cannot be overwritten by an old editor.
    if row.data != state["base"]:
        raise DomainError("revision_conflict")
    data = c.WorkspaceData.model_validate(state["data"])
    if not data.display_name.strip():
        raise DomainError("invalid_profile_section", 422)
    result = data.model_dump(mode="json")
    if result != row.data:
        snapshot = await s.publish_data(session, result, update_current=False)
        row.data = result
        row.revision += 1
        row.saved_at = e.utcnow()
        row.section_revisions = {key: value + 1 for key, value in row.section_revisions.items()}
        row.profile_id = snapshot.id
        if await session.get(ProfileRecordSnapshot, (row.id, snapshot.id)) is None:
            session.add(ProfileRecordSnapshot(record_id=row.id, profile_id=snapshot.id))
    row.editing = None
    await session.flush()
    return view(row)


@router.post("/{id}/editing/cancel")
async def cancel_edit(id: UUID, payload: c.ProfileEditFinish, session: DB) -> dict[str, Any]:
    row = await record(session, id)
    checked_edit(row, payload)
    row.editing = None
    await session.flush()
    return view(row)
