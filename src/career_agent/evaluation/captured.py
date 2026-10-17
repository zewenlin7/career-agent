"""Private, versioned authoritative rows for isolated replay; never a production restore API."""

import base64
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic_core import to_jsonable_python
from sqlalchemy import DateTime, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.resumes import profile_fact_ids
from career_agent.application.services import require
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.resume.renderer import CompileError
from career_agent.resume.store import ArtifactStore

# Explicit dependency closure only; no steps, model bodies, secrets or arbitrary tables.
MODELS = {
    c.__tablename__: c
    for c in (
        e.SourceDocument,
        e.PersonalProfile,
        e.PersonalFact,
        e.Company,
        e.JobPosting,
        e.JobRevision,
        e.JobRequirement,
        e.Application,
        e.ResumeVariant,
        e.ResumeVariantRevision,
        e.RenderArtifact,
        e.CompanyResearch,
        e.PreparationArtifact,
        e.AgentRun,
        e.StarStory,
        e.KnowledgeNote,
        e.InterviewSession,
    )
}


async def freeze_inputs(
    session: AsyncSession,
    profile_id: UUID,
    job_revision_id: UUID,
    resume_revision_id: UUID | None,
    request: dict[str, Any],
    data_dir: Path | None = None,
) -> dict[str, Any]:
    rows: dict[tuple[str, UUID], dict[str, Any]] = {}
    files: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    async def referenced(model: Any, id: Any) -> None:
        if id is None:
            return
        row = await session.get(model, UUID(str(id)))
        if row is None:
            missing.append("missing_dependency")
        else:
            await add(row)

    async def json_dependencies(value: Any) -> None:
        if isinstance(value, dict):
            links = {
                "application_package_id": e.PreparationArtifact,
                "artifact_id": e.PreparationArtifact,
                "result_id": e.PreparationArtifact,
                "fit_analysis_id": e.PreparationArtifact,
                "greeting_id": e.PreparationArtifact,
                "interview_prep_id": e.PreparationArtifact,
                "research_report_id": e.CompanyResearch,
                "render_report_id": e.RenderArtifact,
                "render_artifact_id": e.RenderArtifact,
                "resume_revision_id": e.ResumeVariantRevision,
                "source_resume_revision_id": e.ResumeVariantRevision,
            }
            for key, model in links.items():
                if value.get(key):
                    await referenced(model, value[key])
            for child in value.values():
                await json_dependencies(child)
        elif isinstance(value, list):
            for child in value:
                await json_dependencies(child)

    async def add(row: Any) -> None:
        table = row.__table__
        key = (table.name, row.id)
        if key in rows:
            return
        if table.name not in MODELS:
            raise ModelGatewayError("case_incompatible")
        values = {column.name: getattr(row, column.name) for column in table.columns}
        rows[key] = {"table": table.name, "values": to_jsonable_python(values)}
        for constraint in table.foreign_key_constraints:
            elements = list(constraint.elements)
            if any(values[f.parent.name] is None for f in elements):
                continue
            model = MODELS.get(elements[0].column.table.name)
            if model is None:
                missing.append("unsupported_dependency")
                continue
            parent = await session.scalar(
                select(model).where(
                    *[getattr(model, f.column.name) == values[f.parent.name] for f in elements]
                )
            )
            if parent is None:
                missing.append("missing_dependency")
            else:
                await add(parent)
        if isinstance(row, e.PersonalProfile):
            for fact_id in sorted(profile_fact_ids(row), key=str):
                await referenced(e.PersonalFact, fact_id)
        if isinstance(row, e.JobRevision):
            for requirement in await session.scalars(
                select(e.JobRequirement).where(e.JobRequirement.job_revision_id == row.id)
            ):
                await add(requirement)
        if isinstance(row, e.ResumeVariant):
            head = await session.scalar(
                select(e.ResumeVariantRevision).where(
                    e.ResumeVariantRevision.resume_variant_id == row.id,
                    e.ResumeVariantRevision.revision == row.current_revision,
                )
            )
            if head is not None:
                await add(head)
        if isinstance(row, e.PreparationArtifact):
            await json_dependencies(row.data)
        if isinstance(row, e.RenderArtifact) and row.artifact_ref:
            if data_dir is None:
                missing.append("artifact_store_unavailable")
            else:
                observed: dict[str, Any] = {"hash": row.file_hash}
                try:
                    content = ArtifactStore(data_dir).read(row.artifact_ref, row.file_hash or "")
                    observed["private_pdf_base64"] = base64.b64encode(content).decode("ascii")
                except CompileError as exc:
                    observed["failure"] = exc.code
                files[str(row.artifact_ref)] = observed

    profile = await require(session, e.PersonalProfile, profile_id)
    await add(profile)
    for fact_id in sorted(profile_fact_ids(profile), key=str):
        await add(await require(session, e.PersonalFact, fact_id))
    job = await require(session, e.JobRevision, job_revision_id)
    await add(job)
    for requirement in await session.scalars(
        select(e.JobRequirement).where(e.JobRequirement.job_revision_id == job.id)
    ):
        await add(requirement)
    application = await session.scalar(
        select(e.Application).where(e.Application.job_id == job.job_id)
    )
    if application is not None:
        await add(application)
    if resume_revision_id:
        await add(await require(session, e.ResumeVariantRevision, resume_revision_id))
    for binding in request.get("bindings", {}).values():
        if isinstance(binding, dict) and binding.get("resume_revision_id"):
            await referenced(e.ResumeVariantRevision, binding["resume_revision_id"])
    for key, model in [("star_story_ids", e.StarStory), ("knowledge_note_ids", e.KnowledgeNote)]:
        for id in request.get(key, []):
            await referenced(model, id)
    await json_dependencies(request)
    posting = await require(session, e.JobPosting, job.job_id)
    for research in await session.scalars(
        select(e.CompanyResearch).where(e.CompanyResearch.company_id == posting.company_id)
    ):
        await add(research)
    for artifact in await session.scalars(
        select(e.PreparationArtifact).where(
            e.PreparationArtifact.profile_id == profile_id,
            e.PreparationArtifact.job_revision_id == job_revision_id,
        )
    ):
        await add(artifact)
    return {
        "version": "captured-replay-v1",
        "rows": list(rows.values()),
        "request": request,
        "closure_complete": not missing,
        "evaluation_clock": e.utcnow().isoformat(),
        "missing": sorted(set(missing)),
        "artifact_files": files,
    }


async def restore_inputs(
    session: AsyncSession, frozen: dict[str, Any], data_dir: Path | None = None
) -> None:
    if frozen.get("version") != "captured-replay-v1" or not frozen.get("closure_complete"):
        raise ModelGatewayError("case_incompatible")
    pending = list(frozen["rows"])
    restored: set[tuple[str, str]] = set()
    while pending:
        progressed = False
        for row in list(pending):
            model = MODELS.get(row["table"])
            if model is None:
                raise ModelGatewayError("case_incompatible")
            table: Any = model.__table__
            values = dict(row["values"])
            if set(values) != {c.name for c in table.columns}:
                raise ModelGatewayError("case_incompatible")
            dependencies: set[tuple[str, str]] = set()
            for constraint in table.foreign_key_constraints:
                elements = list(constraint.elements)
                if any(values[f.parent.name] is None for f in elements):
                    continue
                parent = next(
                    (
                        item
                        for item in frozen["rows"]
                        if item["table"] == elements[0].column.table.name
                        and all(
                            item["values"][f.column.name] == values[f.parent.name] for f in elements
                        )
                    ),
                    None,
                )
                if parent is None:
                    raise ModelGatewayError("case_incompatible")
                dependencies.add((parent["table"], parent["values"]["id"]))
            if not dependencies <= restored:
                continue
            for column in table.columns:
                if values[column.name] is not None:
                    if isinstance(column.type, Uuid):
                        values[column.name] = UUID(values[column.name])
                    elif isinstance(column.type, DateTime):
                        values[column.name] = datetime.fromisoformat(values[column.name])
            session.add(model(**values))
            await session.flush()
            restored.add((table.name, str(values["id"])))
            pending.remove(row)
            progressed = True
        if not progressed:
            raise ModelGatewayError("case_incompatible")
    for ref, observed in frozen.get("artifact_files", {}).items():
        if data_dir is None:
            raise ModelGatewayError("case_incompatible")
        if observed.get("failure"):
            # Missing/corrupt frozen artifacts stay unavailable; never consult ambient files.
            continue
        try:
            content = base64.b64decode(observed["private_pdf_base64"], validate=True)
        except (ValueError, KeyError):
            raise ModelGatewayError("case_incompatible") from None
        if hashlib.sha256(content).hexdigest() != observed["hash"]:
            raise ModelGatewayError("case_incompatible")
        ArtifactStore(data_dir).write(UUID(ref), content)


def replay_source(source: dict[str, Any]) -> dict[str, Any]:
    frozen = source.get("replay")
    if (
        source.get("captured_source_version") != "captured-source-v1"
        or not isinstance(frozen, dict)
        or frozen.get("version") != "captured-replay-v1"
        or not frozen.get("closure_complete")
        or not isinstance(frozen.get("rows"), list)
        or not isinstance(frozen.get("request"), dict)
        or not isinstance(frozen.get("evaluation_clock"), str)
    ):
        raise ModelGatewayError("case_incompatible")
    try:
        clock = datetime.fromisoformat(frozen["evaluation_clock"])
        if clock.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError:
        raise ModelGatewayError("case_incompatible") from None
    if "goal" in frozen["request"] and not frozen.get("agent_goal_compatible"):
        raise ModelGatewayError("case_incompatible")
    return {"captured": frozen, "request": frozen["request"]}
