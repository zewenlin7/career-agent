from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from career_agent.domain.rules import ApplicationStatus

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Experience(Contract):
    organization: Label
    role: Label
    description: str = Field(default="", max_length=20000)
    fact_ids: list[UUID] = Field(default_factory=list)


class ProfileData(Contract):
    display_name: Label
    education: list[Experience] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[Experience] = Field(default_factory=list)
    skills: list[Label] = Field(default_factory=list)
    preferences: dict[str, str] = Field(default_factory=dict)


class ProfileWrite(Contract):
    expected_revision: int = Field(ge=0)
    data: ProfileData


class FactCreate(Contract):
    statement: Text
    category: Label
    source_document_id: UUID | None = None
    source_locator: str | None = Field(default=None, max_length=1000)


class FactReplacement(FactCreate):
    expected_revision: int = Field(ge=1)


class StarStoryData(Contract):
    situation: Text
    task: Text
    action: Text
    result: Text
    fact_ids: list[UUID] = Field(default_factory=list)


class RequirementInput(Contract):
    text: Text
    category: Label = "general"
    importance: Annotated[str, StringConstraints(pattern=r"^(must|nice_to_have|unknown)$")] = (
        "unknown"
    )
    source_quote: Text | None = None


class JobCreate(Contract):
    company_name: Label
    title: Label
    jd_text: Text
    requirements: list[RequirementInput] = Field(default_factory=list, max_length=200)


class JobRevisionWrite(Contract):
    expected_revision: int = Field(ge=1)
    title: Label
    jd_text: Text
    requirements: list[RequirementInput] = Field(default_factory=list, max_length=200)


class ApplicationChange(Contract):
    expected_revision: int = Field(ge=1)
    status: ApplicationStatus
    correction: bool = False
    reason: Text | None = None

    @model_validator(mode="after")
    def correction_needs_reason(self) -> "ApplicationChange":
        if self.correction and not self.reason:
            raise ValueError("correction requires reason")
        return self


class NoteCreate(Contract):
    text: Text


class InterviewCreate(Contract):
    application_id: UUID
    round_name: Label


class KnowledgeCreate(Contract):
    title: Label
    content: Text
    interview_id: UUID | None = None
    source_document_id: UUID | None = None


class InterviewNoteData(Contract):
    text: Text
    recorded_at: str
