from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.infrastructure.db import Base
from career_agent.infrastructure.entities import Row, utcnow


class ProfileWorkspace(Base):
    __tablename__ = "profile_workspaces"
    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    revision: Mapped[int] = mapped_column(default=1)
    current_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT")
    )
    base_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT")
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    section_revisions: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ProfilePhoto(Row, Base):
    __tablename__ = "profile_photos"
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column()
    height: Mapped[int] = mapped_column()


class ResumeWorkspace(Row, Base):
    library_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    presentation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    __tablename__ = "resume_workspaces"
    content_sources: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[UUID | None] = mapped_column(unique=True)
    number: Mapped[int | None] = mapped_column()
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resume_workspaces.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(default=1)
    name: Mapped[str] = mapped_column(String(200))
    profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT")
    )
    source_resume_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "resume_variant_revisions.id",
            ondelete="RESTRICT",
            name="fk_resume_workspaces_source_resume",
        )
    )
    # Frozen source even before first Profile publication; draft is never a formal artifact.
    source: Mapped[dict[str, Any]] = mapped_column(JSONB)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    accepted_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resume_variant_revisions.id", ondelete="RESTRICT")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileRecord(Row, Base):
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    __tablename__ = "profile_records"
    editing: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[UUID | None] = mapped_column(unique=True)
    number: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    section_revisions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileRecordSnapshot(Base):
    __tablename__ = "profile_record_snapshots"
    record_id: Mapped[UUID] = mapped_column(
        ForeignKey("profile_records.id", ondelete="RESTRICT"), primary_key=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("personal_profiles.id", ondelete="RESTRICT"), primary_key=True
    )
