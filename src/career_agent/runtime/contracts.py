from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from career_agent.domain.schemas import Contract

# Metadata identifiers only: never prose, prompts, paths, URLs or model reasoning.
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]


class ValidationIssue(Contract):
    loc: list[str | int] = Field(default_factory=list, max_length=12)
    type: Identifier
    message: Literal[
        "canonical schema validation failed",
        "duplicate fact references",
        "short_text must be shorter",
        "control characters are not supported",
        "duplicate IDs or section names",
        "at least one required factual item is needed",
        "document too large",
    ] = "canonical schema validation failed"


class OutputDiagnostic(Contract):
    failure_kind: (
        Literal[
            "provider_timeout",
            "provider_incomplete",
            "provider_refusal",
            "structured_output_invalid",
            "output_validation_failed",
            "output_guardrail_failed",
        ]
        | None
    ) = None
    request_timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    timeout_policy_version: Identifier | None = None
    timeout_phase: Literal["connect", "read", "write", "pool", "unknown"] | None = None
    response_id: Identifier | None = None
    actual_model: Identifier | None = None
    response_status: Literal[
        "completed", "incomplete", "failed", "cancelled", "queued", "in_progress", "unknown"
    ] = "unknown"
    incomplete_reason: Literal["max_output_tokens", "content_filter"] | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list, max_length=20)
    guardrail_code: Identifier | None = None


class VersionMetadata(Contract):
    workflow_version: Identifier | None = None
    prompt_version: Identifier | None = None
    prompt_hash: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] | None = None
    input_schema_version: Identifier | None = None
    output_schema_version: Identifier | None = None
    action_name: Identifier | None = None
    action_version: Identifier | None = None
    tool_name: Identifier | None = None
    tool_version: Identifier | None = None
    model_policy_version: Identifier | None = None
    provider: Identifier | None = None
    model: Identifier | None = None
    resume_template_version: Identifier | None = None
    evaluator_version: Identifier | None = None
    retry_reason: Identifier | None = None
    repair_reason: Identifier | None = None
    output_diagnostic: OutputDiagnostic | None = None


class Usage(Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    actual_model: Identifier | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    # Cost estimates are never provider invoices. Reserved amounts have unknown usage/cost.
    budget_reserved_usd: Decimal = Field(default=Decimal(0), ge=0)
    reserved_input_tokens: int = Field(default=0, ge=0)
    reserved_output_tokens: int = Field(default=0, ge=0)
    actual_billed_cost_usd: Decimal | None = Field(default=None, ge=0)
    billing_tier: Literal["unknown"] = "unknown"
    search_calls: int = Field(default=0, ge=0)
    credits_used: Decimal | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
    pricing_version: Identifier | None = None
    measurement: Literal["reported", "estimated", "unknown"] = "unknown"


class Budget(Contract):
    token_limit: int | None = Field(default=None, ge=0)
    cost_limit: Decimal | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
