"""Deterministic adapter-boundary faults. Recovery remains production policy's job."""

from collections import defaultdict
from typing import Any

from career_agent.evaluation.contracts import Fault, FaultPlan
from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ProviderAdapter,
    ProviderResponse,
    TaskSpec,
)
from career_agent.preparation.research import SearchInput, SearchResult
from career_agent.runtime.contracts import Usage


class FaultController:
    def __init__(self, plan: FaultPlan) -> None:
        self.plan = plan
        self.attempts: dict[str, int] = defaultdict(int)
        self.events: list[dict[str, Any]] = []

    def next(self, operation: str) -> Fault | None:
        self.attempts[operation] += 1
        fault = next(
            (
                x
                for x in self.plan.faults
                if x.operation == operation and x.attempt == self.attempts[operation]
            ),
            None,
        )
        if fault:
            self.events.append(
                {
                    "operation": operation,
                    "attempt": self.attempts[operation],
                    "injected_fault": fault.kind,
                    "fault_plan_version": self.plan.version,
                }
            )
        return fault


class FaultProvider:
    def __init__(self, inner: ProviderAdapter, controller: FaultController) -> None:
        self.inner, self.controller = inner, controller

    async def generate(
        self, candidate: ModelCandidate, context: ModelRequestContext, task: TaskSpec
    ) -> ProviderResponse:
        fault = self.controller.next(context.task_type)
        if fault:
            if fault.kind in {"malformed_output", "schema_failure"}:
                return ProviderResponse(
                    output={},
                    usage=Usage(input_tokens=1, output_tokens=1, estimated_cost=0),
                    finish_reason="stop",
                )
            codes = {
                "timeout": "provider_timeout",
                "429": "provider_rate_limited",
                "5xx": "provider_unavailable",
                "budget_exhaustion": "budget_exhausted",
                "cas_conflict": "revision_conflict",
            }
            raise ModelGatewayError(
                codes.get(fault.kind, "tool_failed"),
                retryable=fault.kind in {"timeout", "429", "5xx"},
                capacity_feedback=fault.capacity_feedback,
            )
        return await self.inner.generate(candidate, context, task)


class FrozenResearch:
    """Exact query-result map. Missing observations fail closed, never refresh the web."""

    def __init__(self, observations: dict[str, Any], controller: FaultController) -> None:
        self.observations, self.controller = observations, controller

    async def search(self, query: SearchInput) -> SearchResult:
        if self.controller.next("research_search"):
            raise ModelGatewayError("research_search_failed", retryable=True)
        if query.query not in self.observations:
            raise ModelGatewayError("frozen_observation_missing")
        return SearchResult.model_validate(self.observations[query.query])
