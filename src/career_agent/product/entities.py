from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.infrastructure.db import Base, ValidatedJSON
from career_agent.infrastructure.entities import Row
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
