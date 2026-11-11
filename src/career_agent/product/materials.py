"""Explicit submission records, distinct from generation or selection."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import change_application, check_revision, require
from career_agent.config import Settings
from career_agent.domain.rules import ApplicationStatus, DomainError, application_status
from career_agent.domain.schemas import ApplicationChange
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.claims import claim
from career_agent.preparation.contracts import PrivateResult, WorkflowState
from career_agent.product.contracts import SubmissionCreate, SubmissionEdit, SubmissionOut
from career_agent.product.entities import MaterialSubmission, ResultRemoval
from career_agent.resume.renderer import CompileError
from career_agent.resume.store import ArtifactStore


async def view(session: AsyncSession, row: MaterialSubmission) -> SubmissionOut:
    resume = await require(session, e.ResumeVariantRevision, row.resume_revision_id)
    target = (
        await session.scalar(
            select(e.PreparationArtifact).where(
                e.PreparationArtifact.data["kind"].astext == "target",
                e.PreparationArtifact.data["output"]["target"].astext == "greeting_generation",
                e.PreparationArtifact.data["output"]["result_id"].astext == str(row.greeting_id),
            )
        )
        if row.greeting_id
        else None
    )
    greeting_name = None
    if target:
        jd = await require(session, e.JobRevision, target.job_revision_id)
        job = await require(session, e.JobPosting, jd.job_id)
        company = await require(session, e.Company, job.company_id)
        greeting_name = f"{company.name} · {jd.title}"
    event = await require(session, e.ApplicationEvent, row.event_id)
    return SubmissionOut(
        **{
            **row.payload,
            "note": row.note_override if row.revision > 1 else row.payload.get("note"),
        },
        display_number=row.display_number,
        revision=row.revision,
        resume_name=resume.display_name,
        greeting_name=greeting_name,
        greeting_target_id=target.id if target else None,
        status_changed=event.kind == "status_changed",
        id=row.id,
        application_id=row.application_id,
        event_id=row.event_id,
        created_at=row.created_at,
    )


async def submit(
    session: AsyncSession, settings: Settings, application_id: UUID, payload: SubmissionCreate
) -> SubmissionOut:
    await claim(session, "submission:" + str(payload.request_id))
    old = await session.scalar(
        select(MaterialSubmission).where(MaterialSubmission.request_id == payload.request_id)
    )
    if old:
        if old.application_id != application_id or old.payload != payload.model_dump(mode="json"):
            raise DomainError("idempotency_conflict")
        return await view(session, old)
    application = await require(session, e.Application, application_id, lock=True)
    check_revision(application.revision, payload.expected_revision)
    resume = await require(session, e.ResumeVariantRevision, payload.resume_revision_id)
    pdf = await require(session, e.RenderArtifact, payload.render_artifact_id)
    if (
        pdf.resume_variant_id != resume.resume_variant_id
        or pdf.resume_variant_revision != resume.revision
        or pdf.report["render_status"] != "accepted"
        or not pdf.artifact_ref
        or not pdf.file_hash
    ):
        raise DomainError("accepted_resume_required")
    try:
        ArtifactStore(settings.data_dir).read(pdf.artifact_ref, pdf.file_hash)
    except CompileError as exc:
        raise DomainError(exc.code) from None
    if payload.greeting_id:
        greeting = await require(session, e.PreparationArtifact, payload.greeting_id)
        jd = await require(session, e.JobRevision, greeting.job_revision_id)
        target = await session.scalar(
            select(e.PreparationArtifact).where(
                e.PreparationArtifact.data["kind"].astext == "target",
                e.PreparationArtifact.data["output"]["target"].astext == "greeting_generation",
                e.PreparationArtifact.data["output"]["result_id"].astext == str(greeting.id),
            )
        )
        if target and await session.scalar(
            select(ResultRemoval.id).where(ResultRemoval.target_id == target.id)
        ):
            raise DomainError("greeting_deleted")
        if greeting.data["kind"] != "greeting" or jd.job_id != application.job_id or not target:
            raise DomainError("context_revision_mismatch")
    if payload.package_id:
        package = await require(session, e.PreparationArtifact, payload.package_id)
        state = PrivateResult.model_validate(package.data).output
        jd = await require(session, e.JobRevision, package.job_revision_id)
        if (
            not isinstance(state, WorkflowState)
            or package.profile_id != resume.profile_id
            or jd.job_id != application.job_id
            or (resume.job_revision_id and package.job_revision_id != resume.job_revision_id)
        ):
            raise DomainError("context_revision_mismatch")
        if not (
            (
                state.resume_variant_id == resume.resume_variant_id
                and state.resume_variant_revision == resume.revision
                and state.render_report_id == pdf.id
            )
            or any(b.resume_revision_id == resume.id for b in state.bindings.values())
        ):
            raise DomainError("material_package_mismatch")
        if payload.greeting_id and state.greeting_id != payload.greeting_id:
            raise DomainError("material_package_mismatch")
    # Existing lifecycle validates explicit real submission; no generation path calls this.
    if application_status(application.status) == ApplicationStatus.TRACKING:
        await change_application(
            session,
            application_id,
            ApplicationChange(
                expected_revision=payload.expected_revision,
                status=ApplicationStatus.APPLIED,
                reason=payload.note,
            ),
        )
        event = await session.scalar(
            select(e.ApplicationEvent).where(
                e.ApplicationEvent.application_id == application_id,
                e.ApplicationEvent.sequence == application.revision,
            )
        )
        assert event is not None
    else:
        application.revision += 1
        event = e.ApplicationEvent(
            application_id=application_id,
            sequence=application.revision,
            kind="note",
            source="submission",
            note=payload.note or "Explicit additional submission",
        )
        session.add(event)
        await session.flush()
    number = (
        await session.scalar(
            select(func.max(MaterialSubmission.display_number)).where(
                MaterialSubmission.application_id == application_id
            )
        )
        or 0
    ) + 1
    row = MaterialSubmission(
        display_number=number,
        request_id=payload.request_id,
        application_id=application_id,
        event_id=event.id,
        resume_revision_id=resume.id,
        render_artifact_id=pdf.id,
        greeting_id=payload.greeting_id,
        package_id=payload.package_id,
        payload=payload.model_dump(mode="json"),
    )
    session.add(row)
    await session.flush()
    return await view(session, row)


async def edit(
    session: AsyncSession,
    application_id: UUID,
    id: UUID,
    payload: SubmissionEdit,
    *,
    remove: bool = False,
) -> SubmissionOut:
    await require(session, e.Application, application_id, lock=True)
    row = await require(session, MaterialSubmission, id, lock=True)
    if row.application_id != application_id:
        raise DomainError("not_found", 404)
    from career_agent.interview.context import digest

    identity = digest({"payload": payload.model_dump(mode="json"), "remove": remove})
    for item in row.edits:
        if item["request_id"] == str(payload.request_id):
            if item["hash"] != identity:
                raise DomainError("idempotency_conflict")
            return await view(session, row)
    check_revision(row.revision, payload.expected_revision)
    if row.deleted_at:
        raise DomainError("not_found", 404)
    note = (payload.note or "").strip() or None
    current = row.note_override if row.revision > 1 else row.payload.get("note")
    if not remove and note == current:
        return await view(session, row)
    row.note_override = current if remove else note
    row.revision += 1
    now = e.utcnow()
    if remove:
        row.deleted_at = now
    row.edits = [
        *row.edits,
        {
            "request_id": str(payload.request_id),
            "hash": identity,
            "revision": row.revision,
            "note": row.note_override,
            "removed": remove,
            "created_at": now.isoformat(),
        },
    ]
    await session.flush()
    return await view(session, row)
