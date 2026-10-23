"""Explicit submission records, distinct from generation or selection."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import change_application, check_revision, require
from career_agent.config import Settings
from career_agent.domain.rules import ApplicationStatus, DomainError
from career_agent.domain.schemas import ApplicationChange
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.claims import claim
from career_agent.preparation.contracts import PrivateResult, WorkflowState
from career_agent.product.contracts import SubmissionCreate, SubmissionOut
from career_agent.product.entities import MaterialSubmission
from career_agent.resume.renderer import CompileError
from career_agent.resume.store import ArtifactStore


def view(row: MaterialSubmission) -> SubmissionOut:
    return SubmissionOut(
        **row.payload,
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
        return view(old)
    application = await require(session, e.Application, application_id, lock=True)
    check_revision(application.revision, payload.expected_revision)
    resume = await require(session, e.ResumeVariantRevision, payload.resume_revision_id)
    if resume.job_revision_id:
        jd = await require(session, e.JobRevision, resume.job_revision_id)
        if jd.job_id != application.job_id:
            raise DomainError("context_revision_mismatch")
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
                e.PreparationArtifact.data["output"]["source_resume_revision_id"].astext
                == str(resume.id),
            )
        )
        if (
            greeting.data["kind"] != "greeting"
            or greeting.profile_id != resume.profile_id
            or jd.job_id != application.job_id
            or not target
            or (resume.job_revision_id and greeting.job_revision_id != resume.job_revision_id)
        ):
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
    if application.status != ApplicationStatus.APPLIED:
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
            note=payload.note or "Explicit additional submission",
        )
        session.add(event)
        await session.flush()
    row = MaterialSubmission(
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
    return view(row)
