"""Deterministic references/token checks, not a semantic judge."""

import re
from typing import Any
from uuid import UUID

from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import (
    FitOutput,
    GreetingOutput,
    InterviewOutput,
    RequirementsOutput,
    ResearchOutput,
)
from career_agent.resume.grounding import numbers
from career_agent.resume.schemas import ResumeDocument
from career_agent.security.model_view import minimize as minimize


def chinese(text: str) -> None:
    if not re.search(r"[\u3400-\u9fff]", text):
        raise ModelGatewayError("locale_invalid")


def refs(values: list[UUID], allowed: set[UUID]) -> None:
    if len(values) != len(set(values)) or not set(values) <= allowed:
        raise ModelGatewayError("invalid_reference")


def validate_extraction(output: RequirementsOutput, jd: str) -> RequirementsOutput:
    unique = []
    seen = set()
    for item in output.requirements:
        if item.evidence_span not in jd:
            raise ModelGatewayError("requirement_evidence_missing")
        # Explicit unsupported concept expansion is never an extracted requirement.
        if any(skill.casefold() not in item.evidence_span.casefold() for skill in item.skills):
            raise ModelGatewayError("unsupported_requirement_inference")
        if not numbers(item.normalized_requirement) <= numbers(item.evidence_span):
            raise ModelGatewayError("unsupported_requirement_inference")
        key = (item.evidence_span, item.normalized_requirement)
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return RequirementsOutput(requirements=unique)


def validate_research(output: ResearchOutput, evidence: set[UUID]) -> None:
    for item in output.conclusions + output.inference:
        chinese(item.text)
        refs(item.evidence_refs, evidence)
    for unknown in output.unknowns:
        chinese(unknown)


def validate_fit(
    output: FitOutput, requirements: set[UUID], facts: dict[UUID, dict[str, Any]]
) -> None:
    ids = [i.requirement_ref for i in output.items]
    if set(ids) != requirements or len(ids) != len(requirements):
        raise ModelGatewayError("requirement_coverage_invalid")
    for item in output.items:
        chinese(item.explanation)
        refs(item.fact_refs, set(facts))
        if item.status in {"matched", "partial", "explicit_gap"} and not item.fact_refs:
            raise ModelGatewayError("missing_personal_evidence")
        if item.status == "no_evidence" and item.fact_refs:
            raise ModelGatewayError("fit_status_invalid")
        if item.status == "explicit_gap" and not any(
            facts[f]["category"] == "explicit_gap" for f in item.fact_refs
        ):
            raise ModelGatewayError("gap_requires_explicit_evidence")
        if re.search(
            r"offer\s*probability|录用概率|匹配率|匹配度|match\s*(?:score|rate)",
            item.explanation,
            re.I,
        ) or (
            re.search(r"\d+(?:\.\d+)?\s*[%％]", item.explanation)
            and re.search(r"匹配|录用|概率|\bmatch\b|\boffer\b", item.explanation, re.I)
        ):
            raise ModelGatewayError("fake_probability")
    for name, status in [
        ("strong_matches", "matched"),
        ("partial_matches", "partial"),
        ("evidence_missing", "no_evidence"),
        ("clear_gaps", "explicit_gap"),
    ]:
        values = getattr(output, name)
        if len(values) != len(set(values)) or set(values) != {
            i.requirement_ref for i in output.items if i.status == status
        }:
            raise ModelGatewayError("fit_summary_invalid")


def validate_greeting(
    output: GreetingOutput, requirements: set[UUID], facts: dict[UUID, dict[str, Any]]
) -> None:
    chinese(output.greeting_text)
    refs(output.fact_refs, set(facts))
    refs(output.requirement_refs, requirements)
    supported = " ".join(facts[f]["statement"] for f in output.fact_refs)
    if not numbers(output.greeting_text) <= numbers(supported):
        raise ModelGatewayError("hard_field_mismatch")


def validate_interview(
    output: InterviewOutput, requirements: set[UUID], facts: set[UUID], projects: set[int]
) -> None:
    for group in [
        output.technical_questions,
        output.project_deep_dive_questions,
        output.behavioral_questions,
        output.company_specific_questions,
    ]:
        for question in group:
            chinese(question.question)
            refs(question.related_fact_refs, facts)
            refs(question.related_requirement_refs, requirements)
            if not set(question.related_project_refs) <= projects:
                raise ModelGatewayError("invalid_project_reference")
            for outline in question.answer_outline:
                chinese(outline)
                if len(outline) > 250:
                    raise ModelGatewayError("answer_too_long")


def validate_compression(
    before: ResumeDocument, after: ResumeDocument, protected: list[str]
) -> None:
    if before.model_dump(exclude={"sections"}) != after.model_dump(exclude={"sections"}):
        raise ModelGatewayError("compression_identity_changed")
    old = {i.item_id: i for s in before.sections for i in s.items}
    new = {i.item_id: i for s in after.sections for i in s.items}
    if set(new) - set(old) or any(i.required and id not in new for id, i in old.items()):
        raise ModelGatewayError("compression_required_changed")
    old_sections = {s.section_id: s for s in before.sections}
    for section in after.sections:
        original = old_sections.get(section.section_id)
        if original is None or original.model_dump(exclude={"items"}) != section.model_dump(
            exclude={"items"}
        ):
            raise ModelGatewayError("compression_structure_changed")
        if not {i.item_id for i in section.items} <= {i.item_id for i in original.items}:
            raise ModelGatewayError("compression_structure_changed")
    if any(
        s.required and s.section_id not in {x.section_id for x in after.sections}
        for s in before.sections
    ):
        raise ModelGatewayError("compression_required_changed")
    for id, item in new.items():
        original_item = old[id]
        if item.model_dump(exclude={"text", "short_text"}) != original_item.model_dump(
            exclude={"text", "short_text"}
        ):
            raise ModelGatewayError("compression_facts_changed")
        for text in [item.text, item.short_text]:
            if text is None:
                continue
            if numbers(text) != numbers(original_item.text):
                raise ModelGatewayError("compression_hard_field_changed")
            fields = protected + [c.value for c in original_item.hard_claims]
            if any(value in original_item.text and value not in text for value in fields):
                raise ModelGatewayError("compression_hard_field_changed")
    if sum(len(i.text) for i in new.values()) >= sum(len(i.text) for i in old.values()):
        raise ModelGatewayError("compression_not_shorter")
