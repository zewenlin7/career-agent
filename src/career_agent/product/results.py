"""Product projection only; historical reads never silently rebind or regenerate."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.evaluation.contracts import Subject
from career_agent.evaluation.entities import InvocationRow
from career_agent.infrastructure import entities as e
from career_agent.preparation.contracts import PrivateResult, TargetArtifact, WorkflowState
from career_agent.product.contracts import ContextSummary, PackageView, ResultView


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
            wrapper = await require(session, e.PreparationArtifact, outcome.artifact_id)
            target = PrivateResult.model_validate(wrapper.data).output
            if (
                not isinstance(target, TargetArtifact)
                or target.target != kind
                or wrapper.profile_id != profile.id
                or wrapper.job_revision_id != jd.id
            ):
                raise DomainError("context_revision_mismatch")
            item.target_artifact_id = wrapper.id
            item.source_resume_revision_id = target.source_resume_revision_id
            item.versions = dict(target.compatibility_versions or {})
            subject_id = target.result_id or target.resume_revision_id
            if target.result_id:
                result = await require(session, e.PreparationArtifact, target.result_id)
                if result.profile_id != profile.id or result.job_revision_id != jd.id:
                    raise DomainError("context_revision_mismatch")
                item.result_id = result.id
                item.content = result.data["output"]
                item.allowed_actions = ["read"]
            if target.resume_revision_id:
                resume = await require(session, e.ResumeVariantRevision, target.resume_revision_id)
                if resume.profile_id != profile.id or resume.job_revision_id != jd.id:
                    raise DomainError("context_revision_mismatch")
                item.resume_revision_id, item.resume_variant_id, item.revision = (
                    resume.id,
                    resume.resume_variant_id,
                    resume.revision,
                )
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
        elif outcome.status == "pending":
            item.allowed_actions = (
                ["provide_input"] if state.outcome.status == "needs_input" else ["decide"]
            )
        results.append(item)
    return PackageView(
        package_id=id, run_id=package.run_id, status=state.outcome.status, results=results
    )
