"""Private task data and small ref-only workflow state. No provider-specific schemas."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from career_agent.domain.schemas import Contract
from career_agent.runtime.contracts import Identifier

Prose = Annotated[str, StringConstraints(min_length=1, max_length=1200)]
Refs = Annotated[list[UUID], Field(max_length=60)]


class TaskType(StrEnum):
    EXTRACTION = "job_requirement_extraction"
    RESEARCH = "company_research_synthesis"
    FIT = "fit_analysis"
    TAILOR = "resume_tailoring"
    COMPRESS = "resume_compression"
    GREETING = "greeting_generation"
    INTERVIEW = "interview_preparation"


class ExtractedRequirement(Contract):
    evidence_span: Prose
    normalized_requirement: Prose
    requirement_kind: Literal["must", "nice_to_have", "responsibility", "preferred", "other"]
    category: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    skills: list[Prose] = Field(max_length=12)


class RequirementsOutput(Contract):
    requirements: list[ExtractedRequirement] = Field(min_length=1, max_length=40)


class ResearchEvidence(Contract):
    id: UUID
    evidence_version: Literal["research-evidence-v1"] = "research-evidence-v1"
    source_url: str = Field(max_length=2000)
    title: str = Field(max_length=500)
    content: str = Field(min_length=1, max_length=6000)
    retrieved_at: datetime
    provider: Identifier
    trust_level: Literal["untrusted_external"] = "untrusted_external"
    source_type: Literal["web"] = "web"


class ResearchConclusion(Contract):
    text: Prose
    evidence_refs: Refs = Field(min_length=1)


class ResearchOutput(Contract):
    locale: Literal["zh-CN"]
    conclusions: list[ResearchConclusion] = Field(max_length=12)
    unknowns: list[Prose] = Field(max_length=12)
    inference: list[ResearchConclusion] = Field(max_length=6)


class ResearchData(Contract):
    compatibility_versions: dict[str, str] | None = None
    evidence: list[ResearchEvidence] = Field(max_length=10)
    report: ResearchOutput
    trust_level: Literal["untrusted_external"] = "untrusted_external"
    mode: Literal["fixture", "live"]


class FitItem(Contract):
    requirement_ref: UUID
    status: Literal["matched", "partial", "no_evidence", "explicit_gap"]
    fact_refs: Refs
    explanation: Prose
    missing_evidence: str = Field(max_length=1000)


class FitOutput(Contract):
    locale: Literal["zh-CN"]
    items: list[FitItem] = Field(min_length=1, max_length=40)
    strong_matches: Refs
    partial_matches: Refs
    evidence_missing: Refs
    clear_gaps: Refs


class GreetingOutput(Contract):
    locale: Literal["zh-CN"]
    greeting_text: str = Field(min_length=1, max_length=500)
    fact_refs: Refs = Field(min_length=1)
    requirement_refs: Refs


class InterviewQuestion(Contract):
    question: Prose
    why_likely: Prose
    what_is_being_tested: Prose
    answer_outline: list[Prose] = Field(max_length=5)
    related_fact_refs: Refs
    # Foundation projects have no independent IDs; use selected profile entry indexes.
    related_project_refs: list[int] = Field(max_length=10)
    related_requirement_refs: Refs


class InterviewOutput(Contract):
    locale: Literal["zh-CN"]
    likely_topics: list[Prose] = Field(max_length=12)
    technical_questions: list[InterviewQuestion] = Field(max_length=8)
    project_deep_dive_questions: list[InterviewQuestion] = Field(max_length=6)
    behavioral_questions: list[InterviewQuestion] = Field(max_length=6)
    company_specific_questions: list[InterviewQuestion] = Field(max_length=6)
    knowledge_gaps: list[Prose] = Field(max_length=12)
    questions_to_ask_interviewer: list[Prose] = Field(max_length=8)


class LayoutBudget(Contract):
    max_projects: int = 3
    max_bullets_per_project: int = 3
    max_experience_bullets: int = 6
    preferred_bullet_length: int = 70
    max_bullet_length: int = 180
    max_total_characters: int = 1800
    target_page_count: Literal[1] = 1
    locale: Literal["zh-CN"] = "zh-CN"


class RunLimits(Contract):
    max_model_calls: int = Field(default=12, ge=0, le=20)
    max_web_search_calls: int = Field(default=2, ge=0, le=2)
    max_input_tokens: int = Field(default=200000, ge=0, le=500000)
    max_output_tokens: int = Field(default=40000, ge=0, le=80000)
    max_estimated_cost: Decimal = Field(default=Decimal("1"), ge=0, le=5)
    max_semantic_resume_compressions: int = Field(default=1, ge=0, le=1)


class Accounting(Contract):
    model_calls: int = 0
    search_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: Decimal = Decimal("0")
    budget_reserved_usd: Decimal = Decimal("0")
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    actual_billed_cost_usd: Decimal | None = None
    unknown_usage_attempts: int = 0
    semantic_compressions: int = 0

    @property
    def budget_consumed_usd(self) -> Decimal:
        return self.estimated_cost + self.budget_reserved_usd


Target = Literal["fit_analysis", "resume_tailoring", "greeting_generation", "interview_preparation"]


class ResumeBinding(Contract):
    resume_revision_id: UUID | None = None
    output_of: Literal["resume_tailoring"] | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "ResumeBinding":
        if (self.resume_revision_id is None) == (self.output_of is None):
            raise ValueError("exactly one resume binding required")
        return self


class TargetOutcome(Contract):
    status: Literal["completed", "failed", "blocked", "pending"] = "pending"
    artifact_id: UUID | None = None
    reason: Identifier | None = None


class PlanNode(Contract):
    name: Identifier
    status: Literal["executed", "reused", "skipped", "failed", "blocked"]
    reason: Identifier | None = None


class WorkflowOutcome(Contract):
    status: Literal["completed", "partial", "failed", "needs_input", "decision_required"]
    reason: Identifier | None = None
    targets: dict[Target, TargetOutcome]
    nodes: list[PlanNode] = Field(default_factory=list)
    gate_policy_version: Literal["fit_gate_policy_v1"] | None = None

    @model_validator(mode="after")
    def consistent_terminal(self) -> "WorkflowOutcome":
        states = [v.status for v in self.targets.values()]
        if not states:
            raise ValueError("outcome requires targets")
        done = states.count("completed")
        if any(
            (v.status == "completed") != (v.artifact_id is not None) for v in self.targets.values()
        ):
            raise ValueError("completed target requires an artifact")
        valid = {
            "completed": done == len(states),
            "partial": 0 < done < len(states) and "pending" not in states,
            "failed": done == 0 and "pending" not in states,
            "needs_input": all(s == "pending" for s in states),
            "decision_required": "pending" in states
            and all(s in {"pending", "completed"} for s in states),
        }
        if not valid[self.status]:
            raise ValueError("inconsistent workflow outcome")
        return self


class TargetArtifact(Contract):
    compatibility_versions: dict[str, str] | None = None
    target: Target
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    result_id: UUID | None = None
    resume_revision_id: UUID | None = None
    render_artifact_id: UUID | None = None
    source_resume_revision_id: UUID | None = None


class WorkflowRequest(Contract):
    job_revision_id: UUID
    profile_id: UUID
    mode: Literal["fixture", "live"] = "fixture"
    limits: RunLimits = Field(default_factory=RunLimits)
    targets: list[Literal["fit_analysis", "resume_tailoring", "greeting_generation"]] = Field(
        default=["fit_analysis", "resume_tailoring", "greeting_generation"],
        min_length=1,
        max_length=3,
    )
    resume_revision_id: UUID | None = None
    bindings: dict[Literal["resume_tailoring", "greeting_generation"], ResumeBinding] = Field(
        default_factory=dict
    )
    fit_gate: Literal["informational", "gate_downstream"] = "informational"
    force_research_refresh: bool = False

    @model_validator(mode="after")
    def valid_targets(self) -> "WorkflowRequest":
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("duplicate targets")
        for target, binding in self.bindings.items():
            if target not in self.targets or (
                binding.output_of
                and (target != "greeting_generation" or "resume_tailoring" not in self.targets)
            ):
                raise ValueError("invalid target binding")
        return self

    application_package_id: UUID | None = None
    star_story_ids: Refs = Field(default_factory=list)
    knowledge_note_ids: Refs = Field(default_factory=list)


class WorkflowState(Contract):
    run_id: UUID
    workflow: Literal["prepare_application", "prepare_interview"]
    mode: Literal["fixture", "live"] = "fixture"
    workflow_version: Literal["preparation-v1", "preparation-v2"] = "preparation-v2"
    job_revision_id: UUID
    profile_id: UUID
    profile_revision: int | None = Field(default=None, ge=1)
    job_id: UUID | None = None
    job_revision: int | None = Field(default=None, ge=1)
    requested_outputs: list[Identifier]
    current_node: Identifier = "validate_inputs"
    step_count: int = 0
    status: Literal[
        "running", "completed", "partial", "failed", "needs_input", "decision_required"
    ] = "running"
    requirement_refs: Refs = Field(default_factory=list)
    evidence_refs: Refs = Field(default_factory=list)
    research_report_id: UUID | None = None
    fit_analysis_id: UUID | None = None
    resume_variant_id: UUID | None = None
    resume_variant_revision: int | None = None
    render_report_id: UUID | None = None
    greeting_id: UUID | None = None
    interview_prep_id: UUID | None = None
    warnings: list[Identifier] = Field(default_factory=list)
    errors: list[Identifier] = Field(default_factory=list)
    usage: Accounting = Field(default_factory=Accounting)
    limits: RunLimits = Field(default_factory=RunLimits)
    stop_reason: Identifier | None = None
    outcome: WorkflowOutcome | None = None
    bindings: dict[str, ResumeBinding] = Field(default_factory=dict)


class PrivateResult(Contract):
    kind: Literal["fit", "greeting", "interview", "package", "target"]
    output: FitOutput | GreetingOutput | InterviewOutput | WorkflowState | TargetArtifact

    @model_validator(mode="after")
    def consistent_kind(self) -> "PrivateResult":
        expected = {
            "fit": FitOutput,
            "greeting": GreetingOutput,
            "interview": InterviewOutput,
            "package": WorkflowState,
            "target": TargetArtifact,
        }
        if not isinstance(self.output, expected[self.kind]):
            raise ValueError("result kind and schema mismatch")
        return self
