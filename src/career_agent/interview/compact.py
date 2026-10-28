"""Compact provider evaluations; canonical artifacts retain exact entry UUID evidence."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from career_agent.domain.schemas import Contract
from career_agent.interview.contracts import (
    ExampleAnswer,
    OverallEvaluation,
    QuestionGroupEvaluation,
    SourceSnapshot,
)
from career_agent.interview.numbering import anchor, numbered
from career_agent.models.contracts import ModelGatewayError


class CompactFinding(Contract):
    content: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=500)


class CompactGroup(Contract):
    strengths: list[CompactFinding] = Field(max_length=8)
    issues: list[CompactFinding] = Field(max_length=8)
    knowledge_gap_hypotheses: list[CompactFinding] = Field(max_length=8)
    improvement_suggestions: list[CompactFinding] = Field(max_length=8)
    example_answer: ExampleAnswer | None = None


class CompactOverall(Contract):
    strengths: list[CompactFinding] = Field(max_length=12)
    recurring_issues: list[CompactFinding] = Field(max_length=12)
    knowledge_gap_hypotheses: list[CompactFinding] = Field(max_length=12)
    practice_recommendations: list[CompactFinding] = Field(max_length=12)
    knowledge_candidates: list[CompactFinding] = Field(max_length=12)


def canonical(
    output: BaseModel, source: SourceSnapshot, group_ref: UUID | None
) -> QuestionGroupEvaluation | OverallEvaluation:
    # Historical artifacts remain canonical; this conversion applies to new provider outputs.
    if not isinstance(output, (CompactGroup, CompactOverall)):
        raise ModelGatewayError("invalid_evaluation_contract")
    if (group_ref is None) != isinstance(output, CompactOverall):
        raise ModelGatewayError("invalid_evaluation_contract")
    entries = [
        entry
        for entry in numbered(source.entries)
        if group_ref is None or entry.entry_id == group_ref or entry.primary_entry_id == group_ref
    ]
    mapping = {anchor(entry): entry.entry_id for entry in entries}
    data = output.model_dump(mode="json")
    for findings in data.values():
        if not isinstance(findings, list):
            continue
        for finding in findings:
            evidence = finding.pop("evidence")
            if not evidence and group_ref is not None and len(entries) == 1:
                evidence = [anchor(entries[0])]
            if not evidence or any(ref not in mapping for ref in evidence):
                raise ModelGatewayError("invalid_evidence_reference")
            finding["evidence_refs"] = [str(mapping[ref]) for ref in evidence]
    if group_ref is not None:
        return QuestionGroupEvaluation.model_validate({**data, "group_ref": group_ref})
    return OverallEvaluation.model_validate(data)


def compact_entries(source: SourceSnapshot, group_ref: UUID | None) -> list[dict[str, Any]]:
    return [
        {"number": anchor(entry), "question": entry.question, "answer": entry.answer}
        for entry in numbered(source.entries)
        if group_ref is None or entry.entry_id == group_ref or entry.primary_entry_id == group_ref
    ]
