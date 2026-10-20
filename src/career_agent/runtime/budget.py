"""One root ledger, with child accounting projections; never sum parent + child usage."""

import asyncio
from collections.abc import Callable
from decimal import Decimal

from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ModelResult,
    TaskSpec,
)
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.budget import BudgetLedger
from career_agent.preparation.contracts import Accounting, RunLimits
from career_agent.preparation.research import ResearchAdapter, SearchInput, SearchResult
from career_agent.runtime.agent_contracts import AgentState
from career_agent.runtime.contracts import Usage


def run_limits(state: AgentState, *, remaining: bool = False) -> RunLimits:
    b, u = state.limits, state.usage
    return RunLimits(
        max_model_calls=max(0, b.max_model_calls - (u.model_calls if remaining else 0)),
        max_web_search_calls=max(0, b.max_web_search_calls - (u.search_calls if remaining else 0)),
        max_input_tokens=max(
            0, b.max_input_tokens - (u.input_tokens + u.reserved_input_tokens if remaining else 0)
        ),
        max_output_tokens=max(
            0,
            b.max_output_tokens - (u.output_tokens + u.reserved_output_tokens if remaining else 0),
        ),
        max_estimated_cost=max(
            Decimal(0), b.max_estimated_cost - (u.budget_consumed_usd if remaining else Decimal(0))
        ),
        max_semantic_resume_compressions=max(0, 1 - u.semantic_compressions),
    )


class RuntimeBudget:
    def __init__(self, state: AgentState, remaining_seconds: Callable[[], float]) -> None:
        self.state, self.remaining_seconds = state, remaining_seconds
        self.root = BudgetLedger(run_limits(state), state.usage)

    def check_time(self) -> None:
        if self.remaining_seconds() <= 0:
            raise ModelGatewayError("active_time_exhausted")

    def tool(self) -> None:
        self.check_time()
        if self.state.usage.tool_calls >= self.state.limits.max_tool_calls:
            raise ModelGatewayError("tool_budget_exhausted")
        self.state.usage.tool_calls += 1

    def before_node(self, name: str) -> None:
        self.check_time()
        if name in {"compile_resume", "recompile_resume"}:
            self.tool()
        if name == "compress_resume":
            if self.state.usage.semantic_compressions >= 1:
                raise ModelGatewayError("layout_failed")
            self.state.usage.semantic_compressions += 1

    async def generate(
        self, gateway: ModelGateway, context: ModelRequestContext, task: TaskSpec
    ) -> ModelResult:
        self.check_time()
        # The attempt selection already binds the remaining root deadline. Do not
        # cancel and reclassify the attempt after Gateway has settled it.
        return await gateway.generate(context, task, remaining_seconds=self.remaining_seconds())

    async def search(self, adapter: ResearchAdapter, query: SearchInput) -> SearchResult:
        self.check_time()
        try:
            return await asyncio.wait_for(adapter.search(query), timeout=self.remaining_seconds())
        except TimeoutError:
            raise ModelGatewayError("active_time_exhausted") from None

    def ledger(self, limits: RunLimits, usage: Accounting) -> "ScopedLedger":
        return ScopedLedger(self, BudgetLedger(limits, usage))


class ScopedLedger(BudgetLedger):
    def __init__(self, scope: RuntimeBudget, child: BudgetLedger) -> None:
        super().__init__(child.limits, child.usage)
        self.scope = scope

    def reserve_model(self, candidate: ModelCandidate, inputs: int, outputs: int) -> Usage:
        self.scope.check_time()
        # Validate both sides before mutating either ledger. No await in this critical section.
        BudgetLedger(
            self.scope.root.limits, self.scope.root.usage.model_copy(deep=True)
        ).reserve_model(candidate, inputs, outputs)
        reservation = super().reserve_model(candidate, inputs, outputs)
        self.scope.root.reserve_model(candidate, inputs, outputs)
        return reservation

    def cancel_model(self, reserved: Usage) -> None:
        self.scope.root.cancel_model(reserved)
        super().cancel_model(reserved)

    def settle(self, reserved: Usage, actual: Usage | None) -> Usage:
        self.scope.root.settle(reserved, actual)
        return super().settle(reserved, actual)

    def reserve_search(self, cost: Decimal) -> Usage:
        BudgetLedger(
            self.scope.root.limits, self.scope.root.usage.model_copy(deep=True)
        ).reserve_search(cost)
        self.scope.tool()
        reserved = super().reserve_search(cost)
        self.scope.root.reserve_search(cost)
        return reserved

    def settle_search(self, reserved: Usage, *, succeeded: bool) -> Usage:
        self.scope.root.settle_search(reserved, succeeded=succeeded)
        return super().settle_search(reserved, succeeded=succeeded)
