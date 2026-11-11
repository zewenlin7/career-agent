"""Product projection only; historical reads never silently rebind or regenerate."""

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import read_application, require
from career_agent.domain.rules import DomainError
from career_agent.evaluation.contracts import Subject
from career_agent.evaluation.entities import InvocationRow
from career_agent.infrastructure import entities as e
from career_agent.preparation.contracts import PrivateResult, TargetArtifact, WorkflowState
from career_agent.product.contracts import (
    ContextSummary,
    PackageView,
    Page,
    ResultView,
    TaskHistoryItem,
)


async def package_view(session: AsyncSession, id: UUID) -> PackageView:
    package = await require(session, e.PreparationArtifact, id)
    private = PrivateResult.model_validate(package.data)
    if private.kind != "package" or not isinstance(private.output, WorkflowState):
        raise DomainError("invalid_application_package", 422)
    state = private.output
    if state.outcome is None:
        raise DomainError("historical_outcome_unavailable")
    profile = await require(session, e.PersonalProfile, package.profile_id)
    jd = await require(session, e.JobRevision, package.job_revision_id)
    job = await require(session, e.JobPosting, jd.job_id)
    context = ContextSummary(
        profile_id=profile.id,
        profile_revision=profile.revision,
        job_id=job.id,
        job_revision_id=jd.id,
        job_revision=jd.revision,
        job_title=jd.title,
        company_id=job.company_id,
    )
    results = []
    for kind, outcome in state.outcome.targets.items():
        item = ResultView(
            kind=kind,
            status="success" if outcome.status == "completed" else outcome.status,
            context=context,
            reason=outcome.reason,
            reused=any(n.name == kind and n.status == "reused" for n in state.outcome.nodes),
        )
        if outcome.artifact_id:
            await populate_target(session, outcome.artifact_id, item)
        elif outcome.status == "pending":
            item.allowed_actions = (
                ["provide_input"] if state.outcome.status == "needs_input" else ["decide"]
            )
        results.append(item)
    return PackageView(
        package_id=id, run_id=package.run_id, status=state.outcome.status, results=results
    )


async def populate_target(session: AsyncSession, id: UUID, item: ResultView) -> None:
    wrapper = await require(session, e.PreparationArtifact, id)
    target = PrivateResult.model_validate(wrapper.data).output
    if (
        not isinstance(target, TargetArtifact)
        or target.target != item.kind
        or wrapper.profile_id != item.context.profile_id
        or wrapper.job_revision_id != item.context.job_revision_id
    ):
        raise DomainError("context_revision_mismatch")
    from career_agent.product.entities import ProductDraft, ResultRemoval

    item.available = not bool(
        await session.scalar(select(ResultRemoval.id).where(ResultRemoval.target_id == wrapper.id))
    )
    item.target_artifact_id = wrapper.id
    item.source_resume_revision_id = target.source_resume_revision_id
    if target.source_resume_revision_id:
        source_resume = await require(
            session, e.ResumeVariantRevision, target.source_resume_revision_id
        )
        item.source_resume_name = source_resume.display_name
    producer = await session.scalar(
        select(ProductDraft).where(ProductDraft.run_id == wrapper.run_id)
    )
    if producer:
        original_id = producer.request.get("source_artifact_id")
        item.source_original_target_id = UUID(original_id) if original_id else None
        if producer.task in {"resume_refinement", "greeting_refinement"}:
            item.source_profile_id = wrapper.profile_id
    elif item.kind == "resume_tailoring":
        # Tailoring receives all verified Profile facts, not just Resume-linked evidence.
        item.source_profile_id = wrapper.profile_id
    if target.interview_context:
        research_id = target.interview_context.get("research_report_id")
        item.source_research_id = UUID(research_id) if research_id else None
    elif item.kind in {"greeting_generation", "interview_preparation"} and not producer:
        # The exact producer package identifies historical optional research. Refinements
        # have no package and must not inherit the predecessor's research selection.
        package = await session.scalar(
            select(e.PreparationArtifact).where(
                e.PreparationArtifact.run_id == wrapper.run_id,
                e.PreparationArtifact.data["kind"].astext == "package",
            )
        )
        if package:
            state = package.data.get("output", {})
            research_id = state.get("research_report_id")
            item.source_research_id = UUID(research_id) if research_id else None
    # Prospective refinement consumes the selected result, not its own predecessor.
    # Old Prep without its frozen input contract remains readable, never executable.
    if item.kind in {"resume_tailoring", "greeting_generation"} or target.interview_context:
        item.refinement_resume_revision_id = (
            target.resume_revision_id or target.source_resume_revision_id
        )
        if item.refinement_resume_revision_id:
            refinement_resume = await require(
                session, e.ResumeVariantRevision, item.refinement_resume_revision_id
            )
            item.refinement_resume_name = refinement_resume.display_name
        if item.kind in {"resume_tailoring", "greeting_generation"}:
            item.refinement_profile_id = wrapper.profile_id
    item.versions = dict(target.compatibility_versions or {})
    subject_id = target.result_id or target.resume_revision_id
    if target.result_id:
        result = await require(session, e.PreparationArtifact, target.result_id)
        if (
            result.profile_id != item.context.profile_id
            or result.job_revision_id != item.context.job_revision_id
        ):
            raise DomainError("context_revision_mismatch")
        item.result_id = result.id
        item.content = result.data["output"]
        item.allowed_actions = ["read"]
    if target.resume_revision_id:
        resume = await require(session, e.ResumeVariantRevision, target.resume_revision_id)
        if (
            resume.profile_id != item.context.profile_id
            or resume.job_revision_id != item.context.job_revision_id
        ):
            raise DomainError("context_revision_mismatch")
        item.resume_revision_id, item.resume_variant_id, item.revision = (
            resume.id,
            resume.resume_variant_id,
            resume.revision,
        )
        # Follow the stable library entry for its current name, retaining exact content below.
        named = resume
        seen = {resume.id}
        while (named.library_state or {}).get("replaced_by_id"):
            next_id = UUID(named.library_state["replaced_by_id"])
            if next_id in seen:
                break
            seen.add(next_id)
            named = await require(session, e.ResumeVariantRevision, next_id)
        item.available = item.available and named.archived_at is None
        item.resume_name = named.display_name or resume.display_name or "简历"
        item.content = resume.document
        item.allowed_actions = ["read", "create_revision"]
        if target.render_artifact_id:
            artifact = await require(session, e.RenderArtifact, target.render_artifact_id)
            if (
                artifact.resume_variant_id != resume.resume_variant_id
                or artifact.resume_variant_revision != resume.revision
            ):
                raise DomainError("context_revision_mismatch")
            item.render_artifact_id = artifact.id
            if artifact.report["render_status"] == "accepted":
                item.download_url = f"/api/v1/artifacts/{artifact.id}/download"
                item.allowed_actions.append("download")
    if subject_id:
        invocation = await session.scalar(
            select(InvocationRow)
            .where(
                InvocationRow.data["output_ref"].astext == str(subject_id),
                InvocationRow.model_call_id.is_not(None),
            )
            .order_by(InvocationRow.created_at.desc(), InvocationRow.id)
            .limit(1)
        )
        if invocation and invocation.model_call_id:
            call = await require(session, e.ModelCall, invocation.model_call_id)
            if call.status.value == "succeeded" and invocation.data.get(
                "accepted_model_call_id"
            ) == str(call.id):
                item.feedback_target = Subject(
                    subject_id=subject_id,
                    task_type=call.task_type,
                    accepted_model_call_id=call.id,
                    operation_id=invocation.id,
                )
                item.allowed_actions.append("feedback")
                item.versions.update(
                    {
                        k: v
                        for k, v in call.versions.items()
                        if k
                        in {
                            "prompt_version",
                            "prompt_hash",
                            "input_schema_version",
                            "output_schema_version",
                            "model_policy_version",
                            "workflow_version",
                        }
                    }
                )


async def history(
    session: AsyncSession,
    id: UUID,
    target: Literal[
        "fit_analysis", "resume_tailoring", "greeting_generation", "interview_preparation"
    ],
    limit: int = 20,
    offset: int = 0,
) -> Page[TaskHistoryItem]:
    application = await read_application(session, id)
    job = await require(session, e.JobPosting, application.job_id)
    stmt = (
        select(e.PreparationArtifact)
        .join(e.JobRevision, e.JobRevision.id == e.PreparationArtifact.job_revision_id)
        .where(
            e.JobRevision.job_id == job.id,
            e.PreparationArtifact.data["kind"].astext == "target",
            e.PreparationArtifact.data["output"]["target"].astext == target,
        )
        .order_by(e.PreparationArtifact.created_at.desc(), e.PreparationArtifact.id)
    )
    from career_agent.product.entities import ResultRemoval

    stmt = stmt.where(~e.PreparationArtifact.id.in_(select(ResultRemoval.target_id)))
    found = list(await session.scalars(stmt))
    items = []
    for row in found:
        profile = await require(session, e.PersonalProfile, row.profile_id)
        jd = await require(session, e.JobRevision, row.job_revision_id)
        item = ResultView(
            kind=target,
            status="success",
            reused=False,
            context=ContextSummary(
                profile_id=profile.id,
                profile_revision=profile.revision,
                job_id=job.id,
                job_revision_id=jd.id,
                job_revision=jd.revision,
                job_title=jd.title,
                company_id=job.company_id,
            ),
        )
        await populate_target(session, row.id, item)
        if item.resume_revision_id:
            named = await require(session, e.ResumeVariantRevision, item.resume_revision_id)
            seen = {named.id}
            while (named.library_state or {}).get("replaced_by_id"):
                next_id = UUID(named.library_state["replaced_by_id"])
                if next_id in seen:
                    break
                seen.add(next_id)
                named = await require(session, e.ResumeVariantRevision, next_id)
            if named.archived_at:
                continue
        items.append(TaskHistoryItem(created_at=row.created_at, result=item))
    return Page(
        items=items[offset : offset + limit],
        limit=limit,
        offset=offset,
        has_more=len(items) > offset + limit,
    )


async def exact(session: AsyncSession, application_id: UUID, id: UUID) -> TaskHistoryItem:
    app = await read_application(session, application_id)
    row = await require(session, e.PreparationArtifact, id)
    if row.data.get("kind") != "target":
        wrapper = await session.scalar(
            select(e.PreparationArtifact)
            .where(
                e.PreparationArtifact.data["kind"].astext == "target",
                e.PreparationArtifact.data["output"]["result_id"].astext == str(id),
            )
            .order_by(e.PreparationArtifact.created_at.desc(), e.PreparationArtifact.id)
            .limit(1)
        )
        if wrapper is None:
            raise DomainError("not_found", 404)
        row = wrapper
    jd = await require(session, e.JobRevision, row.job_revision_id)
    job = await require(session, e.JobPosting, jd.job_id)
    if job.id != app.job_id:
        raise DomainError("context_revision_mismatch")
    profile = await require(session, e.PersonalProfile, row.profile_id)
    item = ResultView(
        kind=row.data["output"]["target"],
        status="success",
        reused=False,
        context=ContextSummary(
            profile_id=profile.id,
            profile_revision=profile.revision,
            job_id=job.id,
            job_revision_id=jd.id,
            job_revision=jd.revision,
            job_title=jd.title,
            company_id=job.company_id,
        ),
    )
    await populate_target(session, row.id, item)
    return TaskHistoryItem(created_at=row.created_at, result=item)


async def greeting_removal(
    session: AsyncSession, application_id: UUID, id: UUID, request_id: UUID | None = None
) -> dict[str, object]:
    from career_agent.infrastructure.claims import claim
    from career_agent.product.entities import MaterialSubmission, ResultRemoval

    await require(session, e.Application, application_id, lock=True)
    item = await exact(session, application_id, id)
    if item.result.kind != "greeting_generation" or item.result.target_artifact_id != id:
        raise DomainError("context_revision_mismatch")
    used = list(
        await session.scalars(
            select(MaterialSubmission.display_number)
            .where(
                MaterialSubmission.greeting_id == item.result.result_id,
            )
            .order_by(MaterialSubmission.display_number)
        )
    )
    old = await session.scalar(select(ResultRemoval).where(ResultRemoval.target_id == id))
    if request_id and not used and not old:
        await claim(session, "result-removal:" + str(request_id))
        collision = await session.scalar(
            select(ResultRemoval).where(ResultRemoval.request_id == request_id)
        )
        if collision:
            raise DomainError("idempotency_conflict")
        session.add(
            ResultRemoval(application_id=application_id, target_id=id, request_id=request_id)
        )
        await session.flush()
    return {"deleted": bool(old or (request_id and not used)), "used_in": used}
