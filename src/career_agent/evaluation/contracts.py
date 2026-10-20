"""Versioned evaluation data. Private snapshots are never operational trace bodies."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from career_agent.domain.schemas import Contract
from career_agent.models.control.contracts import CapacityFeedback
from career_agent.models.control.scenario import ControlScenario
from career_agent.preparation.contracts import RunLimits
from career_agent.runtime.contracts import Usage


class Entrypoint(Contract):
    kind: Literal["component", "business_workflow", "agent_goal"]
    component_kind: Literal["model_task", "deterministic_operation", "business_action"] | None = (
        None
    )
    name: str = Field(min_length=1, max_length=128)


class Expectation(Contract):
    check_id: str
    category: Literal["correctness", "quality", "trajectory", "reliability", "efficiency"] = (
        "correctness"
    )
    tier: int = Field(default=0, ge=0, le=3)
    operator: Literal["equals", "contains", "absent", "max", "min", "valid"] = "valid"
    path: str = "status"
    value: Any = None
    material: bool = True


class Fault(Contract):
    capacity_feedback: CapacityFeedback | None = None
    operation: str
    attempt: int = Field(ge=1)
    kind: Literal[
        "timeout",
        "429",
        "5xx",
        "malformed_output",
        "schema_failure",
        "tool_failure",
        "budget_exhaustion",
        "cas_conflict",
    ]
    expected_recovery: str | None = None


class FaultPlan(Contract):
    version: Literal["fault-plan-v1"] = "fault-plan-v1"
    faults: list[Fault] = Field(default_factory=list, max_length=30)


class EvalCase(Contract):
    control_scenario: ControlScenario = Field(default_factory=ControlScenario)
    schema_version: Literal["eval-case-v1"] = "eval-case-v1"
    case_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,128}$")
    case_version: int = Field(ge=1)
    entrypoint: Entrypoint
    tags: list[str] = Field(default_factory=list)
    source_type: Literal["synthetic", "sanitized", "private_capture"] = "synthetic"
    source_snapshot: dict[str, Any]
    model_input: dict[str, Any] | None = None
    frozen_external_observations: dict[str, Any] = Field(default_factory=dict)
    evaluation_clock: datetime
    expectations: list[Expectation] = Field(min_length=1)
    fault_plan: FaultPlan = Field(default_factory=FaultPlan)
    origin_provenance: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None


class CaseRef(Contract):
    case_id: str
    case_version: int = Field(ge=1)


class EvalSuite(Contract):
    suite_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,128}$")
    version: int = Field(ge=1)
    schema_version: Literal["eval-suite-v1"] = "eval-suite-v1"
    members: list[CaseRef] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_members(self) -> "EvalSuite":
        if len({(x.case_id, x.case_version) for x in self.members}) != len(self.members):
            raise ValueError("duplicate_suite_member")
        return self


class CandidateConfig(Contract):
    schema_version: Literal["candidate-v1"] = "candidate-v1"
    code_revision: str
    code_hash: str
    prompts: dict[str, dict[str, Any]]
    schemas: dict[str, str]
    components: dict[str, str]
    model_policy: dict[str, Any]
    validators: dict[str, str]
    execution_settings: dict[str, Any] = Field(default_factory=dict)
    config_hash: str | None = None


class EvalCheckResult(Contract):
    check_id: str
    check_version: str = "eval-check-v1"
    category: str
    status: Literal["pass", "fail", "skipped", "error"]
    reason_code: str
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tier: int = Field(default=0, ge=0, le=3)
    material: bool = True


class TrialResult(Contract):
    status: Literal["completed", "failed", "case_incompatible", "cancelled"]
    checks: list[EvalCheckResult] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: int = Field(default=0, ge=0)
    reason_code: str | None = None


class OperationSnapshot(Contract):
    schema_version: Literal["operation-invocation-v1"] = "operation-invocation-v1"
    operation_id: UUID = Field(default_factory=uuid4)
    kind: Literal["model_task", "deterministic_operation", "business_action"]
    name: str
    version: str
    input_snapshot: dict[str, Any]
    input_hash: str
    output: dict[str, Any] | None = None
    output_ref: UUID | None = None
    parent_run_id: UUID | None = None
    parent_step_id: UUID | None = None
    accepted_model_call_id: UUID | None = None
    logical_operation_id: UUID | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    injected_fault: str | None = None


class EvalLimits(RunLimits):
    max_model_calls: int = Field(default=200, ge=0, le=5000)
    max_web_search_calls: int = Field(default=100, ge=0, le=500)
    max_input_tokens: int = Field(default=5000000, ge=0, le=50000000)
    max_output_tokens: int = Field(default=1000000, ge=0, le=5000000)
    max_estimated_cost: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    max_active_seconds: float = Field(default=600, gt=0, le=3600)


class EvalRunRequest(Contract):
    suite_id: str
    suite_version: int = Field(ge=1)
    trials: int = Field(default=1, ge=1, le=5)
    mode: Literal["candidate_replay", "origin_reexecution"] = "candidate_replay"
    explicit_diagnostic: bool = False
    max_concurrent_trials: int = Field(default=2, ge=1, le=8)
    limits: EvalLimits = Field(default_factory=EvalLimits)
    per_trial_limits: RunLimits = Field(default_factory=RunLimits)


SamplingReason = Literal[
    "random_sample",
    "forced_user_feedback",
    "forced_deterministic_warning",
    "forced_new_version",
    "forced_manual",
]


class JudgeSamplingPolicy(Contract):
    version: str = "judge-sampling-v1"
    default_rate: Decimal = Field(default=Decimal("0.1"), ge=0, le=1)
    per_task: dict[str, Decimal] = Field(default_factory=dict)
    force_rules: list[SamplingReason] = Field(
        default_factory=lambda: cast(
            list[SamplingReason],
            [
                "forced_user_feedback",
                "forced_deterministic_warning",
                "forced_manual",
            ],
        )
    )

    @model_validator(mode="after")
    def rates(self) -> "JudgeSamplingPolicy":
        if any(not 0 <= x <= 1 for x in self.per_task.values()):
            raise ValueError("invalid_sampling_rate")
        return self


class Subject(Contract):
    subject_id: UUID
    task_type: str
    accepted_model_call_id: UUID | None = None
    operation_id: UUID | None = None
    origin: Literal["business", "evaluation"] = "business"


class SamplingDecision(Contract):
    effective_control_revision: int | None = None
    subject: Subject
    policy_version: str
    effective_rate: Decimal
    sampled: bool
    reason: SamplingReason
    decision_key: str
    population: Literal["random", "targeted"]


class Criterion(Contract):
    criterion: str
    rating: Literal["pass", "minor_issue", "major_issue", "insufficient_evidence"]
    confidence: Literal["low", "medium", "high"]
    uncertainty_reasons: list[str]
    reason: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str]


class JudgeOutput(Contract):
    criteria: list[Criterion] = Field(min_length=1, max_length=30)


class JudgeSpec(Contract):
    name: str = "task-quality"
    version: str = "task-quality-v1"
    target: str
    rubric_version: str = "quality-rubric-v1"
    criteria: list[str] = Field(default_factory=lambda: ["relevance", "clarity", "specificity"])
    prompt_version: str
    prompt_hash: str
    output_schema_version: str = "judge-output-v1"
    model_policy_version: str


class Feedback(Contract):
    subject: Subject
    vote: Literal["thumbs_up", "thumbs_down"]
    reason: Literal[
        "incorrect_or_unsupported",
        "missed_the_point",
        "not_specific_enough",
        "poor_expression",
        "too_verbose_or_too_short",
        "personal_preference",
        "wanted_an_alternative",
        "other",
        "unspecified",
    ] = "unspecified"


class Annotation(Contract):
    subject: Subject
    schema_version: str = "human-annotation-v1"
    rubric_version: str = "quality-rubric-v1"
    annotator: str = Field(min_length=1, max_length=100)
    population: Literal["random", "targeted"]
    criteria: list[Criterion]
    blind: Literal[True] = True
    supersedes_annotation_id: UUID | None = None


class CapturePayload(Contract):
    schema_version: str = "capture-v1"
    subject: Subject
    source_snapshot: dict[str, Any]
    model_input: dict[str, Any] | None = None
    external_observations: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any]
    provenance: dict[str, Any]
    evaluation_refs: list[UUID] = Field(default_factory=list)
    privacy_class: Literal["private", "synthetic"] = "private"
    content_hash: str | None = None


class ComparisonPolicy(Contract):
    version: Literal["comparison-priority-v2"] = "comparison-priority-v2"
    minimum_trials: int = Field(default=1, ge=1)
    efficiency_threshold: Decimal | None = None
    efficiency_blocking: bool = False
