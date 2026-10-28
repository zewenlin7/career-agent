"""User editing is durable; publication alone creates immutable execution context."""

from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application import resumes
from career_agent.application.services import check_revision, put_profile, require
from career_agent.domain.rules import DomainError, FactStatus
from career_agent.domain.schemas import ProfileData, ProfileWrite
from career_agent.infrastructure import entities as e
from career_agent.product.entities import ApplicationBinding
from career_agent.profile_area import contracts as c
from career_agent.profile_area.entities import ProfilePhoto, ProfileWorkspace, ResumeWorkspace
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.schemas import ResumeDocument

SECTIONS = ("personal", "education", "experiences", "projects", "skills", "preferences")


async def workspace(session: AsyncSession) -> ProfileWorkspace:
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    row = await session.get(ProfileWorkspace, "personal")
    if row is None:
        latest = await session.scalar(
            select(e.PersonalProfile)
            .where(e.PersonalProfile.archived_at.is_(None))
            .order_by(e.PersonalProfile.revision.desc())
        )
        data = c.WorkspaceData.model_validate(latest.data if latest else {})
        for education in data.education:
            if not education.degree and education.role:
                education.degree, education.role = education.role, ""
        for entry in data.education + data.experiences + data.projects:
            entry.entry_id = entry.entry_id or uuid4()
        row = ProfileWorkspace(
            key="personal",
            current_profile_id=latest.id if latest else None,
            base_profile_id=latest.id if latest else None,
            data=data.model_dump(mode="json"),
            section_revisions={s: 1 for s in SECTIONS},
        )
        session.add(row)
        await session.flush()
    return row


def view(row: ProfileWorkspace) -> dict[str, Any]:
    return {
        "revision": row.revision,
        "base_profile_id": row.base_profile_id,
        "current_profile_id": row.current_profile_id,
        "data": row.data,
        "section_revisions": row.section_revisions,
    }


async def save_section(
    session: AsyncSession, section: c.Section, request: c.SectionWrite
) -> ProfileWorkspace:
    row = await workspace(session)
    await save_record_section(session, row, section, request)
    return row


async def save_record_section(
    session: AsyncSession, row: Any, section: c.Section, request: c.SectionWrite
) -> Any:
    check_revision(row.section_revisions[section], request.expected_revision)
    payload = dict(row.data)
    if section == "personal":
        info = c.Information.model_validate(request.value)
        payload["display_name"] = info.display_name
        payload["personal"] = info.model_dump(mode="json", exclude={"display_name"})
        if info.photo_id:
            await require(session, ProfilePhoto, info.photo_id)
    elif section == "skills":
        if not isinstance(request.value, str):
            raise DomainError("invalid_request", 422)
        payload["skills_text"] = request.value
        # Keep line structure for existing model-task consumers. Do not split categories/items.
        payload["skills"] = [line.strip() for line in request.value.splitlines() if line.strip()]
    else:
        payload[section] = request.value
    try:
        data = c.WorkspaceData.model_validate(payload)
    except ValidationError:
        raise DomainError("invalid_profile_section", 422) from None
    for entry in data.education + data.experiences + data.projects:
        entry.entry_id = entry.entry_id or uuid4()
    result = data.model_dump(mode="json")

    def comparable(value: dict[str, Any]) -> dict[str, Any]:
        value = c.WorkspaceData.model_validate(value).model_dump(mode="json")
        for key in ["education", "experiences", "projects"]:
            for entry in value[key]:
                entry.pop("entry_id", None)
                if key == "education" and not entry["degree"] and entry["role"]:
                    entry["degree"], entry["role"] = entry["role"], ""
        return value

    if comparable(result) != comparable(row.data):
        row.data = result
        row.revision += 1
        row.section_revisions = {
            **row.section_revisions,
            section: row.section_revisions[section] + 1,
        }
    await session.flush()
    return row


async def publish_data(
    session: AsyncSession, data: dict[str, Any], *, update_current: bool = True
) -> e.PersonalProfile:
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    payload = ProfileData.model_validate(data)
    payload.fact_ids = list(
        await session.scalars(
            select(e.PersonalFact.id)
            .where(
                e.PersonalFact.status == FactStatus.VERIFIED, e.PersonalFact.archived_at.is_(None)
            )
            .order_by(e.PersonalFact.id)
        )
    )
    allowed = set(payload.fact_ids)
    for entry in payload.education + payload.experiences + payload.projects:
        entry.fact_ids = [id for id in entry.fact_ids if id in allowed]
    latest = await session.scalar(select(func.max(e.PersonalProfile.revision))) or 0
    work = await session.get(ProfileWorkspace, "personal")
    if update_current and work:
        current = (
            await session.get(e.PersonalProfile, work.current_profile_id)
            if work.current_profile_id
            else None
        )
        latest = current.revision if current else 0
    return await put_profile(
        session, ProfileWrite(expected_revision=latest, data=payload), update_current=update_current
    )


async def publish(session: AsyncSession, request: c.Publish) -> e.PersonalProfile:
    row = await workspace(session)
    check_revision(row.revision, request.expected_revision)
    if row.current_profile_id and row.base_profile_id != row.current_profile_id:
        raise DomainError("profile_workspace_outdated")
    result = await publish_data(session, row.data)
    row.current_profile_id = result.id
    if row.base_profile_id != result.id:
        row.base_profile_id = result.id
        row.data = result.data
        row.revision += 1
    return result


async def restore(session: AsyncSession, request: c.Restore) -> ProfileWorkspace:
    row = await workspace(session)
    check_revision(row.revision, request.expected_revision)
    historical = await require(session, e.PersonalProfile, request.profile_id)
    row.data = c.WorkspaceData.model_validate(historical.data).model_dump(mode="json")
    row.base_profile_id = row.current_profile_id
    row.revision += 1
    row.section_revisions = {s: r + 1 for s, r in row.section_revisions.items()}
    return row


async def archive_profile(session: AsyncSession, id: UUID) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    row = await require(session, e.PersonalProfile, id, lock=True)
    if await session.scalar(
        select(ApplicationBinding.application_id)
        .where(ApplicationBinding.profile_id == id)
        .limit(1)
    ):
        raise DomainError("profile_in_use")
    # Archival, not deletion: all exact reads and historic references remain valid.
    row.archived_at = row.archived_at or e.utcnow()
    work = await session.get(ProfileWorkspace, "personal")
    if work:
        if work.current_profile_id == id:
            work.current_profile_id = None
        if work.base_profile_id == id:
            work.base_profile_id = None
        work.revision += 1


def draft_document(data: ProfileData | c.WorkspaceData) -> c.ResumeDraftData:
    sections: list[c.DraftSection] = []
    from hashlib import sha256

    from career_agent.domain.schemas import Experience
    from career_agent.resume.schemas import EntryLayout, SectionName

    sources: list[tuple[list[Experience], SectionName]] = [
        (list(data.education), "education"),
        (list(data.experiences), "experience"),
        (list(data.projects), "projects"),
    ]
    for source, name in sources:
        items: list[c.DraftItem] = []
        for entry in source:
            fields = entry.model_dump(mode="json")
            parts = [entry.organization]
            dates: list[int] = []
            subtitles: list[int] = []
            for key in [
                "degree",
                "major",
                "role",
                "start_date",
                "end_date",
                "technology_stack",
                "description",
                "achievements",
            ]:
                if key not in entry.hidden_fields and fields.get(key):
                    if key in {"start_date", "end_date"}:
                        dates.append(len(parts))
                    elif key in {"degree", "major", "role", "technology_stack"}:
                        subtitles.append(len(parts))
                    parts.extend(str(fields[key]).split("\n"))
            items.append(
                c.DraftItem(
                    item_id=uuid4(),
                    kind="entry",
                    text="\n".join(parts),
                    layout=EntryLayout(
                        text_sha256=sha256("\n".join(parts).encode()).hexdigest(),
                        date_lines=dates,
                        subtitle_lines=subtitles,
                    ),
                    fact_refs=entry.fact_ids,
                    priority=50,
                    ordering=len(items),
                )
            )
        if items:
            sections.append(
                c.DraftSection(
                    section_id=uuid4(), name=name, ordering=len(sections), priority=50, items=items
                )
            )
    skills = data.skills_text or "\n".join(data.skills)
    if skills.strip():
        sections.append(
            c.DraftSection(
                section_id=uuid4(),
                name="skills",
                ordering=len(sections),
                priority=50,
                items=[
                    c.DraftItem(item_id=uuid4(), kind="entry", text=skills, priority=50, ordering=0)
                ],
            )
        )
    return c.ResumeDraftData(sections=sections)


async def create_draft(
    session: AsyncSession, request: c.ResumeCreate | None = None
) -> ResumeWorkspace:
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    request = request or c.ResumeCreate()
    if request.request_id:
        existing = await session.scalar(
            select(ResumeWorkspace).where(ResumeWorkspace.request_id == request.request_id)
        )
        if existing:
            if existing.profile_id != request.profile_id:
                raise DomainError("idempotency_conflict")
            return existing
    profile_id: UUID | None
    if request.profile_id:
        profile = await require(session, e.PersonalProfile, request.profile_id)
        if profile.archived_at:
            raise DomainError("profile_in_use")
        source_data, profile_id = profile.data, profile.id
    else:
        source = await workspace(session)
        source_data, profile_id = source.data, source.base_profile_id
    data = c.WorkspaceData.model_validate(source_data)
    number = await next_resume_number(session)
    row = ResumeWorkspace(
        name=f"简历 {number}",
        number=number,
        request_id=request.request_id,
        source=source_data,
        profile_id=profile_id,
        document=draft_document(data).model_dump(mode="json"),
    )
    from career_agent.profile_area.evidence import user_sources

    row.content_sources = user_sources(row.document, "profile")
    session.add(row)
    await session.flush()
    return row


async def review_draft(session: AsyncSession, row: ResumeWorkspace) -> list[e.PersonalFact]:
    result = []
    for section in c.ResumeDraftData.model_validate(row.document).sections:
        for item in section.items:
            locator = f"resume-draft:{row.id}:{item.item_id}"
            fact = await session.scalar(
                select(e.PersonalFact)
                .where(
                    e.PersonalFact.statement == item.text,
                    e.PersonalFact.status.in_([FactStatus.PROPOSED, FactStatus.VERIFIED]),
                    e.PersonalFact.archived_at.is_(None),
                )
                .order_by(e.PersonalFact.created_at)
                .limit(1)
            )
            if fact is None:
                fact = e.PersonalFact(
                    statement=item.text,
                    category={
                        "projects": "project",
                        "skills": "skill",
                        "experience": "experience",
                        "education": "education",
                        "summary": "general",
                    }[section.name],
                    source_locator=locator,
                )
                session.add(fact)
                await session.flush()
            result.append(fact)
    return result


async def accept_draft(session: AsyncSession, row: ResumeWorkspace) -> e.ResumeVariantRevision:
    if row.accepted_revision_id:
        return await require(session, e.ResumeVariantRevision, row.accepted_revision_id)
    data = c.ResumeDraftData.model_validate(row.document)
    facts = list(
        await session.scalars(
            select(e.PersonalFact)
            .where(
                e.PersonalFact.status == FactStatus.VERIFIED, e.PersonalFact.archived_at.is_(None)
            )
            .with_for_update()
        )
    )
    for section in data.sections:
        for item in section.items:
            # Only exact user-confirmed text gets automatic association. No heuristic truth claim.
            matched = [f.id for f in facts if f.statement == item.text]
            item.fact_refs = matched or item.fact_refs
            if not item.fact_refs:
                raise DomainError("resume_draft_needs_review", 422)
    profile = await publish_data(session, row.source, update_current=False)
    original = (
        await require(session, e.ResumeVariantRevision, row.source_resume_revision_id)
        if row.source_resume_revision_id
        else None
    )
    job_id = original.job_revision_id if original else None
    requirement_ids = (
        set(
            await session.scalars(
                select(e.JobRequirement.id).where(e.JobRequirement.job_revision_id == job_id)
            )
        )
        if job_id
        else set()
    )
    document = ResumeDocument(
        job_revision_id=job_id,
        profile_id=profile.id,
        profile_revision=profile.revision,
        sections=data.model_dump(mode="json")["sections"],
    )
    snapshot = await resumes.snapshot_for(session, document)
    findings = validate_grounding(
        document,
        snapshot,
        resumes.profile_fact_ids(profile),
        {f.id: FactEvidence(f.id, f.revision, f.status, f.statement) for f in facts},
        requirement_ids,
    )
    if findings:
        raise DomainError("grounding_failed", 422)
    if original is not None:
        head = await require(session, e.ResumeVariant, original.resume_variant_id, lock=True)
        saved = await resumes.revise_variant(session, head.id, head.current_revision, document)
    else:
        saved = await resumes.create_variant(session, document, library_number=row.number)
    if original is not None:
        from career_agent.profile_area.naming import branch

        saved.library_state = await branch(session, original)
        if row.name != original.display_name:
            saved.library_state = {"branch_id": str(uuid4()), "branch_name": row.name}
    saved.library_state = {
        **(saved.library_state or {}),
        **(row.library_state or {}),
    }
    saved.presentation = row.presentation or {}
    if row.name != "简历草稿":
        saved.display_name = row.name
    row.accepted_revision_id = saved.id
    row.revision += 1
    return saved


async def refresh_current_fact_scope(session: AsyncSession) -> None:
    """Explicit fact decisions freeze a new scope; old Application bindings stay exact."""
    row = await workspace(session)
    from career_agent.profile_area.entities import ProfileRecord, ProfileRecordSnapshot

    records = await session.scalars(
        select(ProfileRecord)
        .where(ProfileRecord.archived_at.is_(None), ProfileRecord.profile_id.is_not(None))
        .order_by(ProfileRecord.id)
        .with_for_update()
    )
    for record in records:
        assert record.profile_id is not None
        old = await require(session, e.PersonalProfile, record.profile_id)
        verified_ids = list(
            await session.scalars(
                select(e.PersonalFact.id)
                .where(
                    e.PersonalFact.status == FactStatus.VERIFIED,
                    e.PersonalFact.archived_at.is_(None),
                )
                .order_by(e.PersonalFact.id)
            )
        )
        if set(ProfileData.model_validate(old.data).fact_ids) == set(verified_ids):
            continue
        snapshot = await publish_data(session, record.data, update_current=False)
        record.profile_id = snapshot.id
        record.data = {**record.data, "fact_ids": snapshot.data["fact_ids"]}
        record.revision += 1
        if await session.get(ProfileRecordSnapshot, (record.id, snapshot.id)) is None:
            session.add(ProfileRecordSnapshot(record_id=record.id, profile_id=snapshot.id))
    if row.current_profile_id is None:
        return
    previous_id = row.current_profile_id
    current = await require(session, e.PersonalProfile, previous_id)
    result = await publish_data(session, current.data)
    if result.id == previous_id:
        return
    row.current_profile_id = result.id
    if row.base_profile_id == previous_id:
        row.base_profile_id = result.id
        row.data = {**row.data, "fact_ids": result.data["fact_ids"]}
    row.revision += 1


async def next_resume_number(session: AsyncSession) -> int:
    await session.execute(text("SELECT pg_advisory_xact_lock(78420109)"))
    roots = list(
        await session.scalars(
            select(ResumeWorkspace).where(
                ResumeWorkspace.parent_id.is_(None),
                ResumeWorkspace.source_resume_revision_id.is_(None),
            )
        )
    )
    active_variants = set(
        await session.scalars(
            select(e.ResumeVariantRevision.resume_variant_id)
            .join(e.ResumeVariant)
            .where(
                e.ResumeVariantRevision.archived_at.is_(None),
                e.ResumeVariant.library_visible.is_(True),
            )
        )
    )
    materialized = {
        id: variant
        for id, variant in (
            await session.execute(
                select(e.ResumeVariantRevision.id, e.ResumeVariantRevision.resume_variant_id).where(
                    e.ResumeVariantRevision.id.in_(
                        [r.accepted_revision_id for r in roots if r.accepted_revision_id]
                    )
                )
            )
        ).all()
    }
    used = {
        r.number
        for r in roots
        if (
            (r.accepted_revision_id and materialized.get(r.accepted_revision_id) in active_variants)
            or (not r.accepted_revision_id and r.archived_at is None)
        )
    }
    linked = select(ResumeWorkspace.accepted_revision_id).where(
        ResumeWorkspace.accepted_revision_id.is_not(None)
    )
    used.update(
        await session.scalars(
            select(e.ResumeVariantRevision.library_number).where(
                e.ResumeVariantRevision.revision == 1,
                e.ResumeVariantRevision.resume_variant_id.in_(active_variants),
                e.ResumeVariantRevision.id.not_in(linked),
            )
        )
    )
    number = 1
    while number in used:
        number += 1
    return number
