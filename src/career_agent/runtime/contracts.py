from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from career_agent.domain.schemas import Contract

# Metadata identifiers only: never prose, prompts, paths, URLs or model reasoning.
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]


class VersionMetadata(Contract):
    workflow_version: Identifier | None = None
    prompt_version: Identifier | None = None
    input_schema_version: Identifier | None = None
    output_schema_version: Identifier | None = None
    tool_name: Identifier | None = None
    tool_version: Identifier | None = None
    model_policy_version: Identifier | None = None
    provider: Identifier | None = None
    model: Identifier | None = None
    resume_template_version: Identifier | None = None
    evaluator_version: Identifier | None = None


class Usage(Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
    pricing_version: Identifier | None = None


class Budget(Contract):
    token_limit: int | None = Field(default=None, ge=0)
    cost_limit: Decimal | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
