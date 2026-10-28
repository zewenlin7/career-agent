"""Small product contracts over exact existing business identities."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from career_agent.domain.schemas import Contract
from career_agent.evaluation.contracts import Subject
from career_agent.preparation.contracts import CompanyResearchRequest, WorkflowRequest

OperationKind = Literal["prepare_application", "prepare_interview", "company_research"]
OperationStatus = Literal[
    "pending",
    "running",
    "success",
    "partial",
    "failure",
    "needs_input",
    "decision_required",
    "recovery_required",
]


class ApplicationBindingRef(Contract):
    application_id: UUID
    revision: int = Field(ge=1)


class OperationCreate(Contract):
    request_id: UUID
    kind: OperationKind
    application_binding: ApplicationBindingRef | None = None
    request: WorkflowRequest | CompanyResearchRequest

    @model_validator(mode="before")
    @classmethod
    def request_contract(cls, value: Any) -> Any:
        if isinstance(value, dict) and "request" in value:
            value = dict(value)
            request = value["request"]
            if isinstance(request, Contract):
                request = request.model_dump(mode="json")
            schema = (
                CompanyResearchRequest
                if value.get("kind") == "company_research"
                else WorkflowRequest
            )
            value["request"] = schema.model_validate(request)
        return value


class OperationOut(Contract):
    id: UUID
    request_id: UUID
    kind: OperationKind
    status: OperationStatus
    run_id: UUID
    package_id: UUID | None = None
    research_report_id: UUID | None = None
    reason: str | None = None
    created_at: datetime
    allowed_actions: list[str]


class SubmissionCreate(Contract):
    request_id: UUID
    expected_revision: int = Field(ge=1)
    resume_revision_id: UUID
    render_artifact_id: UUID
    greeting_id: UUID | None = None
    package_id: UUID | None = None
    note: str | None = Field(default=None, max_length=20000)


class SubmissionOut(SubmissionCreate):
    id: UUID
    application_id: UUID
    event_id: UUID
    created_at: datetime


class ContextSummary(Contract):
    profile_id: UUID
    profile_revision: int
    job_id: UUID
    job_revision_id: UUID
    job_revision: int
    job_title: str
    company_id: UUID


class ResultView(Contract):
    kind: str
    status: str
    target_artifact_id: UUID | None = None
    result_id: UUID | None = None
    resume_revision_id: UUID | None = None
    source_resume_revision_id: UUID | None = None
    resume_variant_id: UUID | None = None
    revision: int | None = None
    render_artifact_id: UUID | None = None
    download_url: str | None = None
    content: dict[str, Any] | None = None
    context: ContextSummary
    versions: dict[str, Any] = Field(default_factory=dict)
    reused: bool
    feedback_target: Subject | None = None
    reason: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)


class PackageView(Contract):
    package_id: UUID
    run_id: UUID
    status: str
    results: list[ResultView]


class Page[T](Contract):
    items: list[T]
    limit: int
    offset: int
    has_more: bool


class ApplicationBindingWrite(Contract):
    expected_revision: int = Field(ge=1)
    profile_id: UUID | None
    resume_revision_id: UUID | None = None
    job_revision_id: UUID


class ApplicationBindingOut(Contract):
    application_id: UUID
    revision: int
    profile_id: UUID | None
    resume_revision_id: UUID | None
    job_revision_id: UUID
    updated_at: datetime
    profile_name: str | None = None
    profile_revision: int | None = None
    resume_name: str | None = None
    resume_revision: int | None = None
    job_revision: int


class TaskHistoryItem(Contract):
    created_at: datetime
    result: ResultView
