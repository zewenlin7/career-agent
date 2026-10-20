"""Versioned metadata-only recovery and automatic-control contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from career_agent.domain.schemas import Contract
from career_agent.models.control.contracts import AttemptSelection
from career_agent.runtime.contracts import Identifier, Usage


def utcnow() -> datetime:
    return datetime.now(UTC)


class AutomaticPolicy(Contract):
    sampling_default: Decimal = Field(default=Decimal(".1"), ge=0, le=1)
    sampling_per_task: dict[str, Decimal] = Field(default_factory=dict)
    version: Identifier = "automatic-control-v1"
    recovery_version: Identifier = "recovery-v1"
    enabled: bool = True
    tick_seconds: float = Field(default=10, ge=1, le=300)
    window_seconds: float = Field(default=120, ge=10, le=3600)
    min_observations: int = Field(default=5, ge=1, le=1000)
    cooldown_seconds: float = Field(default=60, ge=1, le=3600)
    decrease_threshold: float = Field(default=0.25, gt=0, le=1)
    increase_threshold: float = Field(default=0.05, ge=0, lt=1)
    min_pressure: float = Field(default=0.25, gt=0, le=1)
    min_concurrency: int = Field(default=1, ge=1)
    max_concurrency: int = Field(default=100, ge=1)
    min_output_reservation: int = Field(default=128, ge=1)
    max_output_reservation: int = Field(default=8192, ge=1, le=32768)
    sampling_min: Decimal = Field(default=Decimal(".01"), ge=0, le=1)
    sampling_max: Decimal = Field(default=Decimal(".5"), ge=0, le=1)

    @model_validator(mode="after")
    def bounds(self) -> "AutomaticPolicy":
        if (
            any(rate < 0 or rate > 1 for rate in self.sampling_per_task.values())
            or self.increase_threshold >= self.decrease_threshold
            or self.min_concurrency > self.max_concurrency
            or self.min_output_reservation > self.max_output_reservation
            or self.sampling_min > self.sampling_max
        ):
            raise ValueError("invalid_control_bounds")
        return self


class Adjustment(Contract):
    pressure: float = Field(default=1, gt=0, le=1)
    concurrency: int | None = Field(default=None, ge=1)
    output_reservation: int | None = Field(default=None, ge=1, le=32768)
    sampling_rate: Decimal | None = Field(default=None, ge=0, le=1)


class Override(Contract):
    values: Adjustment
    expires_at: datetime


class EffectiveState(Contract):
    schema_version: Literal["effective-control-v1"] = "effective-control-v1"
    revision: int = 0
    generation: UUID = Field(default_factory=uuid4)
    ready: bool = False
    kill: bool = False
    global_kill: bool = False
    global_revision: int = 0
    sampling_rates: dict[str, Decimal] = Field(default_factory=dict)
    automatic: dict[str, Adjustment] = Field(default_factory=dict)
    overrides: dict[str, Override] = Field(default_factory=dict)
    last_adjusted: dict[str, datetime] = Field(default_factory=dict)

    def values(self, route: str, now: datetime) -> Adjustment:
        override = self.overrides.get(route)
        if override and override.expires_at > now:
            return override.values
        return self.automatic.get(route, Adjustment())


class DurableSnapshot(Contract):
    schema_version: Literal["controller-snapshot-v1"] = "controller-snapshot-v1"
    policy_hash: str
    saved_at: datetime
    effective: EffectiveState
    # Metadata only: UTC timestamps, quota counters, health observations. Never bodies.
    leases: list[dict[str, Any]] = Field(default_factory=list)
    circuits: dict[str, dict[str, Any]] = Field(default_factory=dict)
    feedback: dict[str, dict[str, Any]] = Field(default_factory=dict)
    sequence: int = 0


class JournalData(Contract):
    schema_version: Literal["attempt-journal-v1"] = "attempt-journal-v1"
    selection: dict[str, Any]  # Deadline is removed: monotonic values are not restart contracts.
    budget_owner_refs: list[UUID] = Field(default_factory=list)
    financial_reservation: Usage
    usage: Usage | None = None
    provider_outcome: Identifier | None = None
    latency_ms: int | None = None
    dispatch_confirmed: bool = False
    dispatched_at: datetime | None = None
    settled_at: datetime | None = None
    model_call_id: UUID | None = None
    artifact_ref: UUID | None = None
    recovered: bool = False

    @model_validator(mode="after")
    def selection_contract(self) -> "JournalData":
        AttemptSelection.model_validate({**self.selection, "deadline": 0})
        if "deadline" in self.selection:
            raise ValueError("monotonic_timestamp_not_durable")
        return self


class ControlEventData(Contract):
    logical_operation_id: UUID | None = None
    version: Identifier = "control-event-v1"
    kind: Identifier
    reason: Identifier
    policy_version: Identifier
    before_revision: int
    after_revision: int
    occurred_at: datetime
    input_window_start: datetime | None = None
    input_window_end: datetime | None = None
    observations: int | None = None
    route: Identifier | None = None
    attempt_id: UUID | None = None
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    snapshot: DurableSnapshot


class OperatorRequest(Contract):
    expected_global_revision: int | None = Field(default=None, ge=0)
    request_id: UUID
    expected_revision: int = Field(ge=0)
    action: Literal["override", "clear_override", "kill", "global_kill", "tick"]
    route: Identifier | None = None
    enabled: bool | None = None
    values: Adjustment | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=86400)

    @model_validator(mode="after")
    def parameters(self) -> "OperatorRequest":
        if self.action == "override" and (
            not self.route or self.values is None or not self.ttl_seconds
        ):
            raise ValueError("override_fields_required")
        if self.action == "clear_override" and not self.route:
            raise ValueError("route_required")
        if self.action in {"kill", "global_kill"} and self.enabled is None:
            raise ValueError("enabled_required")
        if self.action == "global_kill" and self.expected_global_revision is None:
            raise ValueError("global_revision_required")
        return self


class ReconcileRequest(Contract):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    resolution: Literal["inspect", "manual_acknowledge"] = "inspect"
    reason_code: Identifier = "operator_review"
