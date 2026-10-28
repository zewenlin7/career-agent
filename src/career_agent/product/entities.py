from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.infrastructure.db import Base, ValidatedJSON
from career_agent.infrastructure.entities import Row, utcnow
from career_agent.product.contracts import OperationCreate, SubmissionCreate


class ProductOperation(Row, Base):
    __tablename__ = "product_operations"
    request_id: Mapped[UUID] = mapped_column(unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    # Preallocated identity survives an uncommitted business run; deliberately no FK.
    run_id: Mapped[UUID] = mapped_column(unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(OperationCreate))
    package_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("preparation_artifacts.id", ondelete="RESTRICT")
    )
    research_report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_research.id", ondelete="RESTRICT")
    )
    reason: Mapped[str | None] = mapped_column(String(128))


class MaterialSubmission(Row, Base):
    __tablename__ = "material_submissions"
    request_id: Mapped[UUID] = mapped_column(unique=True)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("application_events.id", ondelete="RESTRICT"), unique=True
    )
    resume_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resume_variant_revisions.id", ondelete="RESTRICT")
    )
    render_artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("render_artifacts.id", ondelete="RESTRICT")
    )
    greeting_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("preparation_artifacts.id", ondelete="RESTRICT")
    )
    package_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("preparation_artifacts.id", ondelete="RESTRICT")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(SubmissionCreate))


class ApplicationBinding(Base):
    """Current defaults only. Executions copy exact refs; no historical artifact is rewritten."""

    __tablename__ = "application_bindings"
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(default=1)
    profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT")
    )
    resume_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resume_variant_revisions.id", ondelete="RESTRICT")
    )
    job_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_revisions.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductDraft(Row, Base):
    __tablename__ = "product_drafts"
    request_id: Mapped[UUID] = mapped_column(unique=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), unique=True
    )
    logical_operation_id: Mapped[UUID] = mapped_column(unique=True)
    task: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    reason: Mapped[str | None] = mapped_column(String(128))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    accepted_model_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_calls.id", ondelete="RESTRICT")
    )
    adopted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
