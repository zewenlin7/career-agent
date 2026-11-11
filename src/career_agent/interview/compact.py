"""Compact provider evaluations; canonical artifacts retain exact entry UUID evidence."""

import hashlib
import json
import re
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from career_agent.domain.schemas import Contract
from career_agent.interview.contracts import (
    ExampleAnswer,
    OverallEvaluation,
    QuestionGroupEvaluation,
    SourceSnapshot,
)
from career_agent.interview.numbering import anchor, numbered
from career_agent.models.contracts import ModelGatewayError
from career_agent.runtime.contracts import OutputDiagnostic, ReferenceDiagnostic, ValidationIssue


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


# V2 is retained above for accepted historical outputs. New overall findings must
# name individual answered anchors; the single-entry group shorthand does not apply.
QuestionNumber = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*(?:\.[1-9][0-9]*)?$")]


class OverallFinding(Contract):
    content: str = Field(min_length=1, max_length=2000)
    evidence: list[QuestionNumber] = Field(min_length=1, max_length=500)


class CompactOverallV3(Contract):
    strengths: list[OverallFinding] = Field(max_length=12)
    recurring_issues: list[OverallFinding] = Field(max_length=12)
    knowledge_gap_hypotheses: list[OverallFinding] = Field(max_length=12)
    practice_recommendations: list[OverallFinding] = Field(max_length=12)
    knowledge_candidates: list[OverallFinding] = Field(max_length=12)


def reference_failure(
    field: str,
    index: int,
    evidence: list[str],
    allowed: list[str],
    all_numbers: set[str],
    group_ref: UUID | None,
) -> ModelGatewayError:
    bad_index = next((i for i, value in enumerate(evidence) if value not in allowed), None)
    value = evidence[bad_index] if bad_index is not None else ""
    numeric = bool(re.fullmatch(r"[1-9][0-9]*(?:\.[1-9][0-9]*)?", value))
    reason = (
        "missing"
        if not evidence
        else "unanswered_number"
        if value in all_numbers
        else "unknown_number"
        if numeric
        else "malformed_number"
    )
    kind = (
        "empty"
        if not evidence
        else "number"
        if numeric
        else "uuid"
        if re.fullmatch(r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}", value)
        else "other"
    )
    location: list[str | int] = [field, index, "evidence"]
    if bad_index is not None:
        location.append(bad_index)
    return ModelGatewayError(
        "invalid_evidence_reference",
        diagnostic=OutputDiagnostic(
            failure_kind="output_guardrail_failed",
            guardrail_code="invalid_evidence_reference",
            validation_issues=[ValidationIssue(loc=location, type=reason)],
            reference_diagnostic=ReferenceDiagnostic.model_validate(
                dict(
                    scope="group" if group_ref else "overall",
                    reason=reason,
                    reference_kind=kind,
                    supplied_count=len(evidence),
                    allowed_count=len(allowed),
                    allowed_hash=hashlib.sha256(
                        json.dumps(allowed, separators=(",", ":")).encode()
                    ).hexdigest(),
                )
            ),
        ),
    )


def canonical(
    output: BaseModel, source: SourceSnapshot, group_ref: UUID | None
) -> QuestionGroupEvaluation | OverallEvaluation:
    # Historical artifacts remain canonical; this conversion applies to new provider outputs.
    if not isinstance(output, (CompactGroup, CompactOverall, CompactOverallV3)):
        raise ModelGatewayError("invalid_evaluation_contract")
    if (group_ref is None) != isinstance(output, (CompactOverall, CompactOverallV3)):
        raise ModelGatewayError("invalid_evaluation_contract")
    entries = [
        entry
        for entry in numbered(source.entries)
        if group_ref is None or entry.entry_id == group_ref or entry.primary_entry_id == group_ref
    ]
    mapping = {anchor(entry): entry.entry_id for entry in entries}
    data = output.model_dump(mode="json")
    allowed = [anchor(entry) for entry in entries if entry.answer]
    for field, findings in data.items():
        if not isinstance(findings, list):
            continue
        for index, finding in enumerate(findings):
            evidence = finding.pop("evidence")
            if not evidence and group_ref is not None and len(entries) == 1:
                evidence = [anchor(entries[0])]
            if not evidence or any(ref not in mapping for ref in evidence):
                raise reference_failure(field, index, evidence, allowed, set(mapping), group_ref)
            if isinstance(output, CompactOverallV3) and any(ref not in allowed for ref in evidence):
                raise reference_failure(field, index, evidence, allowed, set(mapping), group_ref)
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
