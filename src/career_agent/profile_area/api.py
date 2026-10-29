from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import DateTime, String, cast, func, select

from career_agent.api.dependencies import DB
from career_agent.api.schemas import ProfileOut
from career_agent.application import resumes
from career_agent.application import services as svc
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.product.entities import ApplicationBinding
from career_agent.profile_area import contracts as c
from career_agent.profile_area import service as s
from career_agent.profile_area.entities import ProfilePhoto, ResumeWorkspace
from career_agent.profile_area.photos import PhotoStore, normalize
from career_agent.resume.presentation import Presentation, PresentationWrite

router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/profile-workspace")
async def get_workspace(session: DB) -> dict[str, Any]:
    return s.view(await s.workspace(session))


@router.patch("/profile-workspace/sections/{section}")
async def update_section(
    section: c.Section, payload: c.SectionWrite, session: DB
) -> dict[str, Any]:
    try:
        return s.view(await s.save_section(session, section, payload))
    except ValidationError:
        raise DomainError("invalid_profile_section", 422) from None


@router.post("/profile-workspace/publish", response_model=ProfileOut)
async def publish(payload: c.Publish, session: DB) -> e.PersonalProfile:
    try:
        return await s.publish(session, payload)
    except ValidationError:
        raise DomainError("profile_name_required", 422) from None


@router.post("/profile-workspace/restore")
async def restore(payload: c.Restore, session: DB) -> dict[str, Any]:
    return s.view(await s.restore(session, payload))


@router.delete("/profile/revisions/{id}")
async def archive_profile(id: UUID, session: DB) -> dict[str, bool]:
    await s.archive_profile(session, id)
    return {"archived": True}


@router.post("/profile-photos", status_code=201)
async def upload(request: Request, session: DB) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";")[0] not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        raise DomainError("invalid_photo", 422)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 5_000_000:
            raise DomainError("photo_too_large", 413)
    image, width, height = normalize(bytes(content))
    store = PhotoStore(request.app.state.settings.data_dir)
    id = uuid4()
    sha = store.write(id, image)
    session.info.setdefault("artifact_cleanup", []).append((store, id))
    session.add(ProfilePhoto(id=id, sha256=sha, width=width, height=height))
    await session.flush()
    return {"id": id, "width": width, "height": height, "url": f"/api/v1/profile-photos/{id}"}


@router.get("/profile-photos/{id}")
async def photo(id: UUID, request: Request, session: DB) -> Response:
    row = await svc.require(session, ProfilePhoto, id)
    return Response(
        PhotoStore(request.app.state.settings.data_dir).read(id, row.sha256),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline; filename=photo.jpg",
        },
    )


def draft_view(row: ResumeWorkspace) -> dict[str, Any]:
    return {
        "id": row.id,
        "entry_id": (row.library_state or {}).get("entry_id", str(row.id)),
        "revision": row.revision,
        "name": row.name,
        "created_at": (row.library_state or {}).get("entry_created_at", row.created_at),
        "saved_at": row.saved_at,
        "presentation": Presentation.model_validate(row.presentation or {}).model_dump(mode="json"),
        "document": row.document,
        "personal": row.source.get("personal", {}),
        "display_name": row.source.get("display_name", ""),
        "accepted_revision_id": row.accepted_revision_id,
        "profile_id": row.profile_id,
        "source_resume_revision_id": row.source_resume_revision_id,
    }


@router.get("/resume-workspaces")
async def drafts(session: DB, limit: Limit = 100, offset: Offset = 0) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(ResumeWorkspace)
        .where(
            ResumeWorkspace.archived_at.is_(None),
            ResumeWorkspace.accepted_revision_id.is_(None),
            ResumeWorkspace.library_state["replaced_by_id"].astext.is_(None),
        )
        .order_by(
            func.coalesce(
                cast(
                    ResumeWorkspace.library_state["entry_created_at"].astext,
                    DateTime(timezone=True),
                ),
                ResumeWorkspace.created_at,
            ).desc(),
            func.coalesce(
                ResumeWorkspace.library_state["entry_id"].astext, cast(ResumeWorkspace.id, String)
            ),
        )
        .offset(offset)
        .limit(limit)
    )
    return [draft_view(row) for row in rows]


@router.post("/resume-workspaces", status_code=201)
async def create_draft(session: DB, payload: c.ResumeCreate | None = None) -> dict[str, Any]:
    return draft_view(await s.create_draft(session, payload))


@router.get("/resume-workspaces/{id}")
async def get_draft(id: UUID, session: DB) -> dict[str, Any]:
    return draft_view(await svc.require(session, ResumeWorkspace, id))


@router.patch("/resume-workspaces/{id}")
async def save_draft(id: UUID, payload: c.DraftWrite, session: DB) -> dict[str, Any]:
    row = await svc.require(session, ResumeWorkspace, id, lock=True)
    svc.check_revision(row.revision, payload.expected_revision)
    if row.accepted_revision_id or row.archived_at:
        raise DomainError("draft_already_saved")
    document = payload.document.model_dump(mode="json")
    if row.document != document or row.name != payload.name:
        row.document, row.name = document, payload.name
        row.revision += 1
        row.saved_at = e.utcnow()
    return draft_view(row)


@router.delete("/resume-workspaces/{id}")
async def discard_draft(id: UUID, payload: c.Publish, session: DB) -> dict[str, bool]:
    row = await svc.require(session, ResumeWorkspace, id, lock=True)
    svc.check_revision(row.revision, payload.expected_revision)
    row.archived_at = row.archived_at or e.utcnow()
    return {"archived": True}


@router.get("/resume-library/versions")
async def versions(session: DB, limit: Limit = 100, offset: Offset = 0) -> dict[str, Any]:
    first_created = func.coalesce(
        cast(
            e.ResumeVariantRevision.library_state["entry_created_at"].astext,
            DateTime(timezone=True),
        ),
        select(func.min(ResumeWorkspace.created_at))
        .where(ResumeWorkspace.accepted_revision_id == e.ResumeVariantRevision.id)
        .correlate(e.ResumeVariantRevision)
        .scalar_subquery(),
        e.ResumeVariantRevision.created_at,
    )
    rows = list(
        await session.scalars(
            select(e.ResumeVariantRevision)
            .join(e.ResumeVariant, e.ResumeVariant.id == e.ResumeVariantRevision.resume_variant_id)
            .where(
                e.ResumeVariant.library_visible.is_(True),
                e.ResumeVariantRevision.archived_at.is_(None),
                e.ResumeVariantRevision.library_state["replaced_by_id"].astext.is_(None),
            )
            .order_by(
                first_created.desc(),
                func.coalesce(
                    e.ResumeVariantRevision.library_state["entry_id"].astext,
                    cast(e.ResumeVariantRevision.id, String),
                ),
            )
            .limit(limit + 1)
            .offset(offset)
        )
    )
    first_times = {
        id: created
        for id, created in (
            await session.execute(
                select(e.ResumeVariantRevision.id, first_created).where(
                    e.ResumeVariantRevision.id.in_([r.id for r in rows])
                )
            )
        ).all()
    }
    return {
        "items": [
            {
                "id": r.id,
                "entry_id": (r.library_state or {}).get("entry_id", str(r.id)),
                "variant_id": r.resume_variant_id,
                "revision": r.revision,
                "name": r.display_name,
                "metadata_revision": r.metadata_revision,
                "created_at": first_times[r.id],
                "saved_at": r.saved_at,
                "presentation": Presentation.model_validate(r.presentation or {}).model_dump(
                    mode="json"
                ),
                "profile_id": r.profile_id,
            }
            for r in rows[:limit]
        ],
        "has_more": len(rows) > limit,
    }


@router.patch("/resume-library/versions/{id}")
async def rename(id: UUID, payload: c.Rename, session: DB) -> dict[str, Any]:
    row = await svc.require(session, e.ResumeVariantRevision, id, lock=True)
    svc.check_revision(row.metadata_revision, payload.expected_revision)
    if row.display_name != payload.name:
        row.display_name = payload.name
        row.library_state = {
            **(row.library_state or {}),
            "branch_id": str(uuid4()),
            "branch_name": payload.name,
        }
        row.metadata_revision += 1
        row.saved_at = e.utcnow()
    return {
        "saved_at": row.saved_at,
        "name": row.display_name,
        "metadata_revision": row.metadata_revision,
    }


@router.delete("/resume-library/versions/{id}")
async def archive_resume(id: UUID, payload: c.Publish, session: DB) -> dict[str, bool]:
    row = await svc.require(session, e.ResumeVariantRevision, id, lock=True)
    svc.check_revision(row.metadata_revision, payload.expected_revision)
    if await session.scalar(
        select(ApplicationBinding.application_id)
        .where(ApplicationBinding.resume_revision_id == id)
        .limit(1)
    ):
        raise DomainError("resume_in_use")
    if row.archived_at is None:
        row.archived_at = e.utcnow()
        row.metadata_revision += 1
    return {"archived": True}


@router.post("/resume-library/versions/{id}/edit")
async def edit_version(id: UUID, request: Request, session: DB) -> Any:
    from career_agent.resume.grounding import FactEvidence, validate_grounding
    from career_agent.resume.schemas import RevisionRequest

    try:
        payload = RevisionRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise DomainError("invalid_resume_draft", 422) from None
    source = await svc.require(session, e.ResumeVariantRevision, id)
    if source.archived_at:
        raise DomainError("resume_archived")
    variant = await svc.require(session, e.ResumeVariant, source.resume_variant_id, lock=True)
    svc.check_revision(variant.current_revision, payload.expected_revision)
    document = payload.document
    if document.model_dump(mode="json") == source.document:
        return resumes.variant_view(source)
    if (document.profile_id, document.job_revision_id) != (
        source.profile_id,
        source.job_revision_id,
    ):
        raise DomainError("context_revision_mismatch", 422)
    profile = await svc.require(session, e.PersonalProfile, document.profile_id)
    ids = resumes.profile_fact_ids(profile)
    facts = list(
        await session.scalars(
            select(e.PersonalFact).where(e.PersonalFact.id.in_(ids)).with_for_update()
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
        await resumes.snapshot_for(session, document),
        ids,
        {f.id: FactEvidence(f.id, f.revision, f.status, f.statement) for f in facts},
        requirements,
    )
    if findings:
        raise DomainError("grounding_failed", 422)
    return resumes.variant_view(
        await resumes.revise_variant(
            session, source.resume_variant_id, payload.expected_revision, document
        )
    )


def clear_stale_short_text(document: dict[str, Any], original: dict[str, Any]) -> None:
    previous = {i["item_id"]: i for sec in original["sections"] for i in sec["items"]}
    for section in document["sections"]:
        for item in section["items"]:
            before = previous.get(item["item_id"])
            if (
                before
                and item["text"] != before["text"]
                and item.get("short_text") == before.get("short_text")
            ):
                item["short_text"] = None


@router.post("/resume-workspaces/{id}/editions")
async def save_edition(id: UUID, payload: c.ResumeEdit, session: DB) -> dict[str, Any]:
    from sqlalchemy import text

    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    source = await svc.require(session, ResumeWorkspace, id, lock=True)
    existing = await session.scalar(
        select(ResumeWorkspace).where(ResumeWorkspace.request_id == payload.request_id)
    )
    data = payload.document.model_dump(mode="json")
    clear_stale_short_text(data, source.document)
    presentation = (
        payload.presentation.model_dump(mode="json")
        if payload.presentation
        else source.presentation
    )
    if existing:
        if (
            existing.parent_id != id
            or existing.document != data
            or existing.name != payload.name
            or existing.presentation != presentation
        ):
            raise DomainError("idempotency_conflict")
        return draft_view(existing)
    svc.check_revision(source.revision, payload.expected_revision)
    if (source.library_state or {}).get("replaced_by_id"):
        raise DomainError("revision_conflict")
    if source.archived_at:
        raise DomainError("not_found", 404)
    if data == source.document:
        if payload.name != source.name or presentation != source.presentation:
            source.presentation = presentation
            source.saved_at = e.utcnow()
            source.name = payload.name
            source.revision += 1
        return draft_view(source)
    # Editing may alter expression/order/visibility, never introduce another experience.
    allowed = {item["item_id"] for sec in source.document["sections"] for item in sec["items"]}
    if any(item["item_id"] not in allowed for sec in data["sections"] for item in sec["items"]):
        raise DomainError("resume_source_required", 422)
    number = None
    from career_agent.profile_area.evidence import edited_sources

    row = ResumeWorkspace(
        name=payload.name,
        number=number,
        profile_id=source.profile_id,
        source=source.source,
        presentation=presentation,
        source_resume_revision_id=source.accepted_revision_id or source.source_resume_revision_id,
        parent_id=source.id,
        library_state={
            **{k: v for k, v in (source.library_state or {}).items() if k != "replaced_by_id"},
            "entry_id": (source.library_state or {}).get("entry_id", str(source.id)),
            "entry_created_at": (source.library_state or {}).get(
                "entry_created_at", source.created_at.isoformat()
            ),
        },
        document=data,
        request_id=payload.request_id,
    )
    row.content_sources = edited_sources(source, data)
    session.add(row)
    await session.flush()
    source.library_state = {**(source.library_state or {}), "replaced_by_id": str(row.id)}
    return draft_view(row)


@router.post("/resume-workspaces/{id}/resolve")
async def resolve_edition(id: UUID, payload: c.Publish, session: DB) -> dict[str, Any]:
    """Materialize a grounded exact binding without rendering or a provider call."""
    from career_agent.profile_area.evidence import resolve_claims

    await s.workspace(session)
    row = await svc.require(session, ResumeWorkspace, id, lock=True)
    if row.archived_at:
        raise DomainError("not_found", 404)
    if row.accepted_revision_id:
        saved = await svc.require(session, e.ResumeVariantRevision, row.accepted_revision_id)
    else:
        svc.check_revision(row.revision, payload.expected_revision)
        if not any(sec["items"] for sec in row.document["sections"]):
            raise DomainError("resume_content_required", 422)
        issues = await resolve_claims(session, row)
        if issues:
            return {"claim_issues": issues, "resume_revision_id": None, "profile_id": None}
        saved = await s.accept_draft(session, row)
    if saved.archived_at:
        raise DomainError("resume_archived")
    return {"claim_issues": [], "resume_revision_id": saved.id, "profile_id": saved.profile_id}


@router.post("/resume-workspaces/{id}/render")
async def render_edition(
    id: UUID, payload: c.Publish, request: Request, session: DB
) -> dict[str, Any]:
    from career_agent.resume.schemas import ArtifactOut

    await s.workspace(session)  # Global ordering before content/fact/variant locks.
    row = await svc.require(session, ResumeWorkspace, id, lock=True)
    svc.check_revision(row.revision, payload.expected_revision)
    if row.archived_at:
        raise DomainError("not_found", 404)
    if row.accepted_revision_id:
        saved = await svc.require(session, e.ResumeVariantRevision, row.accepted_revision_id)
    else:
        from career_agent.profile_area.evidence import resolve_claims

        if not any(sec["items"] for sec in row.document["sections"]):
            raise DomainError("resume_content_required", 422)
        issues = await resolve_claims(session, row)
        if issues:
            return {"claim_issues": issues, "artifact": None}
        saved = await s.accept_draft(session, row)
    artifact = await resumes.render_variant(session, saved, request.app.state.settings)
    return {
        "claim_issues": [],
        "artifact": ArtifactOut.model_validate(artifact),
        "resume_revision_id": saved.id,
    }


@router.post("/resume-library/versions/{id}/expression")
async def edit_expression(
    id: UUID, payload: c.ExpressionEdit, session: DB, request: Request
) -> dict[str, Any]:
    from sqlalchemy import text

    await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
    source = await svc.require(session, e.ResumeVariantRevision, id, lock=True)
    variant = await svc.require(session, e.ResumeVariant, source.resume_variant_id, lock=True)
    existing = await session.scalar(
        select(ResumeWorkspace).where(ResumeWorkspace.request_id == payload.request_id)
    )
    document = payload.document.model_dump(mode="json")
    clear_stale_short_text(document, source.document)
    payload.document = type(payload.document).model_validate(document)
    presentation = (
        payload.presentation.model_dump(mode="json")
        if payload.presentation
        else source.presentation
    )
    if existing:
        if (
            existing.source_resume_revision_id != id
            or existing.document["sections"] != document["sections"]
            or existing.name != payload.name
            or existing.presentation != presentation
        ):
            raise DomainError("idempotency_conflict")
        return {"workspace": draft_view(existing)}
    generation = None
    if payload.generation_id:
        from career_agent.interview.context import digest
        from career_agent.product.entities import ProductDraft

        generation = await svc.require(session, ProductDraft, payload.generation_id, lock=True)
        proposal = (generation.adopted or {}).get("resume_edit", {})
        if (
            generation.task != "resume_library_compression"
            or generation.status != "completed"
            or proposal.get("source_resume_revision_id") != str(id)
        ):
            raise DomainError("context_revision_mismatch", 422)
        saved_id = (generation.adopted or {}).get("resume_revision_id")
        if saved_id:
            if (generation.adopted or {}).get("save_hash") != digest(
                payload.model_dump(mode="json")
            ):
                raise DomainError("idempotency_conflict")
            return {"resume_revision_id": saved_id}
    svc.check_revision(variant.current_revision, payload.expected_revision)
    if (source.library_state or {}).get("replaced_by_id"):
        raise DomainError("revision_conflict")
    if payload.presentation is not None:
        if payload.expected_metadata_revision is None:
            raise DomainError("revision_conflict")
        svc.check_revision(source.metadata_revision, payload.expected_metadata_revision)
    if source.archived_at:
        raise DomainError("not_found", 404)
    if document == source.document:
        if source.display_name != payload.name or presentation != source.presentation:
            source.presentation = presentation
            source.display_name = payload.name
            source.metadata_revision += 1
            source.saved_at = e.utcnow()
        return {"resume_revision_id": source.id}
    if (payload.document.profile_id, payload.document.job_revision_id) != (
        source.profile_id,
        source.job_revision_id,
    ):
        raise DomainError("context_revision_mismatch", 422)
    allowed = {i["item_id"] for s in source.document["sections"] for i in s["items"]}
    if any(i["item_id"] not in allowed for s in document["sections"] for i in s["items"]):
        raise DomainError("resume_source_required", 422)
    if generation is not None:
        saved = await resumes.revise_variant(
            session, variant.id, payload.expected_revision, payload.document
        )
        saved.display_name = payload.name
        saved.presentation = presentation
        from career_agent.profile_area.naming import branch

        naming = await branch(session, source)
        first_time = await session.scalar(
            select(func.min(ResumeWorkspace.created_at)).where(
                ResumeWorkspace.accepted_revision_id == source.id
            )
        )
        saved.library_state = {
            **naming,
            "entry_id": (source.library_state or {}).get("entry_id", str(source.id)),
            "entry_created_at": (source.library_state or {}).get(
                "entry_created_at", (first_time or source.created_at).isoformat()
            ),
        }
        source.library_state = {**(source.library_state or {}), "replaced_by_id": str(saved.id)}
        from career_agent.evaluation.recording import bind_artifact

        if generation.accepted_model_call_id is None:
            raise DomainError("result_not_available")
        await bind_artifact(
            session,
            generation.accepted_model_call_id,
            saved.id,
            request.app.state.settings.judge_sampling,
        )
        generation.adopted = {
            **(generation.adopted or {}),
            "resume_revision_id": str(saved.id),
            "save_hash": digest(payload.model_dump(mode="json")),
        }
        return {"resume_revision_id": saved.id}
    profile = await svc.require(session, e.PersonalProfile, source.profile_id)
    row = ResumeWorkspace(
        number=None,
        name=payload.name,
        profile_id=profile.id,
        source=profile.data,
        presentation=presentation,
        document={"sections": document["sections"]},
        source_resume_revision_id=id,
        request_id=payload.request_id,
    )
    from career_agent.profile_area.evidence import user_sources

    row.content_sources = user_sources(row.document)
    from career_agent.profile_area.naming import branch

    naming = await branch(session, source)
    first_time = await session.scalar(
        select(func.min(ResumeWorkspace.created_at)).where(
            ResumeWorkspace.accepted_revision_id == source.id
        )
    )
    row.library_state = {
        **naming,
        "entry_id": (source.library_state or {}).get("entry_id", str(source.id)),
        "entry_created_at": (source.library_state or {}).get(
            "entry_created_at", (first_time or source.created_at).isoformat()
        ),
    }
    session.add(row)
    await session.flush()
    source.library_state = {**(source.library_state or {}), "replaced_by_id": str(row.id)}
    return {"workspace": draft_view(row)}


@router.get("/resume-library/subjects/{id}")
async def resume_subject(id: UUID, session: DB) -> dict[str, Any]:
    from career_agent.evaluation.contracts import Subject
    from career_agent.evaluation.entities import InvocationRow

    work = await session.get(ResumeWorkspace, id)
    formal = await session.get(e.ResumeVariantRevision, id)
    if work is None and formal is None:
        raise DomainError("not_found", 404)
    subjects = [str(id)]
    if formal:
        sources = await session.scalars(
            select(ResumeWorkspace.id).where(ResumeWorkspace.accepted_revision_id == id)
        )
        subjects.extend(str(source) for source in sources)
    invocation = await session.scalar(
        select(InvocationRow)
        .where(
            InvocationRow.data["output_ref"].astext.in_(subjects),
            InvocationRow.model_call_id.is_not(None),
        )
        .order_by(InvocationRow.created_at.desc(), InvocationRow.id)
        .limit(1)
    )
    if invocation and invocation.model_call_id:
        call = await svc.require(session, e.ModelCall, invocation.model_call_id)
        if call.status.value == "succeeded" and invocation.data.get(
            "accepted_model_call_id"
        ) == str(call.id):
            return {
                "feedback_target": Subject(
                    subject_id=id,
                    task_type=call.task_type,
                    accepted_model_call_id=call.id,
                    operation_id=invocation.id,
                ).model_dump(mode="json")
            }
    return {"feedback_target": None}


@router.put("/resume-workspaces/{id}/presentation")
async def workspace_presentation(
    id: UUID, payload: PresentationWrite, session: DB
) -> dict[str, Any]:
    row = await svc.require(session, ResumeWorkspace, id, lock=True)
    svc.check_revision(row.revision, payload.expected_revision)
    if row.archived_at:
        raise DomainError("not_found", 404)
    if row.accepted_revision_id:
        raise DomainError("revision_conflict")
    value = Presentation.model_validate(
        payload.model_dump(exclude={"expected_revision"})
    ).model_dump(mode="json")
    if row.presentation != value:
        row.presentation = value
        row.revision += 1
        row.saved_at = e.utcnow()
    return draft_view(row)


@router.put("/resume-library/versions/{id}/presentation")
async def version_presentation(id: UUID, payload: PresentationWrite, session: DB) -> dict[str, Any]:
    row = await svc.require(session, e.ResumeVariantRevision, id, lock=True)
    svc.check_revision(row.metadata_revision, payload.expected_revision)
    if row.archived_at:
        raise DomainError("not_found", 404)
    value = Presentation.model_validate(
        payload.model_dump(exclude={"expected_revision"})
    ).model_dump(mode="json")
    if row.presentation != value:
        row.presentation = value
        row.metadata_revision += 1
        row.saved_at = e.utcnow()
    return {
        "presentation": Presentation.model_validate(row.presentation or {}).model_dump(mode="json"),
        "metadata_revision": row.metadata_revision,
        "saved_at": row.saved_at,
    }
