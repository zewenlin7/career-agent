"""Persistence models. Content tables are private; runtime tables contain metadata only."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum as PythonEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.domain.rules import (
    ApplicationStatus,
    CallStatus,
    FactStatus,
    ObservationStatus,
    RunStatus,
)
from career_agent.domain.schemas import InterviewNoteData, ProfileData, StarStoryData
from career_agent.infrastructure.db import Base, ValidatedJSON, ValidatedList
from career_agent.runtime.contracts import Budget, Identifier, Usage, VersionMetadata


def utcnow() -> datetime:
    return datetime.now(UTC)


def enum_type(cls: type[PythonEnum], name: str | None = None) -> Enum:
    return Enum(
        cls,
        values_callable=lambda e: [v.value for v in e],
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=name or cls.__name__.lower(),
    )


class Row:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceDocument(Row, Base):
    __tablename__ = "source_documents"
    kind: Mapped[str] = mapped_column(String(100))
    data_ref: Mapped[str] = mapped_column(String(200))  # opaque ID, not an absolute path
    sha256: Mapped[str | None] = mapped_column(String(64))
    trust_level: Mapped[str] = mapped_column(String(40), default="untrusted")


class PersonalProfile(Row, Base):
    __tablename__ = "personal_profiles"
    __table_args__ = (CheckConstraint("revision > 0", name="positive_revision"),)
    revision: Mapped[int] = mapped_column(unique=True)
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(ProfileData))


class PersonalFact(Row, Base):
    __tablename__ = "personal_facts"
    __table_args__ = (
        UniqueConstraint("lineage_id", "revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint(
            "status != 'verified' OR verified_at IS NOT NULL", name="verification_time"
        ),
    )
    lineage_id: Mapped[UUID] = mapped_column(default=uuid4)
    revision: Mapped[int] = mapped_column(default=1)
    statement: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(200))
    status: Mapped[FactStatus] = mapped_column(enum_type(FactStatus), default=FactStatus.PROPOSED)
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT")
    )
    source_locator: Mapped[str | None] = mapped_column(Text)
    replaces_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personal_facts.id", ondelete="RESTRICT"), unique=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StarStory(Row, Base):
    __tablename__ = "star_stories"
    title: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(StarStoryData))


class Company(Row, Base):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(200))


class JobPosting(Row, Base):
    __tablename__ = "job_postings"
    __table_args__ = (CheckConstraint("current_revision > 0", name="positive_revision"),)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    current_revision: Mapped[int] = mapped_column(default=1)


class JobRevision(Row, Base):
    __tablename__ = "job_revisions"
    __table_args__ = (
        UniqueConstraint("job_id", "revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_postings.id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    jd_text: Mapped[str] = mapped_column(Text)


class JobRequirement(Row, Base):
    __tablename__ = "job_requirements"
    __table_args__ = (
        CheckConstraint("importance IN ('must', 'nice_to_have', 'unknown')", name="importance"),
    )
    job_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_revisions.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(200))
    importance: Mapped[str] = mapped_column(String(30))
    source_quote: Mapped[str | None] = mapped_column(Text)


class Application(Row, Base):
    __tablename__ = "applications"
    __table_args__ = (CheckConstraint("revision > 0", name="positive_revision"),)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_postings.id", ondelete="RESTRICT"), unique=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_type(ApplicationStatus), default=ApplicationStatus.TRACKING
    )
    revision: Mapped[int] = mapped_column(default=1)


class ApplicationEvent(Row, Base):
    __tablename__ = "application_events"
    __table_args__ = (
        UniqueConstraint("application_id", "sequence"),
        CheckConstraint("kind IN ('created', 'status_changed', 'correction', 'note')", name="kind"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
        CheckConstraint("kind != 'correction' OR note IS NOT NULL", name="correction_reason"),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    sequence: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        enum_type(ApplicationStatus, "from_status")
    )
    to_status: Mapped[ApplicationStatus | None] = mapped_column(
        enum_type(ApplicationStatus, "to_status")
    )
    note: Mapped[str | None] = mapped_column(Text)


class InterviewSession(Row, Base):
    __tablename__ = "interview_sessions"
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    round_name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[list[dict[str, Any]]] = mapped_column(
        ValidatedList(InterviewNoteData), default=list
    )


class KnowledgeNote(Row, Base):
    __tablename__ = "knowledge_notes"
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    interview_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="RESTRICT")
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT")
    )


class AgentRun(Row, Base):
    __tablename__ = "agent_runs"
    workflow: Mapped[str] = mapped_column(String(128))
    workflow_version: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[RunStatus] = mapped_column(enum_type(RunStatus), default=RunStatus.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(128))
    requested_outputs: Mapped[list[str]] = mapped_column(ValidatedList(Identifier), default=list)
    budget: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(Budget), default=dict)
    consumed_usage: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(Usage), default=dict)


class AgentStep(Row, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        UniqueConstraint("id", "run_id"),
        CheckConstraint("attempt > 0 AND sequence > 0", name="positive_counters"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column()
    node: Mapped[str] = mapped_column(String(128))
    action: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[CallStatus] = mapped_column(enum_type(CallStatus), default=CallStatus.PENDING)
    attempt: Mapped[int] = mapped_column(default=1)
    latency_ms: Mapped[int | None] = mapped_column()
    reason_code: Mapped[str | None] = mapped_column(String(128))
    versions: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(VersionMetadata), default=dict)


class ModelCall(Row, Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        CheckConstraint("attempts > 0", name="positive_attempts"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency"),
        CheckConstraint("estimated_cost IS NULL OR estimated_cost >= 0", name="cost"),
    )
    step_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="CASCADE"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[CallStatus] = mapped_column(enum_type(CallStatus), default=CallStatus.PENDING)
    versions: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(VersionMetadata), default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(Usage), default=dict)
    latency_ms: Mapped[int | None] = mapped_column()
    attempts: Mapped[int] = mapped_column(default=1)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    finish_reason: Mapped[str | None] = mapped_column(String(128))
    schema_validation_state: Mapped[str | None] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool] = mapped_column(default=False)


class ToolCall(Row, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint("attempt > 0", name="positive_attempt"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency"),
    )
    step_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(128))
    tool_version: Mapped[str | None] = mapped_column(String(128))
    attempt: Mapped[int] = mapped_column(default=1)
    status: Mapped[CallStatus] = mapped_column(enum_type(CallStatus), default=CallStatus.PENDING)
    latency_ms: Mapped[int | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool] = mapped_column(default=False)


class Observation(Row, Base):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "(model_call_id IS NOT NULL AND tool_call_id IS NULL) OR "
            "(model_call_id IS NULL AND tool_call_id IS NOT NULL)",
            name="exactly_one_call",
        ),
    )
    model_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_calls.id", ondelete="CASCADE")
    )
    tool_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tool_calls.id", ondelete="CASCADE")
    )
    status: Mapped[ObservationStatus] = mapped_column(enum_type(ObservationStatus))
    data_ref: Mapped[UUID | None] = mapped_column()  # opaque private data reference
    evidence_refs: Mapped[list[str]] = mapped_column(ValidatedList(UUID), default=list)
    warnings: Mapped[list[str]] = mapped_column(
        ValidatedList(Identifier), default=list
    )  # codes only
    error_code: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool] = mapped_column(default=False)


# Defense at the ORM boundary as well as at API/contract boundaries. No raw error
# body or private path can be placed in scalar operational metadata fields.
from pydantic import TypeAdapter  # noqa: E402
from sqlalchemy import event  # noqa: E402

_identifier = TypeAdapter(Identifier)
_RUNTIME_FIELDS = {
    AgentRun: ("workflow", "workflow_version", "stop_reason"),
    AgentStep: ("node", "action", "reason_code"),
    ModelCall: (
        "task_type",
        "provider",
        "model",
        "finish_reason",
        "error_code",
        "schema_validation_state",
    ),
    ToolCall: ("tool_name", "tool_version", "error_code"),
    Observation: ("error_code",),
}


def _validate_runtime(mapper: Any, connection: Any, target: Any) -> None:
    for field in _RUNTIME_FIELDS[type(target)]:
        value = getattr(target, field)
        if value is not None:
            _identifier.validate_python(value)


for _runtime_class in _RUNTIME_FIELDS:
    event.listen(_runtime_class, "before_insert", _validate_runtime)
    event.listen(_runtime_class, "before_update", _validate_runtime)


# Resume domain is private structured content, separate from runtime metadata.
from sqlalchemy import ForeignKeyConstraint  # noqa: E402

from career_agent.resume.schemas import InputSnapshot, RenderReport, ResumeDocument  # noqa: E402


class ResumeVariant(Row, Base):
    __tablename__ = "resume_variants"
    __table_args__ = (CheckConstraint("current_revision > 0", name="positive_revision"),)
    current_revision: Mapped[int] = mapped_column(default=1)


class ResumeVariantRevision(Row, Base):
    __tablename__ = "resume_variant_revisions"
    __table_args__ = (
        UniqueConstraint("resume_variant_id", "revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
    )
    resume_variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("resume_variants.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column()
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT")
    )
    job_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_revisions.id", ondelete="RESTRICT")
    )
    document: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(ResumeDocument))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(InputSnapshot))


class RenderArtifact(Row, Base):
    __tablename__ = "render_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_revision"],
            ["resume_variant_revisions.resume_variant_id", "resume_variant_revisions.revision"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("(artifact_ref IS NULL) = (file_hash IS NULL)", name="artifact_hash_pair"),
        CheckConstraint(
            "(report->>'render_status' = 'accepted') = (artifact_ref IS NOT NULL)",
            name="accepted_file",
        ),
        CheckConstraint(
            "report->>'render_status' != 'accepted' OR "
            "(report->>'validation_status' = 'passed' AND report->>'page_count' = '1')",
            name="accepted_validation",
        ),
    )
    resume_variant_id: Mapped[UUID] = mapped_column()
    resume_variant_revision: Mapped[int] = mapped_column()
    artifact_ref: Mapped[UUID | None] = mapped_column(unique=True)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    report: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(RenderReport))
