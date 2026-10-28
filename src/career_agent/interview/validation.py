"""Deterministic reference/privacy boundaries; not semantic truth or LLM judging."""

import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from career_agent.interview.actual import validate_entries
from career_agent.interview.contracts import (
    FrozenContext,
    OverallEvaluation,
    QuestionGroupEvaluation,
    SourceSnapshot,
    TurnOutput,
)
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.guardrails import chinese, minimize, refs

VALIDATION_VERSION = "interview-validation-v2"


def groups(snapshot: SourceSnapshot) -> list[dict[str, Any]]:
    validate_entries(snapshot.entries)
    ordered = sorted(snapshot.entries, key=lambda e: e.order)
    return [
        {
            "group_ref": str(primary.entry_id),
            "group_index": index,
            "entries": [
                entry.model_dump(mode="json")
                for entry in ordered
                if entry.entry_id == primary.entry_id or entry.primary_entry_id == primary.entry_id
            ],
        }
        for index, primary in enumerate((e for e in ordered if e.kind == "primary"), 1)
    ]


def safe_prose(text: str, *, require_chinese: bool = True) -> None:
    if require_chinese:
        chinese(text)
    if minimize(text) != text or re.search(
        r"总分|能力评分|通过概率|录用概率|offer\s*probability|\bscore\s*[:=]", text, re.I
    ):
        raise ModelGatewayError("interview_output_guardrail_failed")


def validate_turn(
    output: BaseModel, context: FrozenContext, kind: str, parent: UUID | None
) -> None:
    if (
        not isinstance(output, TurnOutput)
        or output.kind != kind
        or output.primary_entry_id != parent
    ):
        raise ModelGatewayError("illegal_question_kind")
    if output.reason_code != ("next_primary" if kind == "primary" else "clarify_answer"):
        raise ModelGatewayError("illegal_question_kind")
    safe_prose(output.question)
    safe_prose(output.topic, require_chinese=False)
    refs(output.fact_refs, set(context.fact_snapshot))
    refs(output.requirement_refs, {UUID(x["id"]) for x in context.data["requirements"]})


def validate_evaluation(output: BaseModel, source: SourceSnapshot, group_ref: UUID | None) -> None:
    entries = source.entries
    if group_ref is not None:
        if not isinstance(output, QuestionGroupEvaluation) or output.group_ref != group_ref:
            raise ModelGatewayError("invalid_group_reference")
        entries = [e for e in entries if e.entry_id == group_ref or e.primary_entry_id == group_ref]
    elif not isinstance(output, OverallEvaluation):
        raise ModelGatewayError("invalid_overall_output")
    answered = {e.entry_id for e in entries if e.answer}
    data = output.model_dump()
    for findings in data.values():
        if not isinstance(findings, list):
            continue
        for finding in findings:
            refs(finding["evidence_refs"], answered)
            safe_prose(finding["content"])
            for entry in entries:
                for original in (entry.question, entry.answer):
                    if (
                        original
                        and len(original.strip()) >= 8
                        and original.strip() in finding["content"]
                    ):
                        raise ModelGatewayError("source_copy_forbidden")
    if isinstance(output, QuestionGroupEvaluation) and output.example_answer:
        if not answered or source.context is None:
            raise ModelGatewayError("example_answer_not_grounded")
        example = output.example_answer
        facts = {UUID(f["id"]): f["statement"] for f in source.context.data["facts"]}
        refs(example.grounded_fact_refs, set(facts))
        # Conservative v0.2b baseline: no novel autobiographical prose in examples.
        expected = "".join(facts[id] for id in example.grounded_fact_refs)

        def compact(text: str) -> str:
            return "".join(text.split())

        if compact(example.content) != compact(expected):
            raise ModelGatewayError("example_answer_not_grounded")
        safe_prose(example.content)
