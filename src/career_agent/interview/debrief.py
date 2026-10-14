"""Standalone snapshot analysis with bounded provider concurrency and durable business events."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import check_revision, require
from career_agent.config import Settings
from career_agent.domain.rules import DomainError, RunStatus
from career_agent.domain.schemas import InterviewEntry, InterviewNoteData
from career_agent.infrastructure import entities as e
from career_agent.interview.calls import InterviewCalls
from career_agent.interview.context import clean, digest, freeze
from career_agent.interview.contracts import (
    DebriefCreate,
    EvaluationData,
    EventData,
    FrozenContext,
    OverallEvaluation,
    QuestionGroupEvaluation,
    SourceSnapshot,
)
from career_agent.interview.mock import frozen_policy, turns
from career_agent.interview.policy import CallPolicy, InterviewPolicy
from career_agent.interview.validation import groups, validate_evaluation
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.gateway import ModelGateway


def inputs_for(snapshot: SourceSnapshot, group_ref: UUID | None) -> dict[str, Any]:
    context = snapshot.context.data if snapshot.context else {}
    if group_ref is None:
        return {
            "stable_context": context,
            "source": clean(snapshot.model_dump(mode="json", exclude={"context"})),
        }
    group = next(g for g in groups(snapshot) if g["group_ref"] == str(group_ref))
    return {"stable_context": context, "group": clean(group)}


def call_policy(policy: InterviewPolicy, source: SourceSnapshot, kind: str) -> CallPolicy:
    if source.source_kind == "actual":
        return policy.actual_group if kind == "group" else policy.actual_overall
    return policy.mock_group if kind == "group" else policy.mock_overall


def task_type(kind: str) -> str:
    return "interview_group_debrief" if kind == "group" else "interview_overall_debrief"


def presentation(snapshot: SourceSnapshot, artifact: e.DebriefArtifact) -> dict[str, Any]:
    """IDs remain machine refs in API data, never presentation labels or user prose."""
    all_groups = groups(snapshot)
    anchors = {}
    for group in all_groups:
        for item in group["entries"]:
            anchors[item["entry_id"]] = {
                "question_number": group["group_index"],
                "label": "来自追问" if item["kind"] == "follow_up" else "主问题",
                "preview": item["question"][:80],
            }
    out: dict[str, Any] = {
        "section": "overall" if artifact.kind == "overall" else "questions",
        "display_order": artifact.display_order,
        "group_index": artifact.group_index,
    }
    if artifact.group_ref:
        group = next(g for g in all_groups if g["group_ref"] == str(artifact.group_ref))
        out["qa"] = [
            {
                "question": i["question"],
                "answer": i["answer"],
                "label": "追问" if i["kind"] == "follow_up" else "主问题",
                "answer_missing": i["answer"] is None,
            }
            for i in group["entries"]
        ]
    if artifact.data:
        data = artifact.data[artifact.kind]
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, list):
                result[key] = [
                    {
                        "content": finding["content"],
                        "evidence": [anchors[str(ref)] for ref in finding["evidence_refs"]],
                    }
                    for finding in value
                ]
            elif key == "example_answer" and value:
                result[key] = {"content": value["content"]}
        out["evaluation"] = result
    return out


class DebriefService:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], settings: Settings, gateway: ModelGateway
    ) -> None:
        self.sessions, self.settings, self.gateway = sessions, settings, gateway
        self.calls = InterviewCalls(sessions, gateway)

    async def create(self, request: DebriefCreate) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            if request.source_kind == "actual":
                interview = await require(
                    session, e.InterviewSession, request.interview_id, lock=True
                )
                check_revision(interview.content_revision, request.expected_source_revision)
                context = (
                    await freeze(session, self.settings, self.gateway, request.context)
                    if request.context
                    else None
                )
                if context:
                    application = await require(session, e.Application, interview.application_id)
                    if context.job_id != application.job_id:
                        raise DomainError("context_revision_mismatch")
                snapshot = SourceSnapshot(
                    source_kind="actual",
                    interview_id=interview.id,
                    content_revision=interview.content_revision,
                    entries=[InterviewEntry.model_validate(x) for x in interview.entries],
                    notes=[InterviewNoteData.model_validate(x) for x in interview.notes],
                    context=context,
                )
            else:
                mock = await require(
                    session, e.MockInterviewSession, request.interview_id, lock=True
                )
                check_revision(mock.revision, request.expected_source_revision)
                if mock.status != "completed" or mock.generation_active:
                    raise DomainError("mock_not_completed")
                if (
                    request.context
                    and request.context != FrozenContext.model_validate(mock.context).binding
                ):
                    raise DomainError("context_revision_mismatch")
                history = await turns(session, mock.id)
                snapshot = SourceSnapshot(
                    source_kind="mock",
                    interview_id=mock.id,
                    content_revision=mock.revision,
                    notes=[],
                    context=FrozenContext.model_validate(mock.context),
                    completion_type=mock.completion_type,
                    entries=[
                        InterviewEntry(
                            entry_id=t.id,
                            order=t.sequence,
                            kind=t.data["kind"],
                            question=t.data["question"],
                            answer=t.answer,
                            primary_entry_id=t.data["primary_entry_id"],
                        )
                        for t in history
                    ],
                )
            grouped = groups(snapshot)
            selected = (
                grouped
                if request.question_analysis == "all"
                else [g for g in grouped if g["group_ref"] == str(request.primary_entry_id)]
                if request.question_analysis == "single"
                else []
            )
            if request.question_analysis == "single" and len(selected) != 1:
                raise DomainError("invalid_primary_reference", 422)
            if not selected and not request.overall_analysis:
                raise DomainError("no_question_groups", 422)
            policy = frozen_policy(self.settings)
            plan: list[tuple[str, UUID | None, int | None, int]] = [
                ("group", UUID(g["group_ref"]), g["group_index"], g["group_index"])
                for g in selected
            ]
            if request.overall_analysis:
                plan.append(("overall", None, None, len(grouped) + 1))
            for kind, ref, _, _ in plan:
                self.calls.preflight(
                    task_type(kind),
                    request.mode,
                    inputs_for(snapshot, ref),
                    call_policy(policy, snapshot, kind),
                )
            limits = (
                policy.actual_debrief if snapshot.source_kind == "actual" else policy.mock_debrief
            ).model_copy(deep=True)
            # Calls include transport/schema attempts; operator limits remain authoritative.
            limits.max_model_calls = min(
                limits.max_model_calls,
                len(plan) * (1 + policy.transport_retries + policy.schema_repairs),
            )
            run = e.AgentRun(
                workflow="interview_debrief",
                workflow_version="interview-loop-v1",
                budget={
                    "token_limit": limits.max_input_tokens + limits.max_output_tokens,
                    "cost_limit": str(limits.max_estimated_cost),
                },
                status=RunStatus.PENDING,
                requested_outputs=[task_type(k) for k in sorted({p[0] for p in plan})],
            )
            session.add(run)
            await session.flush()
            data = snapshot.model_dump(mode="json")
            row = e.DebriefRun(
                run_id=run.id,
                mode=request.mode,
                snapshot=data,
                source_hash=digest(data),
                limits=limits.model_dump(mode="json"),
                execution_policy=policy.model_dump(mode="json"),
            )
            session.add(row)
            await session.flush()
            for kind, ref, index, order in plan:
                session.add(
                    e.DebriefArtifact(
                        debrief_id=row.id,
                        kind=kind,
                        group_ref=ref,
                        group_index=index,
                        display_order=order,
                    )
                )
            id = row.id
        return await self.view(id)

    async def view(self, id: UUID) -> dict[str, Any]:
        async with self.sessions() as session:
            row = await require(session, e.DebriefRun, id)
            source = SourceSnapshot.model_validate(row.snapshot)
            artifacts = list(
                await session.scalars(
                    select(e.DebriefArtifact)
                    .where(e.DebriefArtifact.debrief_id == id)
                    .order_by(e.DebriefArtifact.display_order)
                )
            )
            return {
                "id": row.id,
                "run_id": row.run_id,
                "status": row.status,
                "source_hash": row.source_hash,
                "snapshot": row.snapshot,
                "usage": row.usage,
                "event_sequence": row.event_sequence,
                "artifacts": [
                    {
                        "id": a.id,
                        "kind": a.kind,
                        "group_ref": a.group_ref,
                        "group_index": a.group_index,
                        "status": a.status,
                        "error_code": a.error_code,
                        "attempts": a.attempts,
                        "data": a.data,
                        "presentation": presentation(source, a),
                    }
                    for a in artifacts
                ],
            }

    async def events(self, id: UUID, after: int = 0) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            await require(session, e.DebriefRun, id)
            return [
                {"sequence": event.sequence, **event.data}
                for event in await session.scalars(
                    select(e.DebriefEvent)
                    .where(e.DebriefEvent.debrief_id == id, e.DebriefEvent.sequence > after)
                    .order_by(e.DebriefEvent.sequence)
                    .limit(1000)
                )
            ]

    async def event(
        self, session: AsyncSession, run: e.DebriefRun, data: EventData
    ) -> dict[str, Any]:
        run.event_sequence += 1
        session.add(
            e.DebriefEvent(
                debrief_id=run.id, sequence=run.event_sequence, data=data.model_dump(mode="json")
            )
        )
        return {"sequence": run.event_sequence, **data.model_dump(mode="json")}

    async def artifact_event(
        self,
        id: UUID,
        artifact_id: UUID,
        status: str,
        *,
        result: EvaluationData | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            run = await require(session, e.DebriefRun, id, lock=True)
            artifact = await require(session, e.DebriefArtifact, artifact_id)
            artifact.status = {
                "started": "running",
                "retrying": "retrying",
                "completed": "completed",
                "failed": "failed",
            }[status]
            if status == "started":
                artifact.attempts += 1
            artifact.error_code = reason
            if result:
                artifact.data = result.model_dump(mode="json")
            message = (
                "该题分析暂时失败，系统正在自动重试。"
                if status == "retrying"
                else "本次分析失败，自动重试已达上限或该错误不可重试，可稍后单独重试。"
                if status == "failed"
                else None
            )
            event = EventData.model_validate(
                {
                    "event": f"{artifact.kind}_{status}",
                    "artifact_id": artifact.id,
                    "group_index": artifact.group_index,
                    "display_section": "overall" if artifact.kind == "overall" else "questions",
                    "display_order": artifact.display_order,
                    "reason_code": reason,
                    "message": message,
                }
            )
            value = await self.event(session, run, event)
        # This function returns only after both artifact and event commit.
        return value

    async def process(
        self, id: UUID, artifact_id: UUID, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        async with self.sessions() as session:
            run = await require(session, e.DebriefRun, id)
            artifact = await require(session, e.DebriefArtifact, artifact_id)
            source = SourceSnapshot.model_validate(run.snapshot)
            if digest(run.snapshot) != run.source_hash:
                await queue.put(
                    await self.artifact_event(
                        id, artifact_id, "failed", reason="snapshot_integrity_failed"
                    )
                )
                return
            policy = InterviewPolicy.model_validate(run.execution_policy)
            kind, ref = artifact.kind, artifact.group_ref
        transport = repairs = 0
        last: str | None = None
        while True:
            await queue.put(await self.artifact_event(id, artifact_id, "started"))
            inputs = inputs_for(source, ref)
            if repairs:
                inputs["repair_reason"] = "schema_invalid"
            try:
                result = await self.calls.generate(
                    "debrief",
                    id,
                    task_type(kind),
                    inputs,
                    call_policy(policy, source, kind),
                    lambda value: validate_evaluation(value, source, ref),
                    attempt=1 + transport + repairs,
                    retry_reason=last if transport else None,
                    repair_reason="schema_invalid" if repairs else None,
                )
            except ModelGatewayError as exc:
                schema = exc.code in {"structured_output_invalid", "output_validation_failed"}
                if schema and repairs < policy.schema_repairs:
                    repairs += 1
                elif exc.retryable and transport < policy.transport_retries:
                    transport += 1
                else:
                    await queue.put(
                        await self.artifact_event(id, artifact_id, "failed", reason=exc.code)
                    )
                    return
                last = exc.code
                await queue.put(
                    await self.artifact_event(id, artifact_id, "retrying", reason=exc.code)
                )
                continue
            data = EvaluationData(
                group=result if isinstance(result, QuestionGroupEvaluation) else None,
                overall=result if isinstance(result, OverallEvaluation) else None,
            )
            await queue.put(await self.artifact_event(id, artifact_id, "completed", result=data))
            return

    async def execute(self, id: UUID) -> AsyncGenerator[dict[str, Any], None]:
        async with self.sessions.begin() as session:
            run = await require(session, e.DebriefRun, id, lock=True)
            if run.status != "ready":
                raise DomainError("debrief_already_started")
            run.status = "running"
            parent = await require(session, e.AgentRun, run.run_id)
            parent.status = RunStatus.RUNNING
            policy = InterviewPolicy.model_validate(run.execution_policy)
            ids = list(
                await session.scalars(
                    select(e.DebriefArtifact.id)
                    .where(e.DebriefArtifact.debrief_id == id)
                    .order_by(e.DebriefArtifact.display_order.desc())
                )
            )
        # A fixed worker count, not one asyncio task per question. Overall competes in the same
        # pool and starts first; output display order remains independent of execution order.
        work: asyncio.Queue[UUID] = asyncio.Queue()
        for artifact_id in ids:
            work.put_nowait(artifact_id)
        emitted: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def worker() -> None:
            while not work.empty():
                artifact_id = work.get_nowait()
                try:
                    await self.process(id, artifact_id, emitted)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await emitted.put(
                        await self.artifact_event(
                            id, artifact_id, "failed", reason="interview_internal_error"
                        )
                    )
                finally:
                    work.task_done()

        # Signal worker termination independently from business events. A persistence failure
        # must not leave the request waiting forever for a completion event that cannot exist.
        async def supervised_worker() -> None:
            try:
                await worker()
            finally:
                await emitted.put({"worker_finished": True})

        workers = [
            asyncio.create_task(supervised_worker())
            for _ in range(min(policy.concurrency, len(ids)))
        ]
        completed = 0
        finished_workers = 0
        try:
            while completed < len(ids):
                event = await emitted.get()
                if event.get("worker_finished"):
                    finished_workers += 1
                    if finished_workers == len(workers) and completed < len(ids):
                        await asyncio.gather(*workers, return_exceptions=True)
                        yield await self.finish(id, interrupted=True)
                        return
                    continue
                yield event
                if event["event"] in {
                    "group_completed",
                    "group_failed",
                    "overall_completed",
                    "overall_failed",
                }:
                    completed += 1
            await asyncio.gather(*workers)
            yield await self.finish(id)
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            # Disconnect stops new calls; completed artifacts survive. Unknown in-flight usage
            # remains reserved. No hidden background worker or automatic replay.
            await self.finish(id, interrupted=True)

    async def finish(self, id: UUID, *, interrupted: bool = False) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            run = await require(session, e.DebriefRun, id, lock=True)
            if run.status in {"completed", "partial", "failed"}:
                return {}
            artifacts = list(
                await session.scalars(
                    select(e.DebriefArtifact).where(e.DebriefArtifact.debrief_id == id)
                )
            )
            for artifact in artifacts:
                if interrupted and artifact.status not in {"completed", "failed"}:
                    artifact.status, artifact.error_code = "failed", "execution_cancelled"
                    await self.event(
                        session,
                        run,
                        EventData.model_validate(
                            {
                                "event": f"{artifact.kind}_failed",
                                "artifact_id": artifact.id,
                                "group_index": artifact.group_index,
                                "display_section": "overall"
                                if artifact.kind == "overall"
                                else "questions",
                                "display_order": artifact.display_order,
                                "reason_code": "execution_cancelled",
                            }
                        ),
                    )
            successes = sum(a.status == "completed" for a in artifacts)
            run.status = (
                "completed" if successes == len(artifacts) else "partial" if successes else "failed"
            )
            parent = await require(session, e.AgentRun, run.run_id)
            parent.status = {
                "completed": RunStatus.COMPLETED,
                "partial": RunStatus.PARTIAL,
                "failed": RunStatus.FAILED,
            }[run.status]
            parent.finished_at = e.utcnow()
            return await self.event(
                session,
                run,
                EventData.model_validate(
                    {
                        "event": f"run_{run.status}",
                        "display_section": "run",
                        "display_order": len(artifacts) + 1,
                    }
                ),
            )
