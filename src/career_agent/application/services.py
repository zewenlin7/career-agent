from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.domain import schemas as s
from career_agent.domain.rules import (
    ApplicationStatus,
    DomainError,
    reject_fact,
    replace_fact,
    transition_application,
    verify_fact,
)
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.db import Base


async def require[T: Base](
    session: AsyncSession, cls: type[T], row_id: UUID, *, lock: bool = False
) -> T:
    statement = select(cls).where(cls.id == row_id)  # type: ignore[attr-defined]
    if lock:
        statement = statement.with_for_update()
    row = await session.scalar(statement)
    if row is None:
        raise DomainError("not_found", 404)
    return row


def check_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise DomainError("revision_conflict")


async def get_profile(session: AsyncSession) -> e.PersonalProfile:
    profile = await session.scalar(
        select(e.PersonalProfile).order_by(e.PersonalProfile.revision.desc())
    )
    if profile is None:
        raise DomainError("not_found", 404)
    return profile


async def put_profile(session: AsyncSession, payload: s.ProfileWrite) -> e.PersonalProfile:
    # Single-user profile: serialize even the first insert, where no row exists to lock.
    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    latest = await session.scalar(select(func.max(e.PersonalProfile.revision))) or 0
    check_revision(latest, payload.expected_revision)
    for experience in payload.data.education + payload.data.experiences + payload.data.projects:
        for fact_id in experience.fact_ids:
            await require(session, e.PersonalFact, fact_id)
    profile = e.PersonalProfile(revision=latest + 1, data=payload.data.model_dump(mode="json"))
    session.add(profile)
    await session.flush()
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


async def supersede_fact(
    session: AsyncSession, row_id: UUID, payload: s.FactReplacement
) -> e.PersonalFact:
    old = await require(session, e.PersonalFact, row_id, lock=True)
    check_revision(old.revision, payload.expected_revision)
    old.status = replace_fact(old.status)
    new = await create_fact(
        session, s.FactCreate.model_validate(payload.model_dump(exclude={"expected_revision"}))
    )
    new.lineage_id, new.revision, new.replaces_id = old.lineage_id, old.revision + 1, old.id
    await session.flush()
    return new


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
    # Names are not reliable company identities: never merge companies solely by name.
    company = e.Company(name=payload.company_name)
    session.add(company)
    await session.flush()
    job = e.JobPosting(company_id=company.id)
    session.add(job)
    await session.flush()
    await add_job_revision(session, job, payload.title, payload.jd_text, payload.requirements)
    application = e.Application(job_id=job.id)
    session.add(application)
    await session.flush()
    session.add(
        e.ApplicationEvent(
            application_id=application.id,
            sequence=1,
            kind="created",
            to_status=ApplicationStatus.TRACKING,
        )
    )
    await session.flush()
    return job


async def revise_job(
    session: AsyncSession, row_id: UUID, payload: s.JobRevisionWrite
) -> e.JobPosting:
    job = await require(session, e.JobPosting, row_id, lock=True)
    check_revision(job.current_revision, payload.expected_revision)
    job.current_revision += 1
    await add_job_revision(session, job, payload.title, payload.jd_text, payload.requirements)
    return job


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
        select(e.Application.id).where(e.Application.job_id == job.id)
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
    previous = application.status
    application.status = payload.status
    application.revision += 1
    session.add(
        e.ApplicationEvent(
            application_id=row_id,
            sequence=application.revision,
            kind="correction" if payload.correction else "status_changed",
            from_status=previous,
            to_status=payload.status,
            note=payload.reason,
        )
    )
    await session.flush()
    return application


async def application_note(
    session: AsyncSession, row_id: UUID, payload: s.NoteCreate
) -> e.ApplicationEvent:
    application = await require(session, e.Application, row_id, lock=True)
    application.revision += 1
    event = e.ApplicationEvent(
        application_id=row_id, sequence=application.revision, kind="note", note=payload.text
    )
    session.add(event)
    await session.flush()
    return event


async def create_interview(session: AsyncSession, payload: s.InterviewCreate) -> e.InterviewSession:
    await require(session, e.Application, payload.application_id)
    interview = e.InterviewSession(**payload.model_dump())
    session.add(interview)
    await session.flush()
    return interview


async def interview_note(
    session: AsyncSession, row_id: UUID, payload: s.NoteCreate
) -> e.InterviewSession:
    interview = await require(session, e.InterviewSession, row_id, lock=True)
    note = s.InterviewNoteData(text=payload.text, recorded_at=e.utcnow().isoformat())
    interview.notes = [*interview.notes, note.model_dump()]
    await session.flush()
    return interview


async def create_knowledge(session: AsyncSession, payload: s.KnowledgeCreate) -> e.KnowledgeNote:
    if payload.interview_id:
        await require(session, e.InterviewSession, payload.interview_id)
    if payload.source_document_id:
        await require(session, e.SourceDocument, payload.source_document_id)
    note = e.KnowledgeNote(**payload.model_dump())
    session.add(note)
    await session.flush()
    return note


async def reject_user_fact(session: AsyncSession, row_id: UUID) -> e.PersonalFact:
    fact = await require(session, e.PersonalFact, row_id, lock=True)
    fact.status = reject_fact(fact.status)
    await session.flush()
    return fact
