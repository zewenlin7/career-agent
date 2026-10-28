from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from career_agent.domain.rules import ApplicationStatus

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Experience(Contract):
    organization: Label
    role: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=20000)
    fact_ids: list[UUID] = Field(default_factory=list)

    entry_id: UUID | None = None
    start_date: str = Field(default="", max_length=20)
    end_date: str = Field(default="", max_length=20)
    achievements: str = Field(default="", max_length=20000)
    hidden_fields: list[
        Literal[
            "role",
            "description",
            "start_date",
            "end_date",
            "achievements",
            "major",
            "degree",
            "technology_stack",
        ]
    ] = Field(default_factory=list)


class Education(Experience):
    degree: str = Field(default="", max_length=200)
    major: str = Field(default="", max_length=200)


class Project(Experience):
    technology_stack: str = Field(default="", max_length=2000)


class PersonalInformation(Contract):
    phone: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=200)
    github: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=500)
    other_contact: str = Field(default="", max_length=500)
    photo_id: UUID | None = None


class ProfileData(Contract):
    display_name: Label
    education: list[Education] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Text] = Field(default_factory=list)
    preferences: dict[str, str] = Field(default_factory=dict)
    personal: PersonalInformation = Field(default_factory=PersonalInformation)
    skills_text: str = Field(default="", max_length=20000)
    fact_ids: list[UUID] = Field(default_factory=list)


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
    company_id: UUID | None = None
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
    expected_revision: Literal[0] = 0
    application_id: UUID
    round_name: Label
    occurred_at: AwareDatetime | None = None
    status: Literal["draft", "completed"] = "completed"
    round_number: int | None = Field(default=None, ge=1, le=50)
    interview_type: Literal["technical", "hr", "mixed", "other"] | None = None


class InterviewEntry(Contract):
    entry_id: UUID = Field(default_factory=uuid4)
    order: int = Field(ge=1, le=10000)
    kind: Literal["primary", "follow_up"]
    question: Text
    answer: Text | None = None
    primary_entry_id: UUID | None = None
    main_question_number: int | None = Field(default=None, ge=1)
    followup_index: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def parent(self) -> "InterviewEntry":
        if (self.kind == "follow_up") != (self.primary_entry_id is not None):
            raise ValueError("invalid_primary_binding")
        return self


class InterviewMutation(Contract):
    expected_revision: int = Field(ge=1)


class InterviewEntryCreate(InterviewMutation):
    entry: InterviewEntry


class InterviewUpdate(InterviewMutation):
    round_name: Label | None = None
    occurred_at: AwareDatetime | None = None
    entries: list[InterviewEntry] | None = Field(default=None, max_length=500)
    status: Literal["draft", "completed"] | None = None
    round_number: int | None = Field(default=None, ge=1, le=50)
    interview_type: Literal["technical", "hr", "mixed", "other"] | None = None
    notes_text: str | None = Field(default=None, max_length=20000)


class InterviewNoteCreate(InterviewMutation):
    text: Text


class KnowledgeCreate(Contract):
    application_id: UUID | None = None
    title: Label
    content: Text
    interview_id: UUID | None = None
    source_document_id: UUID | None = None


class InterviewNoteData(Contract):
    text: Text
    recorded_at: str


class KnowledgeUpdate(Contract):
    expected_revision: int = Field(ge=1)
    title: Label
    content: Text
