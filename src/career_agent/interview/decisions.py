"""Server-owned legal choices and compact current-group context for one model decision."""

from typing import Any
from uuid import UUID

from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.interview.context import clean
from career_agent.interview.contracts import DecisionOutput, FrozenContext, MockPolicy
from career_agent.interview.validation import validate_turn
from career_agent.models.contracts import ModelGatewayError

CONTRACT = "mock-decision-v1"


def inputs_for(row: e.MockInterviewSession, history: list[e.MockInterviewTurn]) -> dict[str, Any]:
    policy = MockPolicy.model_validate(row.policy)
    primary = [t for t in history if t.data["kind"] == "primary"]
    follow = [t for t in history if t.data["kind"] == "follow_up"]
    if len(primary) != row.primary_question_count or len(follow) != row.followup_count:
        raise DomainError("interview_source_contract_incompatible", 422)
    latest = history[-1] if history else None
    current = None
    if latest:
        current = (
            latest
            if latest.data["kind"] == "primary"
            else next((t for t in primary if str(t.id) == latest.data["primary_entry_id"]), None)
        )
        if current is None:
            raise DomainError("interview_source_contract_incompatible", 422)
    parent = str(current.id) if current else None
    group = [
        t
        for t in history
        if t.id == (current.id if current else None)
        or (current and t.data["primary_entry_id"] == str(current.id))
    ]
    # Validated JSON stores UUID references as strings.
    remaining_primary = int(policy.primary_target or 0) - len(primary)
    remaining_followup = int(policy.followup_max or 0) - len(follow)
    answered = all(t.answer is not None for t in history)
    allowed = []
    if answered:
        if remaining_primary > 0:
            allowed.append("ask_primary")
        if current and remaining_followup > 0:
            allowed.append("ask_follow_up")
        if remaining_primary == 0:
            allowed.append("finish")
    group_ids = {t.id for t in group}
    return {
        "stable_context": FrozenContext.model_validate(row.context).data,
        "question_history": [
            {
                "entry_id": str(t.id),
                "kind": t.data["kind"],
                "question": t.data["question"],
                "primary_entry_id": t.data["primary_entry_id"],
            }
            for t in history
            if t.id not in group_ids
        ],
        "current_group": {
            "primary_entry_id": parent,
            "entries": [
                {
                    "entry_id": str(t.id),
                    "kind": t.data["kind"],
                    "question": t.data["question"],
                    "answer": clean(t.answer) if t.answer is not None else None,
                    "primary_entry_id": t.data["primary_entry_id"],
                }
                for t in group
            ],
        },
        "policy": {
            "decision_contract_version": CONTRACT,
            "focus": row.focus,
            "primary_question_count": len(primary),
            "followup_count": len(follow),
            "interviewer_turn_count": len(history),
            "remaining_primary": remaining_primary,
            "remaining_followup": remaining_followup,
            "all_answered": answered,
            "current_primary_id": parent,
            "current_question_id": str(history[-1].id) if history else None,
            "legal_actions": allowed,
            **row.policy,
        },
    }


def validate(output: DecisionOutput, context: FrozenContext, inputs: dict[str, Any]) -> None:
    policy = inputs["policy"]
    if not policy["all_answered"]:
        raise ModelGatewayError("answer_required")
    if output.action == "finish":
        if "finish" not in policy["legal_actions"] or policy["remaining_primary"] != 0:
            raise ModelGatewayError("illegal_interview_finish")
        return
    assert output.turn is not None
    turn = output.turn
    action = "ask_primary" if turn.kind == "primary" else "ask_follow_up"
    remaining = (
        policy["remaining_primary"] if turn.kind == "primary" else policy["remaining_followup"]
    )
    if action not in policy["legal_actions"] or remaining <= 0:
        raise ModelGatewayError("illegal_question_kind")
    parent = policy["current_primary_id"] if turn.kind == "follow_up" else None
    if turn.kind == "follow_up" and parent is None:
        raise ModelGatewayError("illegal_question_kind")
    validate_turn(turn, context, turn.kind, UUID(parent) if parent else None)


def metadata(output: DecisionOutput) -> dict[str, Any]:
    return {
        "action": output.action,
        "kind": output.turn.kind if output.turn else None,
        "primary_entry_id": str(output.turn.primary_entry_id)
        if output.turn and output.turn.primary_entry_id
        else None,
    }
