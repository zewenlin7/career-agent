"""Reported usage, price-derived estimates and unknown-cost reservations are distinct."""

import json
from decimal import Decimal

from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    TaskSpec,
)
from career_agent.preparation.contracts import Accounting, RunLimits
from career_agent.runtime.contracts import Usage


def input_bound(context: ModelRequestContext, task: TaskSpec) -> int:
    # UTF-8 bytes upper-bound ordinary text tokens; include output schema and envelope margin.
    # Version/hash telemetry is not sent to the model and must not consume context budget.
    value = {
        "instruction": task.instruction,
        "inputs": task.inputs,
        "output_schema": context.output_schema.model_json_schema(),
    }
    count = len(json.dumps(value, ensure_ascii=False).encode()) + 1024
    if count > 80000:
        raise ModelGatewayError("context_too_large")
    return count


class BudgetLedger:
    def __init__(self, limits: RunLimits, usage: Accounting) -> None:
        self.limits, self.usage = limits, usage

    def reserve_model(self, candidate: ModelCandidate, inputs: int, outputs: int) -> Usage:
        cost = (
            inputs * candidate.input_cost_per_million + outputs * candidate.output_cost_per_million
        ) / Decimal(1000000)
        u, b = self.usage, self.limits
        if (
            u.model_calls >= b.max_model_calls
            or u.input_tokens + u.reserved_input_tokens + inputs > b.max_input_tokens
            or u.output_tokens + u.reserved_output_tokens + outputs > b.max_output_tokens
            or u.budget_consumed_usd + cost > b.max_estimated_cost
        ):
            raise ModelGatewayError("budget_exhausted")
        u.model_calls += 1
        u.reserved_input_tokens += inputs
        u.reserved_output_tokens += outputs
        u.budget_reserved_usd += cost
        return Usage(
            reserved_input_tokens=inputs,
            reserved_output_tokens=outputs,
            budget_reserved_usd=cost,
            measurement="unknown",
            pricing_version=candidate.pricing_version,
        )

    def settle(self, reserved: Usage, actual: Usage | None) -> Usage:
        result = actual.model_copy(deep=True) if actual else Usage()
        u = self.usage
        if result.input_tokens is not None:
            u.reserved_input_tokens -= reserved.reserved_input_tokens
            u.input_tokens += result.input_tokens
        else:
            result.reserved_input_tokens = reserved.reserved_input_tokens
        if result.output_tokens is not None:
            u.reserved_output_tokens -= reserved.reserved_output_tokens
            u.output_tokens += result.output_tokens
        else:
            result.reserved_output_tokens = reserved.reserved_output_tokens
        if result.estimated_cost is not None:
            u.budget_reserved_usd -= reserved.budget_reserved_usd
            u.estimated_cost += result.estimated_cost
        else:
            result.budget_reserved_usd = reserved.budget_reserved_usd
            result.pricing_version = result.pricing_version or reserved.pricing_version
        if result.input_tokens is None or result.output_tokens is None:
            u.unknown_usage_attempts += 1
        return result

    def reserve_search(self, cost: Decimal) -> Usage:
        if (
            self.usage.search_calls >= self.limits.max_web_search_calls
            or self.usage.budget_consumed_usd + cost > self.limits.max_estimated_cost
        ):
            raise ModelGatewayError("budget_exhausted")
        self.usage.search_calls += 1
        self.usage.budget_reserved_usd += cost
        return Usage(
            search_calls=1,
            budget_reserved_usd=cost,
            pricing_version="tavily-basic-payg-equivalent-v1",
        )

    def settle_search(self, reserved: Usage, *, succeeded: bool) -> Usage:
        # One observed HTTP search attempt is not proof of billed credits/free-tier coverage.
        if not succeeded:
            return reserved
        self.usage.budget_reserved_usd -= reserved.budget_reserved_usd
        self.usage.estimated_cost += reserved.budget_reserved_usd
        return Usage(
            search_calls=1,
            estimated_cost=reserved.budget_reserved_usd,
            measurement="reported",
            pricing_version=reserved.pricing_version,
        )
