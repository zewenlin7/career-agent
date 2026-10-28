"""Mutable presentation choices, separate from immutable factual content."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from career_agent.domain.schemas import Contract
from career_agent.resume.schemas import ResumeDocument, SectionName


class Presentation(Contract):
    hidden_sections: list[SectionName] = Field(default_factory=list, max_length=5)
    hidden_item_ids: list[UUID] = Field(default_factory=list, max_length=500)
    item_order: list[UUID] = Field(default_factory=list, max_length=500)
    compact_item_ids: list[UUID] = Field(default_factory=list, max_length=500)
    experience_order: Literal["work_first", "projects_first"] = "work_first"


class PresentationWrite(Presentation):
    expected_revision: int = Field(ge=1)


def section_rank(name: str, projects_first: bool = False) -> int:
    names = (
        ["summary", "education", "projects", "experience", "skills"]
        if projects_first
        else ["summary", "education", "experience", "projects", "skills"]
    )
    return names.index(name)


def apply_presentation(document: ResumeDocument, value: dict[str, Any]) -> ResumeDocument:
    config = Presentation.model_validate(value)
    result = document.model_copy(deep=True)
    result.sections = [s for s in result.sections if s.name not in config.hidden_sections]
    for section in result.sections:
        section.items = [i for i in section.items if i.item_id not in config.hidden_item_ids]
        rank = {id: index for index, id in enumerate(config.item_order)}
        section.items.sort(key=lambda i: (rank.get(i.item_id, 500 + i.ordering), str(i.item_id)))
        for index, item in enumerate(section.items):
            item.ordering = index
            if item.item_id in config.compact_item_ids:
                if not item.short_text:
                    raise ValueError("compact_expression_unavailable")
                item.text, item.short_text = item.short_text, None
        section.ordering = section_rank(section.name, config.experience_order == "projects_first")
    result.sections = [s for s in result.sections if s.items]
    result.sections.sort(key=lambda s: s.ordering)
    return result
