"""Text mock interview: explicit durable answers, bounded single-question generation."""

from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import check_revision, require
from career_agent.config import Settings
from career_agent.domain.rules import DomainError, RunStatus
from career_agent.infrastructure import entities as e
from career_agent.interview.calls import InterviewCalls, validate_accepted_call
from career_agent.interview.context import clean, digest, freeze
from career_agent.interview.contracts import (
    AnswerSubmit,
    Continuation,
    FrozenContext,
    MockCreate,
    MockPolicy,
    TurnOutput,
)
from career_agent.interview.policy import InterviewPolicy
from career_agent.interview.validation import validate_turn
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.gateway import ModelGateway


def frozen_policy(settings: Settings) -> InterviewPolicy:
    return settings.interview_policy.model_copy(
        deep=True,
        update={
            "transport_retries": settings.model_retry_limit,
            "schema_repairs": settings.schema_repair_limit,
        },
    )


async def turns(session: AsyncSession, id: UUID) -> list[e.MockInterviewTurn]:
    return list(
        await session.scalars(
            select(e.MockInterviewTurn)
            .where(e.MockInterviewTurn.session_id == id)
            .order_by(e.MockInterviewTurn.sequence)
        )
    )


def next_kind(
    row: e.MockInterviewSession, history: list[e.MockInterviewTurn]
) -> tuple[str, UUID | None]:
    policy = MockPolicy.model_validate(row.policy)
    assert policy.primary_target is not None and policy.followup_max is not None
    # Fixed schedule: optional follow-up allowance is spent on earliest answered primaries.
    # No model can decide to stop or turn a follow-up into an extra primary.
    if (
        history
        and history[-1].data["kind"] == "primary"
        and history[-1].answer is not None
        and row.followup_count < policy.followup_max
    ):
        return "follow_up", history[-1].id
    if row.primary_question_count < policy.primary_target:
        return "primary", None
    return "finish", None


def generation_inputs(
    row: e.MockInterviewSession, history: list[e.MockInterviewTurn]
) -> dict[str, Any]:
    kind, parent = next_kind(row, history)
    last = history[-1] if history else None
    return {
        "stable_context": FrozenContext.model_validate(row.context).data,
        "question_history": [
            {
                "entry_id": str(t.id),
                "kind": t.data["kind"],
                "question": t.data["question"],
                "topic": t.data["topic"],
                "primary_entry_id": t.data["primary_entry_id"],
            }
            for t in history
        ],
        "current_question": {"entry_id": str(last.id), "question": last.data["question"]}
        if last
        else None,
        "current_answer": clean(last.answer) if last else None,
        "policy": {
            "next_kind": kind,
            "parent": str(parent) if parent else None,
            "focus": row.focus,
            "primary_question_count": row.primary_question_count,
            "followup_count": row.followup_count,
            "interviewer_turn_count": row.interviewer_turn_count,
            **row.policy,
        },
    }


class MockService:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], settings: Settings, gateway: ModelGateway
    ) -> None:
        self.sessions, self.settings, self.gateway = sessions, settings, gateway
        self.calls = InterviewCalls(sessions, gateway)

    async def create(self, request: MockCreate) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            context = await freeze(session, self.settings, self.gateway, request.context)
            policy = frozen_policy(self.settings)
            limits = policy.mock_session.model_copy(deep=True)
            assert (
                request.policy.primary_target is not None
                and request.policy.followup_max is not None
            )
            limits.max_model_calls = request.policy.primary_target + request.policy.followup_max
            run = e.AgentRun(
                workflow="mock_interview",
                workflow_version="interview-loop-v1",
                budget={
                    "token_limit": limits.max_input_tokens + limits.max_output_tokens,
                    "cost_limit": str(limits.max_estimated_cost),
                },
                status=RunStatus.WAITING_INPUT,
                requested_outputs=["mock_interview_turn_generation"],
            )
            session.add(run)
            await session.flush()
            row = e.MockInterviewSession(
                run_id=run.id,
                mode=request.mode,
                focus=request.focus,
                policy=request.policy.model_dump(mode="json"),
                context=context.model_dump(mode="json"),
                execution_policy=policy.model_dump(mode="json"),
                limits=limits.model_dump(mode="json"),
            )
            session.add(row)
            await session.flush()
            id = row.id
        # Creation persists ready state; an explicit generation request starts the first question.
        return await self.view(id)

    async def view(self, id: UUID) -> dict[str, Any]:
        async with self.sessions() as session:
            row = await require(session, e.MockInterviewSession, id)
            history = await turns(session, id)
            return {
                "id": id,
                "run_id": row.run_id,
                "revision": row.revision,
                "status": row.status,
                "completion_type": row.completion_type,
                "stop_reason": row.stop_reason,
                "generation_active": row.generation_active,
                "pending_question_id": row.pending_question_id,
                "primary_question_count": row.primary_question_count,
                "followup_count": row.followup_count,
                "interviewer_turn_count": row.interviewer_turn_count,
                "policy": row.policy,
                "context": row.context,
                "usage": row.usage,
                "turns": [
                    {
                        "id": t.id,
                        "sequence": t.sequence,
                        "logical_operation_id": t.logical_operation_id,
                        "accepted_model_call_id": t.accepted_model_call_id,
                        "question": t.data,
                        "answer": t.answer,
                        "answered_at": t.answered_at,
                    }
                    for t in history
                ],
            }

    async def continue_(
        self, id: UUID, request: Continuation, operation: Literal["answer", "generate", "end"]
    ) -> dict[str, Any]:
        request_hash = digest({"operation": operation, **request.model_dump(mode="json")})
        generate = False
        async with self.sessions.begin() as session:
            row = await require(session, e.MockInterviewSession, id, lock=True)
            receipt = await session.scalar(
                select(e.MockRequestReceipt).where(
                    e.MockRequestReceipt.session_id == id,
                    e.MockRequestReceipt.request_id == request.request_id,
                )
            )
            if receipt:
                if receipt.request_hash != request_hash:
                    raise DomainError("idempotency_conflict")
            else:
                check_revision(row.revision, request.expected_revision)
                if row.generation_active:
                    raise DomainError("generation_in_progress")
                if row.status == "completed":
                    raise DomainError("mock_completed")
                history = await turns(session, id)
                if operation == "answer":
                    if (
                        not isinstance(request, AnswerSubmit)
                        or row.status != "waiting_answer"
                        or row.pending_question_id != request.pending_question_id
                    ):
                        raise DomainError("pending_question_mismatch")
                    turn = await require(session, e.MockInterviewTurn, request.pending_question_id)
                    if turn.session_id != row.id or turn.answer is not None:
                        raise DomainError("answer_immutable")
                    # Validate the candidate next context before accepting the answer.
                    turn.answer = request.answer
                    turn.answered_at = e.utcnow()
                    row.status, row.pending_question_id = "ready_to_generate", None
                elif operation == "generate" and row.status != "ready_to_generate":
                    raise DomainError("answer_required")
                if operation == "end":
                    row.status, row.completion_type = "completed", "user_ended_early"
                    row.pending_question_id = None
                elif next_kind(row, history)[0] == "finish":
                    row.status, row.completion_type = "completed", "target_reached"
                else:
                    policy = InterviewPolicy.model_validate(row.execution_policy)
                    self.calls.preflight(
                        "mock_interview_turn_generation",
                        row.mode,
                        generation_inputs(row, history),
                        policy.mock_generation,
                    )
                    row.generation_operation_id = row.generation_operation_id or uuid4()
                    row.generation_active = True
                    generate = True
                row.revision += 1
                row.stop_reason = None
                session.add(
                    e.MockRequestReceipt(
                        session_id=id, request_id=request.request_id, request_hash=request_hash
                    )
                )
                run = await require(session, e.AgentRun, row.run_id)
                run.status = RunStatus.COMPLETED if row.status == "completed" else RunStatus.RUNNING
                if row.status == "completed":
                    run.finished_at = e.utcnow()
        if generate:
            await self.generate(id)
        return await self.view(id)

    async def generate(self, id: UUID) -> None:
        import asyncio

        failure: str | None = None
        output = None
        cancelled = False
        try:
            async with self.sessions() as session:
                row = await require(session, e.MockInterviewSession, id)
                history = await turns(session, id)
                context = FrozenContext.model_validate(row.context)
                kind, parent = next_kind(row, history)
                inputs = generation_inputs(row, history)
                policy = InterviewPolicy.model_validate(row.execution_policy)
            assert row.generation_operation_id is not None
            accepted = await self.calls.generate(
                "mock",
                id,
                "mock_interview_turn_generation",
                inputs,
                policy.mock_generation,
                lambda value: validate_turn(value, context, kind, parent),
                logical_operation_id=row.generation_operation_id,
            )
            output = cast(TurnOutput, accepted.output)
        except ModelGatewayError as exc:
            failure = exc.code
        except asyncio.CancelledError:
            cancelled, failure = True, "execution_cancelled"
        async with self.sessions.begin() as session:
            row = await require(session, e.MockInterviewSession, id, lock=True)
            row.generation_active = False
            row.revision += 1
            row.stop_reason = failure
            if output is not None:
                await validate_accepted_call(
                    session, accepted, row.run_id, row.generation_operation_id
                )
                turn = e.MockInterviewTurn(
                    session_id=id,
                    sequence=row.interviewer_turn_count + 1,
                    data=output.model_dump(mode="json"),
                    logical_operation_id=accepted.logical_operation_id,
                    accepted_model_call_id=accepted.model_call_id,
                )
                session.add(turn)
                await session.flush()
                row.generation_operation_id = None
                row.pending_question_id = turn.id
                row.primary_question_count += output.kind == "primary"
                row.followup_count += output.kind == "follow_up"
                row.interviewer_turn_count += 1
                row.status = "waiting_answer"
            else:
                row.status = "ready_to_generate"
            run = await require(session, e.AgentRun, row.run_id)
            run.status = RunStatus.WAITING_INPUT
            run.stop_reason = failure
        if cancelled:
            raise asyncio.CancelledError()
