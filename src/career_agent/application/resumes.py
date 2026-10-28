import asyncio
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import check_revision, require
from career_agent.config import Settings
from career_agent.domain.rules import DomainError
from career_agent.domain.schemas import ProfileData
from career_agent.infrastructure import entities as e
from career_agent.resume.compiler import compile_resume
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.renderer import CompileError, TypstRenderer
from career_agent.resume.schemas import (
    FactSnapshot,
    Finding,
    InputSnapshot,
    RenderReport,
    ResumeDocument,
    VariantOut,
)
from career_agent.resume.store import ArtifactStore


def profile_fact_ids(profile: e.PersonalProfile) -> set[UUID]:
    data = ProfileData.model_validate(profile.data)
    return set(data.fact_ids) | {
        f for x in data.education + data.experiences + data.projects for f in x.fact_ids
    }


async def snapshot_for(session: AsyncSession, document: ResumeDocument) -> InputSnapshot:
    profile = await require(session, e.PersonalProfile, document.profile_id)
    if profile.revision != document.profile_revision:
        raise DomainError("invalid_variant", 422)
    if document.job_revision_id:
        await require(session, e.JobRevision, document.job_revision_id)
    facts = list(
        await session.scalars(
            select(e.PersonalFact)
            .where(e.PersonalFact.id.in_(profile_fact_ids(profile)))
            .order_by(e.PersonalFact.id)
        )
    )
    return InputSnapshot(
        display_name=ProfileData.model_validate(profile.data).display_name,
        personal=ProfileData.model_validate(profile.data).personal,
        facts=[FactSnapshot(fact_id=f.id, revision=f.revision) for f in facts],
    )


async def save_revision(
    session: AsyncSession,
    variant: e.ResumeVariant,
    document: ResumeDocument,
    *,
    library_number: int | None = None,
) -> e.ResumeVariantRevision:
    snapshot = await snapshot_for(session, document)
    from career_agent.profile_area.service import next_resume_number

    number = (
        (library_number if library_number is not None else await next_resume_number(session))
        if variant.current_revision == 1 and variant.library_visible
        else None
    )
    label = f"简历 {number}" if number is not None else "简历"
    if document.job_revision_id:
        job = await require(session, e.JobRevision, document.job_revision_id)
        posting = await require(session, e.JobPosting, job.job_id)
        company = await require(session, e.Company, posting.company_id)
        ordinal = (
            await session.scalar(
                select(func.count())
                .select_from(e.ResumeVariantRevision)
                .join(e.JobRevision, e.JobRevision.id == e.ResumeVariantRevision.job_revision_id)
                .where(e.JobRevision.job_id == job.job_id)
            )
            or 0
        ) + 1
        label = f"{company.name} · {job.title} · 优化版 {ordinal}"
    row = e.ResumeVariantRevision(
        resume_variant_id=variant.id,
        revision=variant.current_revision,
        library_number=number,
        display_name=label[:200],
        profile_id=document.profile_id,
        job_revision_id=document.job_revision_id,
        document=document.model_dump(mode="json"),
        input_snapshot=snapshot.model_dump(mode="json"),
    )
    session.add(row)
    await session.flush()
    return row


async def create_variant(
    session: AsyncSession,
    document: ResumeDocument,
    *,
    library_visible: bool = True,
    library_number: int | None = None,
) -> e.ResumeVariantRevision:
    variant = e.ResumeVariant(library_visible=library_visible)
    session.add(variant)
    await session.flush()
    return await save_revision(session, variant, document, library_number=library_number)


async def get_revision(
    session: AsyncSession, variant_id: UUID, revision: int | None = None
) -> e.ResumeVariantRevision:
    variant = await require(session, e.ResumeVariant, variant_id)
    row = await session.scalar(
        select(e.ResumeVariantRevision).where(
            e.ResumeVariantRevision.resume_variant_id == variant_id,
            e.ResumeVariantRevision.revision == (revision or variant.current_revision),
        )
    )
    if row is None:
        raise DomainError("not_found", 404)
    return row


async def revise_variant(
    session: AsyncSession, variant_id: UUID, expected_revision: int, document: ResumeDocument
) -> e.ResumeVariantRevision:
    variant = await require(session, e.ResumeVariant, variant_id, lock=True)
    check_revision(variant.current_revision, expected_revision)
    current = await get_revision(session, variant_id, variant.current_revision)
    if current.document == document.model_dump(mode="json"):
        return current
    variant.current_revision += 1
    return await save_revision(session, variant, document)


def variant_view(row: e.ResumeVariantRevision) -> VariantOut:
    return VariantOut(
        resume_revision_id=row.id,
        id=row.resume_variant_id,
        revision=row.revision,
        created_at=row.created_at,
        document=ResumeDocument.model_validate(row.document),
        input_snapshot=InputSnapshot.model_validate(row.input_snapshot),
    )


async def render_variant(
    session: AsyncSession, row: e.ResumeVariantRevision, settings: Settings
) -> e.RenderArtifact:
    document = ResumeDocument.model_validate(row.document)
    snapshot = InputSnapshot.model_validate(row.input_snapshot)
    profile = await require(session, e.PersonalProfile, row.profile_id)
    # Hold locks through accepted-artifact commit, so confirmation cannot change mid-render.
    ids = sorted({f for s in document.sections for i in s.items for f in i.fact_refs}, key=str)
    facts = list(
        await session.scalars(
            select(e.PersonalFact)
            .where(e.PersonalFact.id.in_(ids))
            .order_by(e.PersonalFact.id)
            .with_for_update()
        )
    )
    requirements = (
        set(
            await session.scalars(
                select(e.JobRequirement.id).where(
                    e.JobRequirement.job_revision_id == document.job_revision_id
                )
            )
        )
        if document.job_revision_id
        else set()
    )
    findings = validate_grounding(
        document,
        snapshot,
        profile_fact_ids(profile),
        {f.id: FactEvidence(f.id, f.revision, f.status, f.statement) for f in facts},
        requirements,
    )
    if (
        document.profile_id != row.profile_id
        or document.profile_revision != profile.revision
        or document.job_revision_id != row.job_revision_id
    ):
        findings.append(Finding(code="snapshot_mismatch"))
    from career_agent.resume.presentation import apply_presentation

    content = None
    if findings:
        report = RenderReport(
            render_status="failed",
            validation_status="not_run",
            error_code="grounding_failed",
            findings=findings,
        )
    else:
        from career_agent.profile_area.entities import ProfilePhoto
        from career_agent.profile_area.photos import PhotoStore

        renderer = TypstRenderer(
            settings.typst_bin, settings.compile_timeout_seconds, settings.font_dir
        )
        if snapshot.personal:
            renderer.header = snapshot.personal.model_dump(mode="json", exclude={"photo_id"})
            if snapshot.personal.photo_id:
                photo = await require(session, ProfilePhoto, snapshot.personal.photo_id)
                renderer.photo = PhotoStore(settings.data_dir).read(photo.id, photo.sha256)
        report, content = await asyncio.to_thread(
            compile_resume,
            apply_presentation(document, row.presentation or {}),
            snapshot.display_name,
            renderer,
        )
    report.presentation = row.presentation or {}
    artifact = e.RenderArtifact(
        resume_variant_id=row.resume_variant_id, resume_variant_revision=row.revision
    )
    store = ArtifactStore(settings.data_dir)
    if content is not None:
        ref = uuid4()
        try:
            digest = store.write(ref, content)
            if digest != report.file_hash:
                store.remove(ref)
                raise CompileError("artifact_write_failed")
            artifact.file_hash = digest
            artifact.artifact_ref = ref
            # Request transaction rollback cleanup, no private path in API/trace.
            session.info.setdefault("artifact_cleanup", []).append((store, ref))
        except CompileError:
            report.file_hash = None
            artifact.file_hash = None
            artifact.artifact_ref = None
            report.render_status = "failed"
            report.error_code = "artifact_write_failed"
            report.findings.append(Finding(code="artifact_write_failed"))
    artifact.report = report.model_dump(mode="json")
    session.add(artifact)
    await session.flush()
    return artifact
