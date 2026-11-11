"""Visibility removal with frozen-source checks; generation/audit data is never deleted."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.evaluation.entities import InvocationRow
from career_agent.infrastructure import entities as e
from career_agent.product.entities import (
    MaterialSubmission,
    ProductDraft,
    ProductOperation,
    ResultRemoval,
)


def contains(value: Any, refs: set[str]) -> bool:
    if isinstance(value, dict):
        return any(contains(v, refs) for v in value.values())
    if isinstance(value, list):
        return any(contains(v, refs) for v in value)
    return isinstance(value, str) and value in refs


async def captured_input_use(
    session: AsyncSession, package: e.PreparationArtifact, field: str
) -> bool | None:
    """Inspect actual task inputs, following exact reused outputs; absence is not evidence."""
    runs = {package.run_id}
    state = package.data.get("output", {})
    outcomes = (state.get("outcome") or {}).get("targets", {})
    for outcome in outcomes.values():
        if outcome.get("status") != "completed" or not outcome.get("artifact_id"):
            continue
        source = await session.get(e.PreparationArtifact, UUID(outcome["artifact_id"]))
        if source is None:
            return None
        runs.add(source.run_id)
    calls = list(
        await session.scalars(
            select(e.ModelCall)
            .join(e.AgentStep, e.AgentStep.id == e.ModelCall.step_id)
            .where(e.AgentStep.run_id.in_(runs))
        )
    )
    if not calls:
        return None
    captures = list(
        await session.scalars(
            select(InvocationRow).where(
                InvocationRow.model_call_id.in_([call.id for call in calls])
            )
        )
    )
    by_call = {row.model_call_id: row for row in captures}
    unknown = False
    for call in calls:
        captured = by_call.get(call.id)
        context = captured.data.get("input_snapshot", {}).get("context") if captured else None
        if not isinstance(context, dict):
            unknown = True
        elif context.get(field) is not None:
            return True
    return None if unknown else False


def purpose(label: str, row: Any) -> str:
    from zoneinfo import ZoneInfo

    saved = row.created_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    return f"{label}（{saved}）"


async def consumers(
    session: AsyncSession, refs: set[str], own_runs: set[UUID], own_ids: set[UUID]
) -> list[str]:
    uses: set[str] = set()
    uncertain = False
    for row in await session.scalars(select(e.PreparationArtifact)):
        if row.id in own_ids or (row.run_id in own_runs and row.data.get("kind") == "package"):
            continue
        data = row.data
        if data.get("kind") == "package":
            state = dict(data.get("output", {}))
            report = state.get("research_report_id")
            if report in refs:
                consumed = await captured_input_use(session, row, "research")
                if consumed is not True:
                    state.pop("research_report_id", None)
                    uncertain = uncertain or consumed is None
            requested = state.get("requested_outputs", [])
            for task, output_key in (
                ("fit_analysis", "fit_analysis_id"),
                ("interview_preparation", "interview_prep_id"),
            ):
                if requested == [task] and state.get(output_key) in refs:
                    # Publishing the same result is not a downstream input consumer.
                    state.pop(output_key, None)
                    state.pop("outcome", None)
            data = {**data, "output": state}
        if contains(data, refs):
            kind = row.data.get("output", {}).get("workflow") or row.data.get("kind")
            names = {
                "prepare_application": "投递材料",
                "prepare_interview": "面试准备",
                "target": "生成结果",
            }
            requested = row.data.get("output", {}).get("requested_outputs", [])
            label = names.get(str(kind), "准备记录")
            if requested == ["greeting_generation"]:
                label = "招呼语"
            elif requested == ["fit_analysis"]:
                label = "岗位匹配"
            elif requested == ["resume_tailoring"]:
                label = "简历优化"
            uses.add(purpose(label, row))
    for draft in await session.scalars(select(ProductDraft)):
        if draft.run_id not in own_runs and (
            contains(draft.request, refs) or contains(draft.context, refs)
        ):
            uses.add(purpose("调整任务及其历史来源", draft))
    for operation in await session.scalars(select(ProductOperation)):
        if operation.run_id not in own_runs and (
            contains(operation.payload, refs) or str(operation.package_id) in refs
        ):
            uses.add(purpose("生成任务", operation))
    for mock in await session.scalars(select(e.MockInterviewSession)):
        if contains(mock.context, refs):
            uses.add(purpose("模拟面试", mock))
    for debrief in await session.scalars(select(e.DebriefRun)):
        if contains(debrief.snapshot, refs):
            uses.add(purpose("面试复盘", debrief))
    for checkpoint in await session.scalars(select(e.AgentCheckpoint)):
        if checkpoint.run_id not in own_runs and contains(checkpoint.state, refs):
            uses.add(purpose("已冻结的任务上下文", checkpoint))
    for invocation in await session.scalars(select(InvocationRow)):
        if invocation.data.get("parent_run_id") not in {str(run) for run in own_runs} and contains(
            invocation.data.get("input_snapshot", {}), refs
        ):
            uses.add(purpose("历史生成来源", invocation))
    for submission in await session.scalars(select(MaterialSubmission)):
        if str(submission.package_id) in refs or str(submission.greeting_id) in refs:
            uses.add(purpose(f"第 {submission.display_number} 次投递", submission))
    for resume in await session.scalars(select(e.ResumeVariantRevision)):
        if contains(resume.input_snapshot, refs) or contains(resume.library_state, refs):
            uses.add(purpose("简历来源", resume))
    if uncertain and not uses:
        raise DomainError("result_references_unavailable")
    return sorted(uses)


async def remove_target(
    session: AsyncSession, application_id: UUID, id: UUID, request_id: UUID
) -> dict[str, Any]:
    from career_agent.infrastructure.claims import claim
    from career_agent.preparation.contracts import PrivateResult, TargetArtifact
    from career_agent.product.results import exact

    await require(session, e.Application, application_id, lock=True)
    row = await require(session, e.PreparationArtifact, id, lock=True)
    item = await exact(session, application_id, id)
    operation = await session.scalar(
        select(ProductOperation).where(ProductOperation.run_id == row.run_id)
    )
    draft = await session.scalar(select(ProductDraft).where(ProductDraft.run_id == row.run_id))
    owner = (
        operation.payload.get("application_id")
        or (operation.payload.get("application_binding") or {}).get("application_id")
        if operation
        else None
    ) or (draft.request.get("application_id") if draft else None)
    if owner is None and operation is not None:
        from career_agent.interview.ownership import legacy_owner

        request = operation.payload.get("request", {})
        # Verify the generation request itself agrees with the immutable artifact.
        if request.get("job_revision_id") == str(row.job_revision_id) and request.get(
            "profile_id"
        ) == str(row.profile_id):
            resolved = await legacy_owner(session, request, created_at=row.created_at)
            owner = str(resolved) if resolved else None
    if owner is None:
        raise DomainError("historical_reference_unavailable")
    if owner != str(application_id):
        raise DomainError("context_revision_mismatch")
    if item.result.kind not in {"fit_analysis", "interview_preparation"}:
        raise DomainError("context_revision_mismatch")
    old = await session.scalar(select(ResultRemoval).where(ResultRemoval.target_id == id))
    if old:
        return {"deleted": True, "used_by": []}
    target = PrivateResult.model_validate(row.data).output
    if not isinstance(target, TargetArtifact) or target.result_id is None:
        raise DomainError("historical_reference_unavailable")
    # Lock the underlying source as well as its Product wrapper: consumers may use either ID.
    await require(session, e.PreparationArtifact, target.result_id, lock=True)
    own_ids = {row.id, target.result_id}
    refs = {str(x) for x in own_ids}
    packages = list(
        await session.scalars(
            select(e.PreparationArtifact).where(
                e.PreparationArtifact.run_id == row.run_id,
                e.PreparationArtifact.data["kind"].astext == "package",
            )
        )
    )
    refs.update(str(package.id) for package in packages)
    used = await consumers(session, refs, {row.run_id}, own_ids)
    # A multi-output package can contain independent results. Preserve an actual
    # model input or explicit gate decision, not mere co-publication.
    unresolved = False
    if target.target == "fit_analysis":
        for package in packages:
            state = package.data.get("output", {})
            if len(state.get("requested_outputs", [])) <= 1:
                continue
            consumed = await captured_input_use(session, package, "fit")
            if consumed is True or (state.get("outcome") or {}).get("gate_policy_version"):
                used.append(purpose("使用匹配结果的投递材料", package))
            elif consumed is None:
                unresolved = True
    if unresolved and not used:
        raise DomainError("result_references_unavailable")
    if used:
        return {"deleted": False, "used_by": used}
    await claim(session, "result-removal:" + str(request_id))
    if await session.scalar(select(ResultRemoval.id).where(ResultRemoval.request_id == request_id)):
        raise DomainError("idempotency_conflict")
    session.add(ResultRemoval(application_id=application_id, target_id=id, request_id=request_id))
    await session.flush()
    return {"deleted": True, "used_by": []}


async def remove_research(session: AsyncSession, company_id: UUID, id: UUID) -> dict[str, Any]:
    await require(session, e.Company, company_id, lock=True)
    row = await require(session, e.CompanyResearch, id, lock=True)
    if row.company_id != company_id:
        raise DomainError("not_found", 404)
    if row.deleted_at is not None:
        return {"deleted": True, "used_by": []}
    own_runs = set(
        await session.scalars(
            select(ProductOperation.run_id).where(
                ProductOperation.research_report_id == id,
                ProductOperation.kind == "company_research",
            )
        )
    )
    used = await consumers(session, {str(id)}, own_runs, set())
    if used:
        return {"deleted": False, "used_by": used}
    row.deleted_at = e.utcnow()
    await session.flush()
    return {"deleted": True, "used_by": []}


async def require_source_visible(session: AsyncSession, id: UUID) -> None:
    wrappers = list(
        await session.scalars(
            select(e.PreparationArtifact.id).where(
                e.PreparationArtifact.data["kind"].astext == "target",
                e.PreparationArtifact.data["output"]["result_id"].astext == str(id),
            )
        )
    )
    if await session.scalar(
        select(ResultRemoval.id).where(ResultRemoval.target_id.in_([id, *wrappers]))
    ):
        raise DomainError("result_removed")
