from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from career_agent.domain.schemas import Contract, Label, PersonalInformation, ProfileData
from career_agent.resume.presentation import Presentation
from career_agent.resume.schemas import ResumeDocument, ResumeItem, ResumeSection

Section = Literal["personal", "education", "experiences", "projects", "skills", "preferences"]


class WorkspaceData(ProfileData):
    display_name: str = Field(default="", max_length=200)


class SectionWrite(Contract):
    record_name: Label | None = None
    expected_record_revision: int | None = Field(default=None, ge=1)
    expected_revision: int = Field(ge=1)
    value: dict[str, Any] | list[dict[str, Any]] | str


class Publish(Contract):
    expected_revision: int = Field(ge=1)


class Restore(Publish):
    profile_id: UUID


class Information(PersonalInformation):
    display_name: Label


class DraftItem(ResumeItem):
    fact_refs: list[UUID] = Field(default_factory=list, max_length=30)


class DraftSection(ResumeSection):
    items: list[DraftItem] = Field(default_factory=list, max_length=100)  # type: ignore[assignment]


class ResumeDraftData(Contract):
    sections: list[DraftSection] = Field(default_factory=list, max_length=5)


class DraftWrite(Publish):
    name: Label
    document: ResumeDraftData


class Rename(Publish):
    name: Label


class ResumeCreate(Contract):
    request_id: UUID | None = None
    profile_id: UUID | None = None


class ResumeEdit(DraftWrite):
    request_id: UUID
    presentation: Presentation | None = None


class ExpressionEdit(Contract):
    request_id: UUID
    generation_id: UUID | None = None
    presentation: Presentation | None = None
    expected_metadata_revision: int | None = Field(default=None, ge=1)
    expected_revision: int = Field(ge=1)
    name: Label
    document: ResumeDocument


class ProfileCreate(Contract):
    request_id: UUID | None = None


class ProfileEditWrite(Publish):
    edit_id: UUID
    data: WorkspaceData


class ProfileEditFinish(Publish):
    edit_id: UUID
