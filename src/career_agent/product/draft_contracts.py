"""Reviewable proposals are not verified facts or adopted business artifacts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from career_agent.domain.schemas import Contract, Text

DraftTask = Literal[
    "base_resume_drafting",
    "resume_library_compression",
    "resume_claim_refinement",
    "resume_refinement",
    "greeting_refinement",
    "interview_preparation_refinement",
]


class DraftCreate(Contract):
    request_id: UUID
    task: DraftTask
    profile_id: UUID | None = None
    source_artifact_id: UUID | None = None
    source_resume_revision_id: UUID | None = None
    source_workspace_id: UUID | None = None
    selected_item_ids: list[UUID] = Field(default_factory=list, max_length=500)
    feedback: Text | None = None
    feedback_id: UUID | None = None
    application_id: UUID | None = None
    intent: Literal["refine", "regenerate"] = "refine"
    mode: Literal["fixture", "live"] = "fixture"


class DraftAdopt(Contract):
    pass


class ResumeExpression(Contract):
    source_item_id: UUID
    text: Text
    short_text: Text | None = None


class ResumeExpressions(Contract):
    items: list[ResumeExpression] = Field(min_length=1, max_length=500)
