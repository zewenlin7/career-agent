from datetime import datetime
from uuid import UUID

from career_agent.domain.rules import ApplicationStatus, CallStatus, FactStatus, RunStatus
from career_agent.domain.schemas import (
    Contract,
    InterviewNoteData,
    ProfileData,
    RequirementInput,
)
from career_agent.runtime.contracts import Budget, Usage, VersionMetadata


class RowOut(Contract):
    id: UUID
    created_at: datetime


class ProfileOut(RowOut):
    revision: int
    data: ProfileData


class FactOut(RowOut):
    lineage_id: UUID
    revision: int
    statement: str
    category: str
    status: FactStatus
    source_document_id: UUID | None
    source_locator: str | None
    replaces_id: UUID | None
    verified_at: datetime | None


class RequirementOut(RequirementInput):
    id: UUID


class JobOut(RowOut):
    company_id: UUID
    company_name: str
    revision: int
    title: str
    jd_text: str
    requirements: list[RequirementOut]
    application_id: UUID


class EventOut(RowOut):
    application_id: UUID
    sequence: int
    kind: str
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus | None
    note: str | None


class ApplicationOut(RowOut):
    job_id: UUID
    status: ApplicationStatus
    revision: int
    events: list[EventOut]


class InterviewOut(RowOut):
    application_id: UUID
    round_name: str
    notes: list[InterviewNoteData]


class KnowledgeOut(RowOut):
    title: str
    content: str
    interview_id: UUID | None
    source_document_id: UUID | None


class RunOut(RowOut):
    workflow: str
    workflow_version: str | None
    status: RunStatus
    started_at: datetime | None
    finished_at: datetime | None
    stop_reason: str | None
    requested_outputs: list[str]
    budget: Budget
    consumed_usage: Usage


class StepOut(RowOut):
    run_id: UUID
    sequence: int
    node: str
    action: str | None
    status: CallStatus
    attempt: int
    latency_ms: int | None
    reason_code: str | None
    versions: VersionMetadata
