from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.domain import schemas as s
from career_agent.domain.rules import (
    ApplicationStatus,
    DomainError,
    application_status,
    transition_application,
    verify_fact,
)
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.db import Base


async def require[T: Base](
    session: AsyncSession, cls: type[T], row_id: UUID, *, lock: bool = False
) -> T:
    statement = select(cls).where(cls.id == row_id)  # type: ignore[attr-defined]
    if cls in (e.PreparationArtifact, e.CompanyResearch) and not lock:
        statement = statement.with_for_update(read=True).execution_options(populate_existing=True)
    if lock or cls is e.Application:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(statement)
    if row is None or (isinstance(row, e.Application) and row.deleted_at is not None):
        raise DomainError("not_found", 404)
    return row


async def read_application(session: AsyncSession, id: UUID) -> e.Application:
    """MVCC read for navigation; writers/admissions retain their existing locks."""
    row = await session.scalar(select(e.Application).where(e.Application.id == id))
    if row is None or row.deleted_at is not None:
        raise DomainError("not_found", 404)
    return row


def check_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise DomainError("revision_conflict")


async def get_profile(session: AsyncSession) -> e.PersonalProfile:
    from career_agent.profile_area.entities import ProfileWorkspace

    work = await session.get(ProfileWorkspace, "personal")
    if work:
        if work.current_profile_id is None:
            raise DomainError("not_found", 404)
        return await require(session, e.PersonalProfile, work.current_profile_id)
    profile = await session.scalar(
        select(e.PersonalProfile)
        .where(e.PersonalProfile.archived_at.is_(None))
        .order_by(e.PersonalProfile.revision.desc())
    )
    if profile is None:
        raise DomainError("not_found", 404)
    return profile


def profile_content(data: dict[str, Any]) -> dict[str, Any]:
    value = s.ProfileData.model_validate(data).model_dump(mode="json")
    for section in ["education", "experiences", "projects"]:
        for entry in value[section]:
            entry.pop("entry_id", None)
            if section == "education" and not entry["degree"] and entry["role"]:
                entry["degree"], entry["role"] = entry["role"], ""
    return value


async def put_profile(
    session: AsyncSession, payload: s.ProfileWrite, *, update_current: bool = True
) -> e.PersonalProfile:
    # Single-user profile: serialize even the first insert, where no row exists to lock.
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    from career_agent.profile_area.entities import ProfileWorkspace

    work = await session.get(ProfileWorkspace, "personal")
    current = (
        await session.get(e.PersonalProfile, work.current_profile_id)
        if work and work.current_profile_id
        else None
    )
    latest = await session.scalar(select(func.max(e.PersonalProfile.revision))) or 0
    expected_head = (current.revision if current else 0) if work and update_current else latest
    check_revision(expected_head, payload.expected_revision)
    if payload.data.personal.photo_id:
        from career_agent.profile_area.entities import ProfilePhoto

        await require(session, ProfilePhoto, payload.data.personal.photo_id)
    for fact_id in payload.data.fact_ids:
        await require(session, e.PersonalFact, fact_id)
    for experience in payload.data.education + payload.data.experiences + payload.data.projects:
        for fact_id in experience.fact_ids:
            await require(session, e.PersonalFact, fact_id)
    data = payload.data.model_dump(mode="json")
    if (
        current is not None
        and current.archived_at is None
        and profile_content(current.data) == profile_content(data)
    ):
        return current
    if latest:
        previous = await session.scalar(
            select(e.PersonalProfile).where(e.PersonalProfile.revision == latest)
        )
        if (
            previous is not None
            and previous.archived_at is None
            and profile_content(previous.data) == profile_content(data)
        ):
            if update_current:
                if work:
                    work.current_profile_id = previous.id
            return previous
    profile = e.PersonalProfile(revision=latest + 1, data=data)
    session.add(profile)
    await session.flush()
    if update_current:
        if work:
            work.current_profile_id = profile.id
    return profile


async def create_fact(session: AsyncSession, payload: s.FactCreate) -> e.PersonalFact:
    if payload.source_document_id:
        await require(session, e.SourceDocument, payload.source_document_id)
    fact = e.PersonalFact(**payload.model_dump())  # status is never accepted from imports/API
    session.add(fact)
    await session.flush()
    return fact


async def verify_user_fact(session: AsyncSession, row_id: UUID) -> e.PersonalFact:
    fact = await require(session, e.PersonalFact, row_id, lock=True)
    fact.status = verify_fact(fact.status, explicit_user_action=True)
    fact.verified_at = e.utcnow()
    await session.flush()
    return fact


async def add_job_revision(
    session: AsyncSession,
    job: e.JobPosting,
    title: str,
    jd_text: str,
    requirements: list[s.RequirementInput],
) -> None:
    revision = e.JobRevision(
        job_id=job.id, revision=job.current_revision, title=title, jd_text=jd_text
    )
    session.add(revision)
    await session.flush()
    for requirement in requirements:
        session.add(e.JobRequirement(job_revision_id=revision.id, **requirement.model_dump()))
    await session.flush()


async def create_job(session: AsyncSession, payload: s.JobCreate) -> e.JobPosting:
    from career_agent.interview.context import digest

    normalized = payload.model_dump(mode="json", exclude={"request_id"})
    normalized["company_name"] = payload.company_name.strip()
    fingerprint = digest(normalized)
    if payload.request_id:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 4312))"),
            {"key": str(payload.request_id)},
        )
        receipt = await session.get(e.JobCreateRequest, payload.request_id)
        if receipt:
            if receipt.payload_hash != fingerprint:
                raise DomainError("request_identity_conflict", 409)
            return await require(session, e.JobPosting, receipt.job_id)
    # Only trim outer whitespace; never case-fold or fuzzy-merge company identities.
    name = payload.company_name.strip()
    if payload.company_id:
        company = await require(session, e.Company, payload.company_id)
        if company.name.strip() != name:
            raise DomainError("company_name_mismatch", 422)
    else:
        # Serialize concurrent name-only misses without declaring names globally unique.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "job-company:" + name},
        )
        matches = list(
            await session.scalars(
                select(e.Company)
                .where(
                    func.btrim(
                        e.Company.name,
                        " \t\r\n\v\f\u0085\u00a0\u1680\u2000\u2001\u2002"
                        "\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\x1c\x1d\x1e\x1f",
                    )
                    == name
                )
                .limit(2)
            )
        )
        if len(matches) > 1:
            raise DomainError("company_selection_required", 409)
        if matches:
            company = matches[0]
        else:
            company = e.Company(name=name)
            session.add(company)
            await session.flush()
    job = e.JobPosting(company_id=company.id)
    session.add(job)
    await session.flush()
    await add_job_revision(session, job, payload.title, payload.jd_text, payload.requirements)
    application = e.Application(job_id=job.id)
    session.add(application)
    await session.flush()
    from career_agent.product.bindings import initialize

    await initialize(session, application)
    session.add(
        e.ApplicationEvent(
            application_id=application.id,
            sequence=1,
            kind="created",
            to_status=ApplicationStatus.TRACKING,
        )
    )
    if payload.request_id:
        session.add(
            e.JobCreateRequest(
                id=payload.request_id,
                payload_hash=fingerprint,
                job_id=job.id,
                application_id=application.id,
            )
        )
    await session.flush()
    return job


async def active_job(session: AsyncSession, job_id: UUID) -> None:
    # Concurrent admissions must still reach the reuse claim; only deletion/state writes wait.
    application = await session.scalar(
        select(e.Application)
        .where(e.Application.job_id == job_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if application is not None and application.deleted_at is not None:
        raise DomainError("application_deleted", 409)


async def active_jd(session: AsyncSession, jd_id: UUID) -> None:
    jd = await require(session, e.JobRevision, jd_id)
    await active_job(session, jd.job_id)


async def active_interview_target(
    session: AsyncSession,
    row: e.MockInterviewSession | e.DebriefRun | e.InterviewSession | e.KnowledgeNote,
) -> None:
    if isinstance(row, (e.InterviewSession, e.KnowledgeNote)):
        if row.application_id:
            await require(session, e.Application, row.application_id)
        elif isinstance(row, e.KnowledgeNote) and row.interview_id:
            interview = await require(session, e.InterviewSession, row.interview_id)
            await require(session, e.Application, interview.application_id)
    elif isinstance(row, e.MockInterviewSession):
        if row.application_id:
            await require(session, e.Application, row.application_id)
        else:
            await active_job(session, UUID(row.context["job_id"]))
    else:
        snapshot = row.snapshot
        if snapshot["source_kind"] == "actual":
            interview = await require(session, e.InterviewSession, UUID(snapshot["interview_id"]))
            await require(session, e.Application, interview.application_id)
        else:
            mock = await require(session, e.MockInterviewSession, UUID(snapshot["interview_id"]))
            await active_interview_target(session, mock)


async def revise_job(
    session: AsyncSession, row_id: UUID, payload: s.JobRevisionWrite
) -> e.JobPosting:
    await active_job(session, row_id)
    job = await require(session, e.JobPosting, row_id, lock=True)
    check_revision(job.current_revision, payload.expected_revision)
    previous = (
        await session.scalars(
            select(e.JobRevision).where(
                e.JobRevision.job_id == job.id, e.JobRevision.revision == job.current_revision
            )
        )
    ).one()
    # The legacy endpoint also keeps the single owning application's default coherent.
    if (
        previous.title == payload.title
        and previous.jd_text == payload.jd_text
        and not payload.requirements
    ):
        return job
    job.current_revision += 1
    await add_job_revision(session, job, payload.title, payload.jd_text, payload.requirements)
    from career_agent.product.bindings import initialize

    app = await session.scalar(select(e.Application).where(e.Application.job_id == job.id))
    if app is not None:
        binding = await initialize(session, app)
        jd = (
            await session.scalars(
                select(e.JobRevision).where(
                    e.JobRevision.job_id == job.id, e.JobRevision.revision == job.current_revision
                )
            )
        ).one()
        binding.job_revision_id = jd.id
        binding.revision += 1
        binding.updated_at = e.utcnow()
    return job


async def edit_application_jd(
    session: AsyncSession, id: UUID, payload: s.ApplicationJDWrite
) -> e.JobPosting:
    from career_agent.product.bindings import read

    app = await require(session, e.Application, id, lock=True)
    binding = await read(session, id)
    check_revision(binding.revision, payload.expected_binding_revision)
    job = await require(session, e.JobPosting, app.job_id, lock=True)
    current = (
        await session.scalars(
            select(e.JobRevision).where(
                e.JobRevision.job_id == job.id, e.JobRevision.revision == job.current_revision
            )
        )
    ).one()
    return await revise_job(
        session,
        job.id,
        s.JobRevisionWrite(
            expected_revision=payload.expected_revision,
            title=current.title,
            jd_text=payload.jd_text,
        ),
    )


async def delete_application(session: AsyncSession, id: UUID) -> None:
    app = await require(session, e.Application, id, lock=True)
    if application_status(app.status) != ApplicationStatus.CLOSED:
        raise DomainError("application_not_closed", 409)
    app.deleted_at = e.utcnow()
    app.revision += 1
    await session.flush()


async def job_view(session: AsyncSession, job: e.JobPosting) -> dict[str, Any]:
    revision = (
        await session.scalars(
            select(e.JobRevision).where(
                e.JobRevision.job_id == job.id, e.JobRevision.revision == job.current_revision
            )
        )
    ).one()
    company = await require(session, e.Company, job.company_id)
    application_id = await session.scalar(
        select(e.Application.id).where(
            e.Application.job_id == job.id, e.Application.deleted_at.is_(None)
        )
    )
    requirements = list(
        await session.scalars(
            select(e.JobRequirement)
            .where(e.JobRequirement.job_revision_id == revision.id)
            .order_by(e.JobRequirement.created_at)
        )
    )
    return {
        "id": job.id,
        "job_revision_id": revision.id,
        "created_at": job.created_at,
        "company_id": company.id,
        "company_name": company.name,
        "revision": job.current_revision,
        "title": revision.title,
        "jd_text": revision.jd_text,
        "requirements": requirements,
        "application_id": application_id,
    }


async def application_events(session: AsyncSession, row_id: UUID) -> list[e.ApplicationEvent]:
    return list(
        await session.scalars(
            select(e.ApplicationEvent)
            .where(e.ApplicationEvent.application_id == row_id)
            .order_by(e.ApplicationEvent.sequence)
        )
    )


async def change_application(
    session: AsyncSession, row_id: UUID, payload: s.ApplicationChange
) -> e.Application:
    application = await require(session, e.Application, row_id, lock=True)
    check_revision(application.revision, payload.expected_revision)
    transition_application(
        application.status,
        payload.status,
        correction=payload.correction,
        reason=payload.reason,
        explicit_user_action=True,
    )
    target = application_status(payload.status)
    if application_status(application.status) == target:
        return application
    previous = application.status
    application.status = target
    application.revision += 1
    session.add(
        e.ApplicationEvent(
            application_id=row_id,
            sequence=application.revision,
            kind="correction" if payload.correction else "status_changed",
            from_status=previous,
            to_status=target,
            source="status",
            note=payload.reason,
        )
    )
    await session.flush()
    return application


async def application_note(
    session: AsyncSession, row_id: UUID, payload: s.NoteCreate
) -> e.ApplicationEvent:
    application = await require(session, e.Application, row_id, lock=True)
    if payload.request_id:
        old = await session.scalar(
            select(e.ApplicationEvent).where(e.ApplicationEvent.request_id == payload.request_id)
        )
        if old:
            if (
                old.application_id != row_id
                or old.source != "user_note"
                or old.note != payload.text
            ):
                raise DomainError("idempotency_conflict")
            return old
    if payload.expected_revision is not None:
        check_revision(application.revision, payload.expected_revision)
    application.revision += 1
    event = e.ApplicationEvent(
        application_id=row_id,
        sequence=application.revision,
        kind="note",
        note=payload.text,
        source="user_note",
        request_id=payload.request_id,
    )
    session.add(event)
    await session.flush()
    return event


async def create_interview(session: AsyncSession, payload: s.InterviewCreate) -> e.InterviewSession:
    from career_agent.interview.actual import check_round, validate_entries
    from career_agent.interview.context import digest
    from career_agent.interview.numbering import numbered
    from career_agent.product.bindings import read as read_binding
    from career_agent.product.bindings import view as binding_view

    app = await require(session, e.Application, payload.application_id)
    request_hash = digest(payload.model_dump(mode="json"))
    if payload.request_id:
        existing = await session.scalar(
            select(e.InterviewSession).where(e.InterviewSession.request_id == payload.request_id)
        )
        if existing:
            if existing.application_id != app.id or existing.request_hash != request_hash:
                raise DomainError("idempotency_conflict")
            return existing
    validate_entries(payload.entries)
    if payload.status == "completed" and not any(v.kind == "primary" for v in payload.entries):
        raise DomainError("interview_questions_required", 422)
    await check_round(session, app.id, payload.round_number)
    name = payload.round_name
    if not name:
        if payload.round_number is None or payload.interview_type is None:
            raise DomainError("interview_metadata_required", 422)
        job = await require(session, e.JobPosting, app.job_id)
        company = await require(session, e.Company, job.company_id)
        binding = await binding_view(session, await read_binding(session, app.id))
        revision = await require(session, e.JobRevision, binding.job_revision_id)
        types = {"technical": "技术", "hr": "人力资源", "mixed": "综合", "other": "其他"}
        name = (
            f"{company.name} · {revision.title} · 第{payload.round_number}轮 · "
            f"{types[payload.interview_type]}"
        )
    binding = await binding_view(session, await read_binding(session, payload.application_id))
    interview = e.InterviewSession(
        **payload.model_dump(exclude={"expected_revision", "entries", "notes_text", "round_name"}),
        round_name=name,
        request_hash=request_hash if payload.request_id else None,
        saved_at=e.utcnow(),
        entries=[entry.model_dump(mode="json") for entry in numbered(payload.entries, [])],
        notes=[
            s.InterviewNoteData(
                text=payload.notes_text.strip(), recorded_at=e.utcnow().isoformat()
            ).model_dump()
        ]
        if payload.notes_text and payload.notes_text.strip()
        else [],
        context_binding={
            "profile_id": str(binding.profile_id) if binding.profile_id else None,
            "resume_revision_id": str(binding.resume_revision_id)
            if binding.resume_revision_id
            else None,
            "job_revision_id": str(binding.job_revision_id),
            "binding_revision": binding.revision,
        },
    )
    session.add(interview)
    await session.flush()
    return interview


async def interview_note(
    session: AsyncSession, row_id: UUID, payload: s.InterviewNoteCreate
) -> e.InterviewSession:
    interview = await require(session, e.InterviewSession, row_id, lock=True)
    await active_interview_target(session, interview)
    check_revision(interview.content_revision, payload.expected_revision)
    note = s.InterviewNoteData(text=payload.text, recorded_at=e.utcnow().isoformat())
    interview.notes = [*interview.notes, note.model_dump()]
    interview.content_revision += 1
    await session.flush()
    return interview


async def create_knowledge(session: AsyncSession, payload: s.KnowledgeCreate) -> e.KnowledgeNote:
    from career_agent.infrastructure.claims import claim
    from career_agent.interview.context import digest

    identity = digest(payload.model_dump(mode="json", exclude={"request_id"}))
    if payload.request_id:
        await claim(session, "knowledge:" + str(payload.request_id))
        existing = await session.scalar(
            select(e.KnowledgeNote).where(e.KnowledgeNote.request_id == payload.request_id)
        )
        if existing:
            if existing.request_hash != identity:
                raise DomainError("request_identity_conflict", 409)
            if existing.deleted_at:
                raise DomainError("note_removed", 410)
            return existing
    if payload.application_id:
        await require(session, e.Application, payload.application_id)
    if payload.interview_id:
        interview = await require(session, e.InterviewSession, payload.interview_id)
        await active_interview_target(session, interview)
        if payload.application_id and interview.application_id != payload.application_id:
            raise DomainError("knowledge_application_mismatch", 409)
    if payload.source_document_id:
        await require(session, e.SourceDocument, payload.source_document_id)
    note = e.KnowledgeNote(**payload.model_dump(), request_hash=identity, updated_at=e.utcnow())
    session.add(note)
    await session.flush()
    return note
