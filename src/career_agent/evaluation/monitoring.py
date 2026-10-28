"""Pending quality work and independent human/feedback records; no worker or control loop."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.evaluation import entities as q
from career_agent.evaluation.contracts import (
    Annotation,
    CapturePayload,
    Feedback,
    JudgeSamplingPolicy,
    JudgeSpec,
    SamplingReason,
    Subject,
)
from career_agent.evaluation.prompts import PROMPT
from career_agent.evaluation.sampling import decide
from career_agent.evaluation.store import capture
from career_agent.infrastructure import entities as e
from career_agent.preparation.providers import POLICY


async def resolve_subject(session: AsyncSession, subject: Subject) -> q.InvocationRow:
    if subject.accepted_model_call_id is None:
        raise DomainError("subject_provenance_unavailable")
    call = await require(session, e.ModelCall, subject.accepted_model_call_id)
    if call.status.value != "succeeded" or call.task_type != subject.task_type:
        raise DomainError("subject_provenance_mismatch")
    invocation = await session.scalar(
        select(q.InvocationRow).where(q.InvocationRow.model_call_id == call.id)
    )
    output_matches = invocation is not None and invocation.data.get("output_ref") == str(
        subject.subject_id
    )
    if invocation is not None and not output_matches:
        from career_agent.profile_area.contracts import ResumeDraftData
        from career_agent.profile_area.entities import ResumeWorkspace

        source = await session.scalar(
            select(ResumeWorkspace).where(
                ResumeWorkspace.accepted_revision_id == subject.subject_id,
                ResumeWorkspace.id == invocation.data.get("output_ref"),
            )
        )
        formal = await session.get(e.ResumeVariantRevision, subject.subject_id)
        output_matches = (
            source is not None
            and formal is not None
            and (
                ResumeDraftData.model_validate(source.document).model_dump(mode="json")
                == ResumeDraftData.model_validate(
                    {"sections": formal.document["sections"]}
                ).model_dump(mode="json")
            )
        )
    if (
        invocation is None
        or not output_matches
        or invocation.data.get("accepted_model_call_id") != str(call.id)
        or invocation.data.get("logical_operation_id")
        != (str(call.logical_operation_id) if call.logical_operation_id else None)
        or subject.operation_id is not None
        and subject.operation_id != invocation.id
    ):
        raise DomainError("subject_provenance_unavailable")
    return invocation


async def enqueue(
    session: AsyncSession,
    subject: Subject,
    policy: JudgeSamplingPolicy,
    reason: SamplingReason | None = None,
) -> q.SamplingRow | None:
    decision = decide(subject, policy, reason)
    if decision is None:
        return None
    await resolve_subject(session, subject)
    await require(session, e.ModelCall, subject.accepted_model_call_id, lock=True)  # type: ignore[arg-type]
    old = await session.scalar(
        select(q.SamplingRow).where(q.SamplingRow.decision_key == decision.decision_key)
    )
    if old:
        return old
    call = await require(session, e.ModelCall, subject.accepted_model_call_id)  # type: ignore[arg-type]
    controls = call.versions.get("control_metadata", {})
    rate = controls.get("effective_sampling_rate")
    if rate is not None:
        adjusted = policy.model_copy(deep=True)
        from decimal import Decimal

        adjusted.per_task[subject.task_type] = Decimal(str(rate))
        decision = decide(subject, adjusted, reason)
        assert decision is not None
        decision.effective_control_revision = controls.get("effective_state_revision")
    row = q.SamplingRow(
        subject_id=subject.subject_id,
        decision_key=decision.decision_key,
        data=decision.model_dump(mode="json"),
    )
    session.add(row)
    await session.flush()
    if decision.sampled:
        spec = JudgeSpec(
            target=subject.task_type,
            prompt_version=PROMPT.prompt_version,
            prompt_hash=PROMPT.prompt_hash,
            model_policy_version=POLICY.version,
        )
        session.add(q.JudgeRow(sampling_id=row.id, spec=spec.model_dump(mode="json")))
    return row


async def record_feedback(
    session: AsyncSession, feedback: Feedback, policy: JudgeSamplingPolicy
) -> q.FeedbackRow:
    invocation = await resolve_subject(session, feedback.subject)
    resume = await session.get(e.ResumeVariantRevision, feedback.subject.subject_id)
    artifact = await session.get(e.PreparationArtifact, feedback.subject.subject_id)
    from career_agent.profile_area.entities import ResumeWorkspace

    workspace = await session.get(ResumeWorkspace, feedback.subject.subject_id)
    job_id = resume.job_revision_id if resume else artifact.job_revision_id if artifact else None
    application = None
    if job_id:
        jd = await require(session, e.JobRevision, job_id)
        application = await session.scalar(
            select(e.Application).where(e.Application.job_id == jd.job_id)
        )
    if feedback.application_id and (
        application is None or feedback.application_id != application.id
    ):
        raise DomainError("context_revision_mismatch", 422)
    assert feedback.subject.accepted_model_call_id is not None
    call = await require(session, e.ModelCall, feedback.subject.accepted_model_call_id)
    step = await require(session, e.AgentStep, call.step_id)
    feedback = feedback.model_copy(
        update={
            "application_id": application.id if application else None,
            "artifact_type": "resume_revision"
            if resume
            else artifact.data.get("kind")
            if artifact
            else "resume_workspace"
            if workspace
            else "artifact",
            "generation_provenance": {
                "run_id": str(step.run_id),
                "step_id": str(step.id),
                "model_call_id": str(call.id),
                "invocation_id": str(invocation.id),
                "generation_subject_id": invocation.data.get("output_ref"),
            },
        }
    )
    row = q.FeedbackRow(
        subject_id=feedback.subject.subject_id, data=feedback.model_dump(mode="json")
    )
    session.add(row)
    await session.flush()
    if feedback.vote == "thumbs_down":
        await enqueue(session, feedback.subject, policy, "forced_user_feedback")
        payload = payload_from_invocation(feedback.subject, invocation)
        await capture(session, payload, "user_thumbs_down", row.id)
    return row


def payload_from_invocation(subject: Subject, invocation: q.InvocationRow) -> CapturePayload:
    data = invocation.data
    return CapturePayload(
        subject=subject,
        source_snapshot=data["provenance"].get("source_snapshot", {}),
        model_input=data["input_snapshot"],
        output=data.get("output") or {},
        external_observations=data["provenance"].get("external_observations", {}),
        provenance={
            **data["provenance"],
            "operation_id": data["operation_id"],
            "logical_operation_id": data.get("logical_operation_id"),
        },
    )


async def annotation_queue(
    session: AsyncSession, subject: Subject, population: str
) -> q.AnnotationQueueRow:
    await resolve_subject(session, subject)
    if population not in {"random", "targeted"}:
        raise DomainError("invalid_calibration_population")
    row = q.AnnotationQueueRow(
        subject_id=subject.subject_id, population=population, rubric_version="quality-rubric-v1"
    )
    session.add(row)
    await session.flush()
    return row


async def blind_view(session: AsyncSession, id: UUID) -> dict[str, Any]:
    row = await require(session, q.AnnotationQueueRow, id)
    invocation = await session.scalar(
        select(q.InvocationRow).where(
            q.InvocationRow.data["output_ref"].astext == str(row.subject_id)
        )
    )
    if invocation is None:
        raise DomainError("subject_provenance_unavailable")
    return {
        "id": row.id,
        "subject_id": row.subject_id,
        "population": row.population,
        "rubric_version": row.rubric_version,
        "input": invocation.data["input_snapshot"],
        "output": invocation.data["output"],
        "blind": True,
    }


async def annotate(
    session: AsyncSession, queue_id: UUID, annotation: Annotation
) -> q.AnnotationRow:
    queue = await require(session, q.AnnotationQueueRow, queue_id, lock=True)
    if (
        queue.subject_id != annotation.subject.subject_id
        or queue.population != annotation.population
        or queue.rubric_version != annotation.rubric_version
    ):
        raise DomainError("annotation_context_mismatch")
    await resolve_subject(session, annotation.subject)
    if annotation.supersedes_annotation_id:
        previous = await require(session, q.AnnotationRow, annotation.supersedes_annotation_id)
        if previous.subject_id != queue.subject_id:
            raise DomainError("annotation_context_mismatch")
    row = q.AnnotationRow(subject_id=queue.subject_id, data=annotation.model_dump(mode="json"))
    session.add(row)
    queue.status = "annotated"
    await session.flush()
    return row


async def request_explicit_judge(session: AsyncSession, subject: Subject) -> q.JudgeRow:
    """Explicit evaluation is not recursive automatic sampling."""
    from career_agent.evaluation.contracts import JudgeSamplingPolicy

    if subject.task_type == "quality_judgement":
        raise DomainError("recursive_judge_forbidden")
    await resolve_subject(session, subject)
    decision = decide(
        subject.model_copy(update={"origin": "business"}),
        JudgeSamplingPolicy(version="explicit-judge-v1"),
        "forced_manual",
    )
    assert decision is not None
    decision.subject = subject
    await require(session, e.ModelCall, subject.accepted_model_call_id, lock=True)  # type: ignore[arg-type]
    sampling = await session.scalar(
        select(q.SamplingRow).where(q.SamplingRow.decision_key == decision.decision_key)
    )
    if sampling is not None:
        existing = await session.scalar(
            select(q.JudgeRow).where(q.JudgeRow.sampling_id == sampling.id)
        )
        if existing is not None:
            return existing
    else:
        sampling = q.SamplingRow(
            subject_id=subject.subject_id,
            decision_key=decision.decision_key,
            data=decision.model_dump(mode="json"),
        )
        session.add(sampling)
        await session.flush()
    spec = JudgeSpec(
        target=subject.task_type,
        prompt_version=PROMPT.prompt_version,
        prompt_hash=PROMPT.prompt_hash,
        model_policy_version=POLICY.version,
    )
    row = q.JudgeRow(sampling_id=sampling.id, spec=spec.model_dump(mode="json"))
    session.add(row)
    await session.flush()
    return row
