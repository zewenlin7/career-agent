"""Versioned data only: no user template, path, markup or execution controls."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from career_agent.domain.schemas import Contract
from career_agent.resume.fonts import FONT_POLICY_VERSION
from career_agent.runtime.contracts import VersionMetadata

ResumeText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)
]
SectionName = Literal["summary", "experience", "projects", "education", "skills"]
SCHEMA_VERSION = "resume-v2"
TEMPLATE_VERSION = "resume_zh_cn_a4_single_v1"
POLICY_VERSION = "content-v1"
COMPILER_VERSION = "0.15.1"
MAX_ROUNDS = 8
HEADINGS = {
    "summary": "个人简介",
    "experience": "工作经历",
    "projects": "项目经历",
    "education": "教育经历",
    "skills": "技术栈",
}


class HardClaim(Contract):
    kind: Literal["organization", "title", "degree", "date", "number"]
    value: ResumeText
    fact_ref: UUID


class ResumeItem(Contract):
    item_id: UUID
    kind: Literal["bullet", "summary", "entry"]
    text: ResumeText
    short_text: ResumeText | None = None
    fact_refs: list[UUID] = Field(min_length=1, max_length=30)
    requirement_refs: list[UUID] = Field(default_factory=list, max_length=30)
    hard_claims: list[HardClaim] = Field(default_factory=list, max_length=30)
    priority: int = Field(ge=0, le=100, strict=True)
    required: bool = True
    ordering: int = Field(ge=0, le=1000, strict=True)

    @model_validator(mode="after")
    def validate_item(self) -> "ResumeItem":
        if len(set(self.fact_refs)) != len(self.fact_refs):
            raise ValueError("duplicate fact references")
        if self.short_text and len(self.short_text) >= len(self.text):
            raise ValueError("short_text must be shorter")
        for value in [self.text, self.short_text, *(c.value for c in self.hard_claims)]:
            if value and any(ord(c) < 32 and c not in "\n\t" for c in value):
                raise ValueError("control characters are not supported")
        return self


class ResumeSection(Contract):
    section_id: UUID
    name: SectionName
    ordering: int = Field(ge=0, le=1000, strict=True)
    priority: int = Field(ge=0, le=100, strict=True)
    required: bool = True
    items: list[ResumeItem] = Field(min_length=1, max_length=100)


class ResumeMetadata(Contract):
    label: Annotated[str, StringConstraints(max_length=200)] | None = None


class ResumeDocument(Contract):
    locale: Literal["zh-CN"] = "zh-CN"
    metadata: ResumeMetadata = Field(default_factory=ResumeMetadata)
    schema_version: Literal["resume-v2"] = "resume-v2"
    template: Literal["resume_zh_cn_a4_single_v1"] = "resume_zh_cn_a4_single_v1"
    target_page_count: Literal[1] = 1
    profile_id: UUID
    profile_revision: int = Field(ge=1, strict=True)
    job_revision_id: UUID | None = None
    sections: list[ResumeSection] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_structure(self) -> "ResumeDocument":
        ids = [s.section_id for s in self.sections] + [
            i.item_id for s in self.sections for i in s.items
        ]
        if len(ids) != len(set(ids)) or len({s.name for s in self.sections}) != len(self.sections):
            raise ValueError("duplicate IDs or section names")
        if not any(i.required for s in self.sections for i in s.items):
            raise ValueError("at least one required factual item is needed")
        if sum(len(i.text) for s in self.sections for i in s.items) > 100000:
            raise ValueError("document too large")
        return self


class RevisionRequest(Contract):
    expected_revision: int = Field(ge=1, strict=True)
    document: ResumeDocument


class FactSnapshot(Contract):
    fact_id: UUID
    revision: int = Field(ge=1)


class InputSnapshot(Contract):
    display_name: str
    facts: list[FactSnapshot]


class Finding(Contract):
    code: str
    item_id: UUID | None = None
    reference_id: UUID | None = None


class Decision(Contract):
    action: Literal["short_text", "remove_item", "remove_section"]
    target_id: UUID


class Selection(Contract):
    # Text is private domain/artifact data, not runtime telemetry.
    sections: list[ResumeSection]
    decisions: list[Decision] = Field(default_factory=list)


class PDFValidation(Contract):
    status: Literal["passed", "failed"]
    page_count: int | None = None
    findings: list[Finding] = Field(default_factory=list)


class Attempt(Contract):
    number: int
    selection_hash: str
    selected_item_ids: list[UUID]
    decisions: list[Decision]
    validation: PDFValidation


class RenderVersions(VersionMetadata):
    resume_variant_schema_version: str = SCHEMA_VERSION
    resume_template_version: str = TEMPLATE_VERSION
    layout_policy_version: str = POLICY_VERSION
    compiler_name: Literal["typst"] = "typst"
    compiler_version: str | None = None
    locale: Literal["zh-CN"] = "zh-CN"
    font_policy_version: str = FONT_POLICY_VERSION
    font_family: str | None = None
    font_file_hashes: dict[str, str] = Field(default_factory=dict)
    template_sha256: str | None = None


class RenderReport(Contract):
    file_hash: str | None = None
    render_status: Literal["accepted", "failed"]
    validation_status: Literal["passed", "failed", "not_run"]
    error_code: str | None = None
    page_count: int | None = None
    findings: list[Finding] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    versions: RenderVersions = Field(default_factory=RenderVersions)


class VariantOut(Contract):
    id: UUID
    revision: int
    created_at: datetime
    document: ResumeDocument
    input_snapshot: InputSnapshot


class RenderRequest(Contract):
    revision: int = Field(ge=1, strict=True)


class ArtifactOut(Contract):
    id: UUID
    resume_variant_id: UUID
    resume_variant_revision: int
    created_at: datetime
    artifact_ref: UUID | None
    file_hash: str | None
    report: RenderReport
