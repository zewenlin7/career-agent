"""Application defaults are mutable under CAS; every task still freezes exact inputs."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import check_revision, get_profile, require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.product.contracts import (
    ApplicationBindingOut,
    ApplicationBindingWrite,
    OperationCreate,
)
from career_agent.product.entities import ApplicationBinding


async def initialize(
    session: AsyncSession, application: e.Application, *, use_current_profile: bool = False
) -> ApplicationBinding:
    # Caller owns the Application row or is in its creation transaction.
    binding = await session.get(ApplicationBinding, application.id)
    if binding is not None:
        return binding
    job = await require(session, e.JobPosting, application.job_id)
    jd = await session.scalar(
        select(e.JobRevision).where(
            e.JobRevision.job_id == job.id, e.JobRevision.revision == job.current_revision
        )
    )
    if jd is None:
        raise DomainError("context_revision_mismatch")
    profile = None
    if use_current_profile:
        try:
            profile = await get_profile(session)
            await session.refresh(profile, with_for_update=True)
            if profile.archived_at:
                raise DomainError("profile_archived")
        except DomainError as exc:
            if exc.code != "not_found":
                raise
    binding = ApplicationBinding(
        application_id=application.id,
        job_revision_id=jd.id,
        profile_id=profile.id if profile else None,
    )
    session.add(binding)
    await session.flush()
    return binding


async def read(session: AsyncSession, id: UUID) -> ApplicationBinding:
    application = await require(session, e.Application, id, lock=True)
    return await initialize(session, application)


async def update(
    session: AsyncSession, id: UUID, payload: ApplicationBindingWrite
) -> ApplicationBinding:
    binding = await read(session, id)
    check_revision(binding.revision, payload.expected_revision)
    app = await require(session, e.Application, id)
    jd = await require(session, e.JobRevision, payload.job_revision_id)
    if jd.job_id != app.job_id:
        raise DomainError("context_revision_mismatch", 422)
    if payload.profile_id:
        profile = await require(session, e.PersonalProfile, payload.profile_id, lock=True)
        if profile.archived_at:
            raise DomainError("profile_archived")
    if payload.resume_revision_id:
        resume = await require(
            session, e.ResumeVariantRevision, payload.resume_revision_id, lock=True
        )
        if resume.archived_at:
            raise DomainError("resume_archived")
        if payload.profile_id is not None and resume.profile_id != payload.profile_id:
            raise DomainError("context_revision_mismatch", 422)
        if resume.job_revision_id:
            resume_jd = await require(session, e.JobRevision, resume.job_revision_id)
            if resume_jd.job_id != app.job_id:
                raise DomainError("context_revision_mismatch", 422)
    old = (binding.profile_id, binding.resume_revision_id, binding.job_revision_id)
    # Resume is the persistent product binding. Its immutable source Profile remains
    # available as a derived execution context, not an independently mutable pointer.
    new = (
        None if payload.resume_revision_id else payload.profile_id,
        payload.resume_revision_id,
        payload.job_revision_id,
    )
    if old != new:
        binding.profile_id, binding.resume_revision_id, binding.job_revision_id = new
        binding.revision += 1
        binding.updated_at = e.utcnow()
        await session.flush()
    return binding


async def view(session: AsyncSession, binding: ApplicationBinding) -> ApplicationBindingOut:
    profile = (
        await require(session, e.PersonalProfile, binding.profile_id)
        if binding.profile_id
        else None
    )
    resume = (
        await require(session, e.ResumeVariantRevision, binding.resume_revision_id)
        if binding.resume_revision_id
        else None
    )
    if resume is not None:
        profile = await require(session, e.PersonalProfile, resume.profile_id)
    jd = await require(session, e.JobRevision, binding.job_revision_id)
    return ApplicationBindingOut(
        application_id=binding.application_id,
        revision=binding.revision,
        profile_id=profile.id if profile else None,
        resume_revision_id=binding.resume_revision_id,
        job_revision_id=binding.job_revision_id,
        updated_at=binding.updated_at,
        profile_name=profile.data["display_name"] if profile else None,
        profile_revision=profile.revision if profile else None,
        resume_name=resume.display_name if resume else None,
        resume_revision=resume.revision if resume else None,
        job_revision=jd.revision,
    )


async def validate_request(session: AsyncSession, payload: OperationCreate) -> None:
    """Validate defaults once at creation; execution uses the frozen request thereafter."""
    ref = payload.application_binding
    assert ref is not None
    binding = await read(session, ref.application_id)
    check_revision(binding.revision, ref.revision)
    request = payload.request
    if request.job_revision_id != binding.job_revision_id:
        raise DomainError("context_revision_mismatch", 422)
    if payload.kind == "company_research":
        return
    execution_profile = binding.profile_id
    if binding.resume_revision_id:
        execution_profile = (
            await require(session, e.ResumeVariantRevision, binding.resume_revision_id)
        ).profile_id
    if request.profile_id != execution_profile:
        raise DomainError("context_revision_mismatch", 422)
    if request.resume_revision_id != binding.resume_revision_id:
        raise DomainError("context_revision_mismatch", 422)
    for target_binding in request.bindings.values():
        if target_binding.output_of is None and (
            target_binding.resume_revision_id != binding.resume_revision_id
        ):
            raise DomainError("context_revision_mismatch", 422)
