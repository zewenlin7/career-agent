"""Private interview content contracts, separate from operational trace metadata."""

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from career_agent.domain.schemas import Contract, InterviewEntry, InterviewNoteData, Text
from career_agent.preparation.contracts import Accounting, RunLimits


class InterviewLimits(RunLimits):
    max_model_calls: int = Field(default=100, ge=0, le=1000)
    max_input_tokens: int = Field(default=2000000, ge=0, le=10000000)
    max_output_tokens: int = Field(default=200000, ge=0, le=2000000)
    max_estimated_cost: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    max_active_seconds: float = Field(default=3600, gt=0, le=14400)


class InterviewUsage(Accounting):
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cached_unknown_calls: int = 0
    cache_write_unknown_calls: int = 0
    reasoning_unknown_calls: int = 0
    active_seconds: float = 0
    reserved_seconds: float = 0


class ContextBinding(Contract):
    profile_id: UUID
    job_revision_id: UUID
    resume_revision_id: UUID
    interview_preparation_id: UUID | None = None


class FrozenContext(Contract):
    schema_version: Literal["interview-context-v1"] = "interview-context-v1"
    binding: ContextBinding
    profile_revision: int
    job_id: UUID
    job_revision: int
    fact_snapshot: dict[UUID, int]
    # Minimized, verified facts and exact domain snapshots, never runtime trace bodies.
    data: dict[str, Any]


class MockPolicy(Contract):
    mode: Literal["quick", "standard", "long", "custom"] = "quick"
    primary_target: int | None = Field(default=None, ge=1, le=8)
    followup_max: int | None = Field(default=None, ge=0, le=5)
    policy_version: Literal["mock-policy-v1"] = "mock-policy-v1"

    @model_validator(mode="after")
    def quotas(self) -> "MockPolicy":
        fixed = {"quick": (3, 1), "standard": (5, 3), "long": (8, 5)}
        if self.mode in fixed:
            p, f = fixed[self.mode]
            if self.primary_target not in {None, p} or self.followup_max not in {None, f}:
                raise ValueError("fixed_mode_quota")
            self.primary_target, self.followup_max = p, f
        if self.primary_target is None or self.followup_max is None:
            raise ValueError("custom_quota_required")
        if self.followup_max > self.primary_target:
            raise ValueError("followup_exceeds_primary")
        return self


class MockCreate(Contract):
    context: ContextBinding
    focus: Literal["technical", "project", "behavioral", "company_specific", "mixed"] = "mixed"
    policy: MockPolicy = Field(default_factory=MockPolicy)
    mode: Literal["fixture", "live"] = "fixture"


class Continuation(Contract):
    expected_revision: int = Field(ge=1)
    request_id: UUID


class AnswerSubmit(Continuation):
    pending_question_id: UUID
    answer: Text


class TurnOutput(Contract):
    kind: Literal["primary", "follow_up"]
    question: str = Field(min_length=1, max_length=2000)
    question_type: Literal["technical", "project", "behavioral", "company_specific"]
    topic: str = Field(min_length=1, max_length=200)
    primary_entry_id: UUID | None
    requirement_refs: list[UUID] = Field(max_length=30)
    fact_refs: list[UUID] = Field(max_length=30)
    reason_code: Literal["next_primary", "clarify_answer"]


class SourceSnapshot(Contract):
    schema_version: Literal["interview-source-v1"] = "interview-source-v1"
    source_kind: Literal["actual", "mock"]
    interview_id: UUID
    content_revision: int
    entries: list[InterviewEntry] = Field(max_length=500)
    notes: list[InterviewNoteData]
    context: FrozenContext | None = None
    completion_type: Literal["target_reached", "user_ended_early"] | None = None


class DebriefCreate(Contract):
    source_kind: Literal["actual", "mock"]
    interview_id: UUID
    expected_source_revision: int = Field(ge=1)
    question_analysis: Literal["none", "single", "all"] = "none"
    overall_analysis: bool = False
    primary_entry_id: UUID | None = None
    context: ContextBinding | None = None
    mode: Literal["fixture", "live"] = "fixture"

    @model_validator(mode="after")
    def targets(self) -> "DebriefCreate":
        if self.question_analysis == "none" and not self.overall_analysis:
            raise ValueError("empty_targets")
        if (self.question_analysis == "single") != (self.primary_entry_id is not None):
            raise ValueError("single_group_binding_required")
        return self


class Finding(Contract):
    content: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[UUID] = Field(min_length=1, max_length=500)


class ExampleAnswer(Contract):
    content: str = Field(min_length=1, max_length=4000)
    grounded_fact_refs: list[UUID] = Field(min_length=1, max_length=60)


class QuestionGroupEvaluation(Contract):
    group_ref: UUID
    strengths: list[Finding] = Field(max_length=8)
    issues: list[Finding] = Field(max_length=8)
    knowledge_gap_hypotheses: list[Finding] = Field(max_length=8)
    improvement_suggestions: list[Finding] = Field(max_length=8)
    example_answer: ExampleAnswer | None = None


class OverallEvaluation(Contract):
    strengths: list[Finding] = Field(max_length=12)
    recurring_issues: list[Finding] = Field(max_length=12)
    knowledge_gap_hypotheses: list[Finding] = Field(max_length=12)
    practice_recommendations: list[Finding] = Field(max_length=12)
    knowledge_candidates: list[Finding] = Field(max_length=12)


class EvaluationData(Contract):
    group: QuestionGroupEvaluation | None = None
    overall: OverallEvaluation | None = None


class EventData(Contract):
    event: Literal[
        "group_started",
        "group_retrying",
        "group_completed",
        "group_failed",
        "overall_started",
        "overall_retrying",
        "overall_completed",
        "overall_failed",
        "run_completed",
        "run_partial",
        "run_failed",
    ]
    artifact_id: UUID | None = None
    group_index: int | None = None
    display_section: Literal["questions", "overall", "run"]
    display_order: int
    reason_code: str | None = None
    message: str | None = None
