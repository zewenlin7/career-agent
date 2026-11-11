"""Text mock interview: explicit durable answers, bounded single-question generation."""

from typing import Any, Literal, cast
from uuid import UUID, uuid4

from anyio import CancelScope
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import check_revision, require
from career_agent.config import Settings
from career_agent.domain.rules import CallStatus, DomainError, RunStatus
from career_agent.domain.schemas import InterviewEntry
from career_agent.infrastructure import entities as e
from career_agent.interview.calls import AcceptedCall, InterviewCalls, validate_accepted_call
from career_agent.interview.context import clean, digest, freeze
from career_agent.interview.contracts import (
    AnswerSubmit,
    Continuation,
    DecisionOutput,
    FrozenContext,
    LegacyTurnOutput,
    MockCreate,
    MockPolicy,
    TurnOutput,
)
from career_agent.interview.execution import available
from career_agent.interview.numbering import anchor, numbered
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


def legacy_next_kind(
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


def legacy_generation_inputs(
    row: e.MockInterviewSession, history: list[e.MockInterviewTurn], *, legacy_topics: bool = False
) -> dict[str, Any]:
    kind, parent = legacy_next_kind(row, history)
    last = history[-1] if history else None
    return {
        "stable_context": FrozenContext.model_validate(row.context).data,
        "question_history": [
            {
                "entry_id": str(t.id),
                "kind": t.data["kind"],
                "question": t.data["question"],
                **({"topic": t.data["topic"]} if legacy_topics else {}),
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


def generation_inputs(
    row: e.MockInterviewSession, history: list[e.MockInterviewTurn], *, legacy_topics: bool = False
) -> dict[str, Any]:
    if legacy_topics:
        return legacy_generation_inputs(row, history, legacy_topics=True)
    from career_agent.interview.decisions import inputs_for

    return inputs_for(row, history)


def decision_metadata(output: DecisionOutput | TurnOutput) -> dict[str, Any]:
    from career_agent.interview.decisions import metadata

    value = (
        output if isinstance(output, DecisionOutput) else DecisionOutput(action="ask", turn=output)
    )
    return {
        **metadata(value),
        "origin": "model" if isinstance(output, DecisionOutput) else "legacy_scheduled",
    }


class MockService:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], settings: Settings, gateway: ModelGateway
    ) -> None:
        self.sessions, self.settings, self.gateway = sessions, settings, gateway
        self.calls = InterviewCalls(sessions, gateway)

    def inputs(
        self, row: e.MockInterviewSession, history: list[e.MockInterviewTurn]
    ) -> dict[str, Any]:
        version = self.gateway.prompts.resolve(
            "mock_interview_turn_generation"
        ).output_schema_version
        if version.endswith(("-v1", "-v2")):
            return legacy_generation_inputs(row, history, legacy_topics=version.endswith("-v1"))
        return generation_inputs(row, history)

    async def create(self, request: MockCreate) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            request_hash = digest(request.model_dump(mode="json"))
            if request.request_id:
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 7202))"),
                    {"key": str(request.request_id)},
                )
                existing = await session.scalar(
                    select(e.MockInterviewSession).where(
                        e.MockInterviewSession.request_id == request.request_id
                    )
                )
                if existing:
                    if existing.request_hash != request_hash:
                        raise DomainError("idempotency_conflict")
                    return await self.view(existing.id)
            if request.application_binding:
                from career_agent.product.bindings import read as read_binding
                from career_agent.product.bindings import view as binding_view

                binding = await binding_view(
                    session, await read_binding(session, request.application_binding.application_id)
                )
                check_revision(binding.revision, request.application_binding.revision)
                if (binding.profile_id, binding.resume_revision_id, binding.job_revision_id) != (
                    request.context.profile_id,
                    request.context.resume_revision_id,
                    request.context.job_revision_id,
                ):
                    raise DomainError("context_revision_mismatch", 422)
            context = await freeze(
                session, self.settings, self.gateway, request.context, visible_only=True
            )
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
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 7201))"),
                {"key": str(context.job_id)},
            )
            number = (
                await session.scalar(
                    select(func.max(e.MockInterviewSession.display_number)).where(
                        e.MockInterviewSession.context["job_id"].astext == str(context.job_id)
                    )
                )
                or 0
            ) + 1
            row = e.MockInterviewSession(
                application_id=request.application_binding.application_id
                if request.application_binding
                else None,
                request_id=request.request_id,
                request_hash=request_hash if request.request_id else None,
                display_number=number,
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
            latest_receipt = await session.scalar(
                select(e.MockRequestReceipt)
                .where(e.MockRequestReceipt.session_id == id)
                .order_by(e.MockRequestReceipt.created_at.desc(), e.MockRequestReceipt.id.desc())
                .limit(1)
            )
            display = {
                entry.entry_id: entry
                for entry in numbered(
                    [
                        InterviewEntry(
                            entry_id=t.id,
                            order=t.sequence,
                            kind=t.data["kind"],
                            question=t.data["question"],
                            answer=t.answer,
                            primary_entry_id=t.data["primary_entry_id"],
                        )
                        for t in history
                    ]
                )
            }
            from career_agent.interview.ownership import mock_owner

            orphaned = row.generation_active and await available(session, id)
            return {
                "id": id,
                "application_id": await mock_owner(session, row),
                "display_number": row.display_number,
                "run_id": row.run_id,
                "revision": row.revision,
                "status": row.status,
                "completion_type": row.completion_type,
                "stop_reason": "execution_outcome_unknown" if orphaned else row.stop_reason,
                "latest_request_id": latest_receipt.request_id if latest_receipt else None,
                "generation_active": row.generation_active and not orphaned,
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
                        "main_question_number": display[t.id].main_question_number,
                        "followup_index": display[t.id].followup_index,
                        "question_number": anchor(display[t.id]),
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
        self,
        id: UUID,
        request: Continuation,
        operation: Literal["answer", "generate", "end", "recover"],
    ) -> dict[str, Any]:
        # Serialize the full action, including accepted-output adoption and turn commit.
        # A crash releases this lock; the durable flag alone does not imply a live worker.
        async with self.sessions.begin() as execution:
            if not await available(execution, id):
                raise DomainError("generation_in_progress")
            return await self._continue_locked(id, request, operation)

    async def _continue_locked(
        self,
        id: UUID,
        request: Continuation,
        operation: Literal["answer", "generate", "end", "recover"],
    ) -> dict[str, Any]:
        payload = request.model_dump(mode="json")
        # Preserve receipts written before early-end-with-answer was supported.
        if payload.get("end_early") is False:
            payload.pop("end_early")
        request_hash = digest({"operation": operation, **payload})
        generate = False
        recovered = None
        decision_context = None
        decision_input_hash = None
        async with self.sessions.begin() as session:
            row = await require(session, e.MockInterviewSession, id, lock=True)
            from career_agent.application.services import active_interview_target

            await active_interview_target(session, row)
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
                if operation == "recover":
                    recovered = await self.accepted_output(
                        session, row, generation_inputs(row, await turns(session, id))
                    )
                    if recovered is None:
                        raise DomainError("execution_outcome_unknown")
                elif row.stop_reason in {"recovery_decision_required", "execution_outcome_unknown"}:
                    raise DomainError("execution_outcome_unknown")
                elif row.generation_active:
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
                if operation == "end" or (isinstance(request, AnswerSubmit) and request.end_early):
                    row.status, row.completion_type = "completed", "user_ended_early"
                    row.pending_question_id = None
                elif generation_inputs(row, history)["policy"]["legal_actions"] == ["finish"]:
                    final_inputs = generation_inputs(row, history)
                    decision_context, decision_input_hash = (
                        final_inputs["policy"],
                        digest(final_inputs),
                    )
                    row.status, row.completion_type = "completed", "target_reached"
                else:
                    if (
                        FrozenContext.model_validate(row.context).schema_version
                        != "interview-context-v2"
                    ):
                        raise DomainError("interview_source_contract_incompatible", 422)
                    inputs = self.inputs(row, history)
                    if row.generation_operation_id and recovered is None:
                        recovered = await self.accepted_output(session, row, inputs)
                    if recovered is None:
                        # An explicitly failed old-contract attempt is closed. A new explicit
                        # decision may adopt the current contract, never replay an unknown request.
                        previous = (
                            await session.scalar(
                                select(e.ModelCall)
                                .where(
                                    e.ModelCall.logical_operation_id == row.generation_operation_id
                                )
                                .order_by(e.ModelCall.attempts.desc())
                            )
                            if row.generation_operation_id
                            else None
                        )
                        if (
                            previous
                            and previous.versions.get("output_schema_version")
                            != self.gateway.prompts.resolve(
                                "mock_interview_turn_generation"
                            ).output_schema_version
                        ):
                            if previous.status != CallStatus.FAILED or previous.error_code in {
                                None,
                                "execution_cancelled",
                                "execution_outcome_unknown",
                                "recovery_decision_required",
                            }:
                                raise DomainError("execution_outcome_unknown")
                            row.generation_operation_id = None
                        policy = InterviewPolicy.model_validate(row.execution_policy)
                        self.calls.preflight(
                            "mock_interview_turn_generation",
                            row.mode,
                            inputs,
                            policy.mock_generation,
                        )
                        decision_context = inputs["policy"]
                        decision_input_hash = digest(inputs)
                    else:
                        decision_context = {
                            "decision_contract_version": "mock-decision-v1"
                            if isinstance(recovered.output, DecisionOutput)
                            else "mock-scheduled-v1",
                            "recovery": True,
                        }
                    row.generation_operation_id = row.generation_operation_id or uuid4()
                    row.generation_active = True
                    generate = True
                row.revision += 1
                row.stop_reason = None
                session.add(
                    e.MockRequestReceipt(
                        session_id=id,
                        request_id=request.request_id,
                        request_hash=request_hash,
                        outcome={
                            "state": "running" if generate else "success",
                            "decision_context": decision_context,
                            "decision_input_hash": decision_input_hash,
                            "decision": None
                            if generate
                            else {
                                "action": "finish",
                                "kind": None,
                                "primary_entry_id": None,
                                "origin": "user"
                                if row.completion_type == "user_ended_early"
                                else "quota_constraint",
                            },
                            "completion_type": row.completion_type,
                            "reason": None,
                            "revision": row.revision,
                            "logical_operation_id": str(row.generation_operation_id)
                            if generate
                            else None,
                        },
                    )
                )
                run = await require(session, e.AgentRun, row.run_id)
                run.status = RunStatus.COMPLETED if row.status == "completed" else RunStatus.RUNNING
                if row.status == "completed":
                    run.finished_at = e.utcnow()
        if generate:
            await self.generate(id, request.request_id)
        return await self.view(id)

    async def generate(self, id: UUID, request_id: UUID) -> None:
        import asyncio

        failure: str | None = None
        output = None
        attempted_decision: dict[str, Any] | None = None
        cancelled = False
        try:
            async with self.sessions() as session:
                row = await require(session, e.MockInterviewSession, id)
                history = await turns(session, id)
                context = FrozenContext.model_validate(row.context)
                kind, parent = legacy_next_kind(row, history)
                inputs = self.inputs(row, history)
                policy = InterviewPolicy.model_validate(row.execution_policy)
            assert row.generation_operation_id is not None
            async with self.sessions() as session:
                accepted = await self.accepted_output(session, row, inputs)

            def validate_candidate(value: BaseModel) -> None:
                nonlocal attempted_decision
                if isinstance(value, (DecisionOutput, TurnOutput)):
                    attempted_decision = decision_metadata(value)
                self.validate_output(value, context, inputs, kind, parent)

            if accepted is None:
                accepted = await self.calls.generate(
                    "mock",
                    id,
                    "mock_interview_turn_generation",
                    inputs,
                    policy.mock_generation,
                    validate_candidate,
                    logical_operation_id=row.generation_operation_id,
                )
            output = cast(DecisionOutput | TurnOutput, accepted.output)
        except ModelGatewayError as exc:
            failure = exc.code
        except asyncio.CancelledError:
            cancelled, failure = True, "execution_cancelled"
        try:
            with CancelScope(shield=cancelled):
                async with self.sessions.begin() as session:
                    row = await require(session, e.MockInterviewSession, id, lock=True)
                    row.generation_active = False
                    row.revision += 1
                    row.stop_reason = failure
                    if output is not None:
                        assert accepted is not None
                        await validate_accepted_call(
                            session, accepted, row.run_id, row.generation_operation_id
                        )
                        decision = (
                            output
                            if isinstance(output, DecisionOutput)
                            else DecisionOutput(action="ask", turn=output)
                        )
                        from career_agent.evaluation.recording import bind_artifact

                        if decision.action == "finish":
                            await bind_artifact(
                                session,
                                accepted.model_call_id,
                                row.id,
                                self.settings.judge_sampling,
                            )
                            row.status, row.completion_type = "completed", "target_reached"
                            row.pending_question_id = None
                        else:
                            assert decision.turn is not None
                            turn = e.MockInterviewTurn(
                                session_id=id,
                                sequence=row.interviewer_turn_count + 1,
                                data=decision.turn.model_dump(mode="json"),
                                logical_operation_id=accepted.logical_operation_id,
                                accepted_model_call_id=accepted.model_call_id,
                            )
                            session.add(turn)
                            await session.flush()
                            await bind_artifact(
                                session,
                                accepted.model_call_id,
                                turn.id,
                                self.settings.judge_sampling,
                            )
                            row.pending_question_id = turn.id
                            row.primary_question_count += decision.turn.kind == "primary"
                            row.followup_count += decision.turn.kind == "follow_up"
                            row.interviewer_turn_count += 1
                            row.status = "waiting_answer"
                        row.generation_operation_id = None
                    else:
                        row.status = "ready_to_generate"
                    run = await require(session, e.AgentRun, row.run_id)
                    run.status = (
                        RunStatus.COMPLETED
                        if row.status == "completed"
                        else RunStatus.WAITING_INPUT
                    )
                    if row.status == "completed":
                        run.finished_at = e.utcnow()
                    run.stop_reason = failure
                    receipt = await session.scalar(
                        select(e.MockRequestReceipt).where(
                            e.MockRequestReceipt.session_id == id,
                            e.MockRequestReceipt.request_id == request_id,
                        )
                    )
                    assert receipt is not None
                    receipt.outcome = {
                        **(receipt.outcome or {}),
                        "state": "success"
                        if output is not None
                        else "cancelled"
                        if cancelled
                        else "unknown"
                        if failure in {"recovery_decision_required", "execution_outcome_unknown"}
                        else "failure",
                        "reason": failure,
                        "revision": row.revision,
                        "decision": decision_metadata(output)
                        if output is not None
                        else attempted_decision,
                        "validation": "accepted"
                        if output is not None
                        else "rejected_or_unavailable",
                        "completion_type": row.completion_type,
                        "accepted_model_call_id": str(accepted.model_call_id)
                        if output is not None and accepted is not None
                        else None,
                        "question_id": str(row.pending_question_id)
                        if row.pending_question_id
                        else None,
                    }
        except SQLAlchemyError:
            # The accepted provider output is already durable; retain its logical identity.
            # A subsequent explicit generation request restores it without another call.
            async with self.sessions.begin() as session:
                row = await require(session, e.MockInterviewSession, id, lock=True)
                row.generation_active = False
                row.status = "ready_to_generate"
                row.stop_reason = "artifact_save_failed"
                run = await require(session, e.AgentRun, row.run_id)
                run.status = RunStatus.WAITING_INPUT
                run.stop_reason = row.stop_reason
                row.revision += 1
                receipt = await session.scalar(
                    select(e.MockRequestReceipt).where(
                        e.MockRequestReceipt.session_id == id,
                        e.MockRequestReceipt.request_id == request_id,
                    )
                )
                assert receipt is not None
                receipt.outcome = {
                    **(receipt.outcome or {}),
                    "state": "failure",
                    "reason": "artifact_save_failed",
                    "revision": row.revision,
                    "accepted_model_call_id": str(accepted.model_call_id)
                    if output is not None and accepted is not None
                    else None,
                }
        if cancelled:
            raise asyncio.CancelledError()

    @staticmethod
    def validate_output(
        value: BaseModel,
        context: FrozenContext,
        inputs: dict[str, Any],
        kind: str,
        parent: UUID | None,
    ) -> None:
        if isinstance(value, DecisionOutput):
            from career_agent.interview.decisions import validate

            validate(value, context, inputs)
        else:
            validate_turn(value, context, kind, parent)

    async def accepted_output(
        self, session: AsyncSession, row: e.MockInterviewSession, inputs: dict[str, Any]
    ) -> AcceptedCall | None:
        from career_agent.evaluation.contracts import OperationSnapshot
        from career_agent.evaluation.entities import InvocationRow

        if row.generation_operation_id is None:
            return None
        records = list(
            await session.scalars(
                select(InvocationRow)
                .join(e.ModelCall, InvocationRow.model_call_id == e.ModelCall.id)
                .where(e.ModelCall.logical_operation_id == row.generation_operation_id)
                .order_by(e.ModelCall.attempts.desc())
            )
        )
        for record in records:
            snapshot = OperationSnapshot.model_validate(record.data)
            if snapshot.output is None or snapshot.accepted_model_call_id is None:
                continue
            version = str(snapshot.provenance.get("output_schema_version", ""))
            history = await turns(session, row.id)
            legacy = version in {
                "mock_interview_turn_generation-output-v1",
                "mock_interview_turn_generation-output-v2",
            }
            expected_inputs = (
                legacy_generation_inputs(row, history, legacy_topics=version.endswith("-v1"))
                if legacy
                else inputs
            )
            # Composition is canonical ordering only, never a source substitution.
            spec = self.gateway.prompts.resolve("mock_interview_turn_generation")
            expected = (
                spec.composition.compose(expected_inputs) if spec.composition else expected_inputs
            )
            if snapshot.input_snapshot != expected:
                raise DomainError("interview_source_contract_incompatible", 422)
            context = FrozenContext.model_validate(row.context)
            output: DecisionOutput | TurnOutput
            if legacy:
                output = (
                    LegacyTurnOutput if version.endswith("-v1") else TurnOutput
                ).model_validate(snapshot.output)
                kind, parent = legacy_next_kind(row, history)
                validate_turn(output, context, kind, parent)
            elif version == "mock_interview_turn_generation-output-v3":
                from career_agent.interview.decisions import validate

                output = DecisionOutput.model_validate(snapshot.output)
                validate(output, context, inputs)
            else:
                raise DomainError("interview_source_contract_incompatible", 422)
            accepted = AcceptedCall(
                output, snapshot.accepted_model_call_id, row.generation_operation_id
            )
            await validate_accepted_call(session, accepted, row.run_id, row.generation_operation_id)
            return accepted
        return None
