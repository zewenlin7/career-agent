"""Versioned control policies; capacity estimates never replace financial reservations."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from career_agent.domain.schemas import Contract
from career_agent.runtime.contracts import Identifier

TrafficClass = Literal["interactive_user", "normal_user", "background", "evaluation"]
RoutingRole = Literal["primary", "capacity_overflow", "runtime_fallback"]


class OutputPolicy(Contract):
    version: Identifier = "output-policy-v1"
    hard_max_output_tokens: int = Field(default=32768, ge=1, le=32768)
    reservation_output_tokens: int = Field(default=512, ge=1, le=32768)
    partial_output_allowed: Literal[False] = False
    partial_validator_version: Identifier | None = None


class RouteApproval(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Identifier
    model: Identifier
    priority: int = Field(ge=0)
    qualification_ref: Identifier
    roles: frozenset[RoutingRole] = Field(default=frozenset({"primary"}), min_length=1)

    @property
    def route(self) -> str:
        return f"{self.provider}:{self.model}"


class TaskControlPolicy(Contract):
    version: Identifier = "task-control-v1"
    candidates: list[RouteApproval] = Field(min_length=1, max_length=16)
    output: OutputPolicy = Field(default_factory=OutputPolicy)
    max_route_attempts: int = Field(default=3, ge=1, le=10)
    max_total_attempts: int = Field(default=3, ge=1, le=10)
    max_route_switches: int = Field(default=1, ge=0, le=5)
    max_wait_seconds: float = Field(default=0.1, ge=0, le=10)
    operation_seconds: float = Field(default=180, gt=0, le=600)
    degradation_modes: list[Identifier] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def unique(self) -> "TaskControlPolicy":
        if len({c.route for c in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate_approved_route")
        return self


class CapacityLimits(Contract):
    rpm: int = Field(default=10000, ge=1)
    tpm: int = Field(default=10000000, ge=1)
    concurrency: int = Field(default=100, ge=1)


class BreakerPolicy(Contract):
    window_seconds: float = Field(default=60, gt=0)
    minimum_observations: int = Field(default=5, ge=1)
    consecutive_failures: int = Field(default=3, ge=1)
    failure_rate: float = Field(default=0.5, gt=0, le=1)
    cooldown_seconds: float = Field(default=15, gt=0)
    max_half_open_probes: int = Field(default=1, ge=1)
    recovery_successes: int = Field(default=1, ge=1)


class FeedbackBucket(Contract):
    scope: Literal["provider_shared", "route", "shared_group"]
    bucket_id: Identifier


class ControlPolicy(Contract):
    version: Identifier = "runtime-control-v2"
    implementation_version: Identifier = "attempt-controller-v2"
    quota_scope: Identifier = "openai-default-project"
    window_seconds: float = Field(default=60, gt=0)
    headroom_factor: float = Field(default=0.90, gt=0, le=1)
    background_fraction: float = Field(default=0.5, gt=0, le=1)
    provider: CapacityLimits = Field(default_factory=CapacityLimits)
    routes: dict[str, CapacityLimits] = Field(default_factory=dict)
    default_route: CapacityLimits = Field(default_factory=CapacityLimits)
    feedback_buckets: dict[str, FeedbackBucket] = Field(default_factory=dict)
    breaker: BreakerPolicy = Field(default_factory=BreakerPolicy)

    def feedback_bucket(self, provider: str, route: str) -> FeedbackBucket:
        return self.feedback_buckets.get(route, FeedbackBucket(scope="route", bucket_id=route))


class CapacityFeedback(Contract):
    quota_scope: Identifier | None = None
    bucket: FeedbackBucket | None = None
    remaining_requests: int | None = Field(default=None, ge=0)
    remaining_tokens: int | None = Field(default=None, ge=0)
    reset_requests_seconds: float | None = Field(default=None, ge=0, le=3600)
    reset_tokens_seconds: float | None = Field(default=None, ge=0, le=3600)
    retry_after_seconds: float | None = Field(default=None, ge=0, le=3600)


class ControlDecision(Contract):
    logical_operation_id: UUID | None = None
    sequence: int = Field(ge=1)
    route: str
    reason: Identifier
    disposition: Literal["admitted", "denied", "released", "settled"]


class AttemptSelection(Contract):
    controller_generation: UUID | None = None
    automatic_policy_version: Identifier | None = None
    effective_state_revision: int = 0
    global_control_revision: int = 0
    effective_sampling_rate: Decimal | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_type: Identifier
    input_hash: str
    logical_operation_id: UUID
    attempt_id: UUID
    lease_id: UUID
    route: str
    provider: Identifier
    model: Identifier
    attempt_index: int
    task_policy_version: Identifier
    model_policy_version: Identifier
    qualification_ref: Identifier
    routing_role: RoutingRole
    traffic_class: TrafficClass
    control_policy_version: Identifier
    output_policy_version: Identifier
    hard_output_tokens: int
    reserved_output_tokens: int
    deadline: float
    circuit_disposition: Literal["closed", "half_open"]


class ServiceDisposition(Contract):
    execution_outcome: Literal["completed", "partial", "failed"] = "completed"
    service_mode: Literal["full", "degraded"] = "full"
    degradation_reason: Identifier | None = None
    missing_capabilities: list[Identifier] = Field(default_factory=list)
