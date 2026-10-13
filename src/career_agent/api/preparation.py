"""Explicit synchronous workflows; no background worker, automatic application or messaging."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from career_agent.api.dependencies import DB
from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import WorkflowRequest
from career_agent.preparation.providers import dependencies
from career_agent.preparation.workflows import PreparationWorkflow

router = APIRouter(prefix="/api/v1")


@router.post("/workflows/{workflow}", status_code=201)
async def prepare(
    workflow: Literal["prepare_application", "prepare_interview"],
    payload: WorkflowRequest,
    request: Request,
    session: DB,
) -> dict[str, Any]:
    try:
        factory = getattr(request.app.state, "preparation_dependencies", dependencies)
        async with factory(request.app.state.settings, payload.mode) as (gateway, research):
            runner = PreparationWorkflow(
                session, request.app.state.settings, gateway, research, payload
            )
            return await runner.execute(workflow)
    except ModelGatewayError as exc:
        raise DomainError(exc.code, 409) from None


@router.get("/preparation-artifacts/{id}")
async def artifact(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, e.PreparationArtifact, id)
    return {
        "id": row.id,
        "run_id": row.run_id,
        "job_revision_id": row.job_revision_id,
        "profile_id": row.profile_id,
        "data": row.data,
    }


@router.get("/company-research/{id}")
async def research(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, e.CompanyResearch, id)
    return {
        "id": row.id,
        "company_id": row.company_id,
        "research_version": row.research_version,
        "fetched_at": row.fetched_at,
        "expires_at": row.expires_at,
        "data": row.data,
    }


@router.get("/runs/{id}/calls")
async def calls(id: UUID, session: DB) -> dict[str, Any]:
    await require(session, e.AgentRun, id)
    step_ids = select(e.AgentStep.id).where(e.AgentStep.run_id == id)
    models = list(
        await session.scalars(
            select(e.ModelCall)
            .where(e.ModelCall.step_id.in_(step_ids))
            .order_by(e.ModelCall.created_at)
        )
    )
    tools = list(
        await session.scalars(
            select(e.ToolCall)
            .where(e.ToolCall.step_id.in_(step_ids))
            .order_by(e.ToolCall.created_at)
        )
    )
    return {
        "model_calls": [
            {
                k: getattr(r, k)
                for k in [
                    "id",
                    "step_id",
                    "task_type",
                    "provider",
                    "model",
                    "status",
                    "versions",
                    "usage",
                    "latency_ms",
                    "attempts",
                    "estimated_cost",
                    "error_code",
                    "schema_validation_state",
                ]
            }
            for r in models
        ],
        "tool_calls": [
            {
                k: getattr(r, k)
                for k in [
                    "id",
                    "step_id",
                    "tool_name",
                    "tool_version",
                    "usage",
                    "attempt",
                    "status",
                    "latency_ms",
                    "error_code",
                ]
            }
            for r in tools
        ],
    }


@router.get("/jobs/{job_id}/preparation-packages")
async def job_packages(
    job_id: UUID, session: DB, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    from career_agent.domain.rules import DomainError

    if not 1 <= limit <= 100 or offset < 0:
        raise DomainError("invalid_pagination", 422)
    await require(session, e.JobPosting, job_id)
    rows = await session.scalars(
        select(e.PreparationArtifact)
        .join(e.JobRevision)
        .where(
            e.JobRevision.job_id == job_id,
            e.PreparationArtifact.data["kind"].astext == "package",
        )
        .order_by(e.PreparationArtifact.created_at.desc(), e.PreparationArtifact.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "job_revision_id": r.job_revision_id,
            "profile_id": r.profile_id,
            "outcome": r.data["output"].get("outcome"),
        }
        for r in rows
    ]


@router.get("/applications/{application_id}/preparation-packages")
async def application_packages(
    application_id: UUID, session: DB, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    row = await require(session, e.Application, application_id)
    return await job_packages(row.job_id, session, limit, offset)


@router.get("/runs/{run_id}/package")
async def run_package(run_id: UUID, session: DB) -> dict[str, Any]:
    await require(session, e.AgentRun, run_id)
    row = await session.scalar(
        select(e.PreparationArtifact)
        .where(
            e.PreparationArtifact.run_id == run_id,
            e.PreparationArtifact.data["kind"].astext == "package",
        )
        .order_by(e.PreparationArtifact.created_at.desc())
    )
    if row is None:
        raise DomainError("not_found", 404)
    return await artifact(row.id, session)


@router.get("/preparation-artifacts/{id}/context")
async def package_context(id: UUID, session: DB) -> dict[str, Any]:
    from career_agent.application.resumes import get_revision, variant_view
    from career_agent.preparation.contracts import PrivateResult, WorkflowState

    row = await require(session, e.PreparationArtifact, id)
    parsed = PrivateResult.model_validate(row.data)
    if not isinstance(parsed.output, WorkflowState):
        raise DomainError("invalid_application_package", 422)
    st = parsed.output
    profile = await require(session, e.PersonalProfile, row.profile_id)
    jd = await require(session, e.JobRevision, row.job_revision_id)
    reqs = list(
        await session.scalars(
            select(e.JobRequirement).where(e.JobRequirement.id.in_(st.requirement_refs))
        )
    )
    if (
        st.profile_id != profile.id
        or st.profile_revision != profile.revision
        or st.job_revision_id != jd.id
        or st.job_revision != jd.revision
        or any(r.job_revision_id != jd.id for r in reqs)
        or len(reqs) != len(st.requirement_refs)
    ):
        raise DomainError("context_revision_mismatch")
    variants = {}
    if st.resume_variant_id and st.resume_variant_revision:
        variants["output"] = variant_view(
            await get_revision(session, st.resume_variant_id, st.resume_variant_revision)
        ).model_dump(mode="json")
    for target, binding in st.bindings.items():
        if binding.resume_revision_id:
            v = await require(session, e.ResumeVariantRevision, binding.resume_revision_id)
            variants[target] = variant_view(v).model_dump(mode="json")
    if any(v["document"]["profile_id"] != str(profile.id) for v in variants.values()):
        raise DomainError("context_revision_mismatch")
    return {
        "profile": {"id": profile.id, "revision": profile.revision, "data": profile.data},
        "job": {
            "id": jd.job_id,
            "job_revision_id": jd.id,
            "revision": jd.revision,
            "title": jd.title,
            "jd_text": jd.jd_text,
        },
        "requirements": [
            {"id": r.id, "text": r.text, "source_quote": r.source_quote} for r in reqs
        ],
        "resumes": variants,
        "research_report_id": st.research_report_id,
        "fit_analysis_id": st.fit_analysis_id,
    }


@router.get("/resume-revisions")
async def resume_choices(
    profile_id: UUID,
    session: DB,
    job_revision_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 100 or offset < 0:
        raise DomainError("invalid_pagination", 422)
    await require(session, e.PersonalProfile, profile_id)
    if job_revision_id:
        await require(session, e.JobRevision, job_revision_id)
    rows = list(
        await session.scalars(
            select(e.ResumeVariantRevision)
            .where(
                e.ResumeVariantRevision.profile_id == profile_id,
            )
            .order_by(e.ResumeVariantRevision.created_at.desc(), e.ResumeVariantRevision.id)
            .limit(limit)
            .offset(offset)
        )
    )
    uses = await session.scalars(
        select(e.PreparationArtifact)
        .where(
            e.PreparationArtifact.profile_id == profile_id,
            e.PreparationArtifact.data["kind"].astext == "target",
        )
        .order_by(e.PreparationArtifact.created_at.desc())
    )
    last_used = {}
    for use in uses:
        source = use.data["output"].get("source_resume_revision_id")
        if source and source not in last_used:
            last_used[source] = use.created_at
    job_ids = set()
    if job_revision_id:
        selected_jd = await require(session, e.JobRevision, job_revision_id)
        job_ids = set(
            await session.scalars(
                select(e.JobRevision.id).where(e.JobRevision.job_id == selected_jd.job_id)
            )
        )
    return [
        {
            "resume_revision_id": r.id,
            "resume_variant_id": r.resume_variant_id,
            "revision": r.revision,
            "profile_id": r.profile_id,
            "job_revision_id": r.job_revision_id,
            "hints": {
                "original": r.revision == 1,
                "same_jd": bool(job_revision_id and r.job_revision_id == job_revision_id),
                "same_job": r.job_revision_id in job_ids,
                "last_used_at": last_used.get(str(r.id)),
            },
            "created_at": r.created_at,
        }
        for r in rows
    ]
