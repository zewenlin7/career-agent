from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from career_agent.api.dependencies import DB
from career_agent.application import resumes as svc
from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.resume.renderer import CompileError
from career_agent.resume.schemas import (
    ArtifactOut,
    RenderReport,
    RenderRequest,
    ResumeDocument,
    RevisionRequest,
    VariantOut,
)
from career_agent.resume.store import ArtifactStore

router = APIRouter(prefix="/api/v1")


@router.post("/resume-variants", response_model=VariantOut, status_code=201)
async def create_variant(payload: ResumeDocument, session: DB) -> VariantOut:
    return svc.variant_view(await svc.create_variant(session, payload))


@router.get("/resume-variants/{variant_id}", response_model=VariantOut)
async def get_variant(
    variant_id: UUID, session: DB, revision: Annotated[int | None, Query(ge=1)] = None
) -> VariantOut:
    return svc.variant_view(await svc.get_revision(session, variant_id, revision))


@router.post("/resume-variants/{variant_id}/revisions", response_model=VariantOut, status_code=201)
async def revise_variant(variant_id: UUID, payload: RevisionRequest, session: DB) -> VariantOut:
    return svc.variant_view(
        await svc.revise_variant(session, variant_id, payload.expected_revision, payload.document)
    )


@router.post("/resume-variants/{variant_id}/render", response_model=ArtifactOut, status_code=201)
async def render_variant(
    variant_id: UUID, payload: RenderRequest, request: Request, session: DB
) -> e.RenderArtifact:
    row = await svc.get_revision(session, variant_id, payload.revision)
    return await svc.render_variant(session, row, request.app.state.settings)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(artifact_id: UUID, session: DB) -> e.RenderArtifact:
    return await require(session, e.RenderArtifact, artifact_id)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: UUID, request: Request, session: DB) -> Response:
    artifact = await require(session, e.RenderArtifact, artifact_id)
    report = RenderReport.model_validate(artifact.report)
    if (
        report.render_status != "accepted"
        or artifact.artifact_ref is None
        or not artifact.file_hash
    ):
        raise DomainError("artifact_not_accepted", 409)
    try:
        content = ArtifactStore(request.app.state.settings.data_dir).read(
            artifact.artifact_ref, artifact.file_hash
        )
    except CompileError as exc:
        raise DomainError(exc.code, 409) from None
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="resume-{artifact_id}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
