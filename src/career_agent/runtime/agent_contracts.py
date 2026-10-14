"""Versioned control data; goal prose lives only in the private Goal record."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from career_agent.domain.schemas import Contract
from career_agent.preparation.contracts import Accounting, ResumeBinding, Target, TargetOutcome
from career_agent.runtime.contracts import Identifier, Usage

AppTarget = Literal["fit_analysis", "resume_tailoring", "greeting_generation"]
ActionName = Literal["prepare_application", "prepare_interview"]
Phase = Literal[
    "ready",
    "planning",
    "executing",
    "waiting_input",
    "waiting_decision",
    "completed",
    "partial",
    "failed",
    "cancelled",
]


class Bindings(Contract):
    profile_id: UUID
    job_revision_id: UUID
    resume_revision_id: UUID | None = None
    application_package_id: UUID | None = None


class AuthorizedScope(Contract):
    targets: list[Target] = Field(min_length=1, max_length=4)
    fit_gate: Literal["informational", "gate_downstream"] = "informational"
    allow_tailored_greeting: bool = False

    @model_validator(mode="after")
    def unique(self) -> "AuthorizedScope":
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("duplicate targets")
        return self


class RuntimeLimits(Contract):
    max_steps: int = Field(default=32, ge=1, le=100)
    max_total_business_actions: int = Field(default=8, ge=0, le=8)
    max_model_calls: int = Field(default=12, ge=0, le=20)
    max_tool_calls: int = Field(default=16, ge=0, le=32)
    max_web_search_calls: int = Field(default=2, ge=0, le=2)
    max_replans: int = Field(default=2, ge=0, le=2)
    max_input_tokens: int = Field(default=200000, ge=0, le=500000)
    max_output_tokens: int = Field(default=40000, ge=0, le=80000)
    max_estimated_cost: Decimal = Field(default=Decimal("1"), ge=0, le=5)
    max_active_seconds: float = Field(default=600, gt=0, le=3600)


class RuntimeUsage(Accounting):
    steps: int = 0
    business_actions: int = 0
    tool_calls: int = 0
    active_seconds: float = 0


class ActionArgs(Contract):
    targets: list[AppTarget] = Field(default_factory=list, max_length=3)
    resume_revision_id: UUID | None = None
    bindings: dict[Literal["resume_tailoring", "greeting_generation"], ResumeBinding] = Field(
        default_factory=dict
    )
    application_package_id: UUID | None = None
    package_from_action: UUID | None = None


class PlanAction(Contract):
    action_id: UUID
    name: ActionName
    # None is retained for reading legacy checkpoints; execution rejects unpinned actions.
    action_version: Identifier | None = None
    args: ActionArgs
    dependencies: list[UUID] = Field(default_factory=list, max_length=3)


class PlanProposal(Contract):
    plan_version: Literal["agent-plan-v1", "agent-plan-v2"] = "agent-plan-v2"
    requested_targets: list[Target] = Field(min_length=1, max_length=4)
    actions: list[PlanAction] = Field(max_length=4)
    bindings: Bindings
    policies: AuthorizedScope
    missing_inputs: list[
        Literal[
            "resume_selection_required",
            "application_package_required",
            "goal_clarification_required",
        ]
    ] = Field(default_factory=list, max_length=3)
    reason_code: Literal["goal_routed", "input_required", "authorized_path_changed"] = "goal_routed"
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=12)


class ActionObservation(Contract):
    schema_version: Literal["action-observation-v1"] = "action-observation-v1"
    action_id: UUID
    disposition: Literal[
        "executed", "reused", "skipped", "failed", "blocked", "needs_input", "decision_required"
    ]
    reason_code: Identifier | None = None
    child_run_id: UUID | None = None
    package_id: UUID | None = None
    targets: dict[Target, TargetOutcome] = Field(default_factory=dict)
    evidence_refs: list[UUID] = Field(default_factory=list)
    guardrails: Literal["passed", "failed", "not_run"] = "not_run"


class ActionProgress(Contract):
    action: PlanAction
    status: Literal["pending", "completed", "failed", "blocked", "waiting"] = "pending"
    observation_id: UUID | None = None
    package_id: UUID | None = None
    child_run_id: UUID | None = None
    fingerprint: str | None = None


class AgentProgress(Contract):
    requested_targets: dict[Target, TargetOutcome] = Field(default_factory=dict)
    actions: dict[UUID, ActionProgress] = Field(default_factory=dict)


class AgentState(Contract):
    schema_version: Literal["agent-state-v1"] = "agent-state-v1"
    run_id: UUID
    goal_id: UUID
    state_revision: int = 0
    plan_revision: int = 0
    bindings: Bindings
    original_scope: AuthorizedScope
    scope: AuthorizedScope
    mode: Literal["fixture", "live"] = "fixture"
    phase: Phase = "ready"
    progress: AgentProgress = Field(default_factory=AgentProgress)
    current_action_id: UUID | None = None
    previous_observation_id: UUID | None = None
    pending_reason: Identifier | None = None
    replan_count: int = 0
    needs_plan: bool = True
    gate_approved: bool = False
    limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    usage: RuntimeUsage = Field(default_factory=RuntimeUsage)
    dispatch_reservation: Usage | None = None
    attempted_fingerprints: list[str] = Field(default_factory=list)
    plan_fingerprints: list[str] = Field(default_factory=list)
    # Private exact fact snapshot for context-change detection, not full statements.
    fact_snapshot: dict[UUID, int] = Field(default_factory=dict)


class AgentCreate(Contract):
    goal: str = Field(min_length=1, max_length=4000)
    bindings: Bindings
    authorized_scope: AuthorizedScope
    limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    mode: Literal["fixture", "live"] = "fixture"
    action_slice: int = Field(default=4, ge=1, le=8)


class AgentResume(Contract):
    expected_checkpoint_revision: int = Field(ge=1)
    request_id: UUID
    resume_revision_id: UUID | None = None
    application_package_id: UUID | None = None
    authorized_targets: list[Target] | None = Field(default=None, min_length=1, max_length=4)
    decision: Literal["continue", "cancel"] | None = None
    action_slice: int = Field(default=4, ge=1, le=8)


class StateTransition(Contract):
    before_revision: int
    after_revision: int
    decision: Literal["continue", "replan", "wait", "finish", "dispatch"]
    reason_code: Identifier | None = None
