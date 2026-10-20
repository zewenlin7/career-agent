"""Metadata-only durable facts. No FK to uncommitted business transactions."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.infrastructure.db import Base, ValidatedJSON
from career_agent.infrastructure.entities import Row
from career_agent.models.control.recovery_contracts import (
    ControlEventData,
    DurableSnapshot,
    JournalData,
)


class ControllerState(Row, Base):
    __tablename__ = "controller_states"
    __table_args__ = (UniqueConstraint("scope"), CheckConstraint("revision >= 0", name="revision"))
    scope: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int]
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(DurableSnapshot))


class AttemptJournal(Row, Base):
    __tablename__ = "attempt_journals"
    __table_args__ = (
        UniqueConstraint("attempt_id"),
        CheckConstraint(
            "status IN ('reserved','dispatch_intent','unknown','settled',"
            "'not_dispatched','business_committed')",
            name="status",
        ),
    )
    scope: Mapped[str] = mapped_column(String(128), index=True)
    attempt_id: Mapped[UUID]
    operation_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(JournalData))


class ControlEvent(Row, Base):
    __tablename__ = "control_events"
    __table_args__ = (
        UniqueConstraint("scope", "sequence", name="uq_control_event_sequence"),
        UniqueConstraint("scope", "request_id", name="uq_control_event_request"),
    )
    scope: Mapped[str] = mapped_column(String(128))
    sequence: Mapped[int]
    request_id: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(ControlEventData))


class RecoveryIncident(Row, Base):
    __tablename__ = "recovery_incidents"
    __table_args__ = (UniqueConstraint("attempt_id"),)
    scope: Mapped[str] = mapped_column(String(128), index=True)
    attempt_id: Mapped[UUID]
    revision: Mapped[int] = mapped_column(default=1)
    reason: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(40), default="open")
    resolution: Mapped[str | None] = mapped_column(String(128))
