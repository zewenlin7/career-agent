import time
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError

from career_agent.models.contracts import (
    Complexity,
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ModelResult,
    ModelTier,
    ProviderAdapter,
    TaskSpec,
)
from career_agent.models.diagnostics import validation_issues
from career_agent.models.prompts import PromptRegistry, application_prompts
from career_agent.runtime.contracts import OutputDiagnostic, VersionMetadata


@dataclass(frozen=True)
class ModelPolicy:
    """Static task routing. No intent classification or Agent State dependency."""

    version: str
    task_tiers: dict[str, ModelTier]

    def select(
        self, context: ModelRequestContext, registry: list[ModelCandidate]
    ) -> ModelCandidate:
        tier = self.task_tiers.get(context.task_type, ModelTier.STRONG)
        if tier == ModelTier.CHEAP and context.complexity == Complexity.HIGH:
            tier = ModelTier.STRONG
        budget = context.budget_remaining
        if budget.token_limit is not None and budget.token_limit < context.max_output_tokens:
            raise ModelGatewayError("insufficient_token_budget")
        candidates = [
            candidate
            for candidate in registry
            if candidate.tier == tier
            and context.required_capabilities <= candidate.capabilities
            and context.privacy_class in candidate.allowed_privacy
        ]
        # Deterministic choice within the chosen tier; never silently upgrade to premium.
        candidates.sort(
            key=lambda c: (
                c.input_cost_per_million + c.output_cost_per_million,
                c.provider,
                c.model,
            )
        )
        for candidate in candidates:
            minimum = (
                candidate.output_cost_per_million * context.max_output_tokens / Decimal(1000000)
            )
            if budget.cost_limit is None or minimum <= budget.cost_limit:
                return candidate
        raise ModelGatewayError("no_eligible_model")


class ModelGateway:
    def __init__(
        self,
        registry: list[ModelCandidate],
        policy: ModelPolicy,
        adapters: dict[str, ProviderAdapter],
        prompts: PromptRegistry | None = None,
    ) -> None:
        if len({(c.provider, c.model) for c in registry}) != len(registry):
            raise ValueError("duplicate model candidate")
        if any(c.provider not in adapters for c in registry):
            raise ValueError("missing provider adapter")
        self.registry, self.policy, self.adapters = registry, policy, adapters
        self.prompts = prompts if prompts is not None else application_prompts()

    def trace_metadata(self, context: ModelRequestContext, task: TaskSpec) -> VersionMetadata:
        versions = self.prompts.trace_metadata(context, task)
        candidate = self.policy.select(context, self.registry)
        return versions.model_copy(
            update={
                "model_policy_version": self.policy.version,
                "provider": candidate.provider,
                "model": candidate.model,
            }
        )

    async def generate(self, context: ModelRequestContext, task: TaskSpec) -> ModelResult:
        versions = self.trace_metadata(context, task)
        candidate = self.policy.select(context, self.registry)
        started = time.perf_counter()
        try:
            response = await self.adapters[candidate.provider].generate(candidate, context, task)
        except ModelGatewayError:
            raise
        except Exception:
            raise ModelGatewayError("provider_error") from None
        try:
            output = context.output_schema.model_validate(response.output)
        except ValidationError as exc:
            diagnostic = response.diagnostic or OutputDiagnostic()
            diagnostic.failure_kind = "output_validation_failed"
            diagnostic.validation_issues = validation_issues(exc, context.output_schema)
            raise ModelGatewayError(
                "output_validation_failed", usage=response.usage, diagnostic=diagnostic
            ) from None
        return ModelResult(
            validated_output=output,
            provider=candidate.provider,
            model=candidate.model,
            usage=response.usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
            attempts=1,
            finish_reason=response.finish_reason,
            estimated_cost=response.usage.estimated_cost,
            schema_validation_state="valid",
            model_policy_version=self.policy.version,
            versions=versions.model_copy(update={"output_diagnostic": response.diagnostic}),
        )
