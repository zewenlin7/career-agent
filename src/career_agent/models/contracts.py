from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from career_agent.domain.schemas import Contract
from career_agent.runtime.contracts import Budget, Identifier, Usage, VersionMetadata


class ModelTier(StrEnum):
    CHEAP = "cheap"
    STRONG = "strong"
    PREMIUM = "premium"


class PrivacyClass(StrEnum):
    SYNTHETIC = "synthetic"
    PRIVATE = "private"


class Complexity(StrEnum):
    BASIC = "basic"
    STANDARD = "standard"
    HIGH = "high"


class ModelRequestContext(Contract):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    task_type: Identifier
    workflow: Identifier | None = None
    complexity: Complexity = Complexity.STANDARD
    required_capabilities: frozenset[Identifier] = frozenset({"structured_output"})
    privacy_class: PrivacyClass = PrivacyClass.SYNTHETIC
    budget_remaining: Budget = Field(default_factory=Budget)
    output_schema: type[BaseModel]
    max_output_tokens: int = Field(default=512, ge=1, le=32768)


class TaskSpec(Contract):
    # In-memory canonical task data, never automatically written to runtime trace.
    instruction: str = Field(min_length=1, max_length=20000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    prompt_version: Identifier | None = None
    input_schema_version: Identifier | None = None
    output_schema_version: Identifier | None = None


class ModelCandidate(Contract):
    provider: Identifier
    model: Identifier
    tier: ModelTier
    capabilities: frozenset[Identifier]
    allowed_privacy: frozenset[PrivacyClass]
    input_cost_per_million: Decimal = Field(ge=0)
    output_cost_per_million: Decimal = Field(ge=0)
    pricing_version: Identifier | None = None


class ProviderResponse(Contract):
    output: dict[str, Any]
    usage: Usage
    finish_reason: Identifier


class ModelResult(Contract):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    validated_output: BaseModel
    provider: Identifier
    model: Identifier
    usage: Usage
    latency_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    finish_reason: Identifier
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    schema_validation_state: Literal["valid"]
    versions: VersionMetadata
    model_policy_version: Identifier


class ProviderAdapter(Protocol):
    async def generate(
        self,
        candidate: ModelCandidate,
        context: ModelRequestContext,
        task: TaskSpec,
    ) -> ProviderResponse: ...


class ModelGatewayError(Exception):
    """Only stable error codes may cross the provider boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
