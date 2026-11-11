"""Interviewer-visible expressions; authoritative evidence stays server-side."""

from typing import Any
from uuid import UUID

from career_agent.domain.rules import DomainError
from career_agent.resume.presentation import apply_presentation
from career_agent.resume.schemas import ResumeDocument


def visible_materials(
    document: dict[str, Any],
    presentation: dict[str, Any],
    facts: dict[UUID, dict[str, Any]],
    profile_refs: dict[str, Any],
) -> dict[str, Any]:
    visible = apply_presentation(ResumeDocument.model_validate(document), presentation)
    expressions: dict[UUID, list[str]] = {}
    sections = []
    for section in visible.sections:
        items = []
        for item in section.items:
            if not set(item.fact_refs) <= facts.keys():
                raise DomainError("grounding_failed", 422)
            for ref in item.fact_refs:
                expressions.setdefault(ref, [])
                if item.text not in expressions[ref]:
                    expressions[ref].append(item.text)
            # Short alternatives, removed hard claims and layout are not model material.
            items.append(
                {
                    "item_id": str(item.item_id),
                    "text": item.text,
                    "fact_refs": [str(ref) for ref in item.fact_refs],
                    "requirement_refs": [str(ref) for ref in item.requirement_refs],
                }
            )
        sections.append(
            {"section_id": str(section.section_id), "name": section.name, "items": items}
        )
    projects = []
    for project in profile_refs.get("projects", []):
        refs = [ref for ref in project["fact_refs"] if UUID(ref) in expressions]
        if refs:
            projects.append({"project_ref": project["project_ref"], "fact_refs": refs})
    return {
        "resume": {"sections": sections},
        "facts": [
            {**facts[ref], "statement": "\n".join(texts)} for ref, texts in expressions.items()
        ],
        "profile_refs": {"projects": projects},
    }
