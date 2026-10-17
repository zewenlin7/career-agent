"""Isolated execution boundaries, shared reservations, frozen clock and observed operations."""

import asyncio
import time
from contextvars import ContextVar
from datetime import datetime
from decimal import Decimal

from career_agent.evaluation.contracts import OperationSnapshot
from career_agent.evaluation.faults import FaultController
from career_agent.evaluation.identity import digest
from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ProviderAdapter,
    ProviderResponse,
    TaskSpec,
)
from career_agent.preparation.budget import BudgetLedger, input_bound
from career_agent.preparation.contracts import Accounting, RunLimits
from career_agent.preparation.research import ResearchAdapter, SearchInput, SearchResult

FROZEN_CLOCK: ContextVar[datetime | None] = ContextVar("evaluation_clock", default=None)


class SharedEvalBudget:
    def __init__(self, limits: RunLimits, max_seconds: float = 600) -> None:
        self.usage = Accounting()
        self.ledger = BudgetLedger(limits, self.usage)
        self.lock = asyncio.Lock()
        self.started = time.monotonic()
        self.max_seconds = max_seconds
        self.exhausted = False

    def remaining_seconds(self) -> float:
        remaining = self.max_seconds - (time.monotonic() - self.started)
        if self.exhausted or remaining <= 0:
            self.exhausted = True
            raise ModelGatewayError("eval_global_budget_exhausted")
        return remaining


class ScopedProvider:
    def __init__(
        self,
        inner: ProviderAdapter,
        shared: SharedEvalBudget,
        limits: RunLimits,
        operations: list[OperationSnapshot],
        faults: FaultController,
    ) -> None:
        self.inner, self.shared, self.operations, self.faults = inner, shared, operations, faults
        self.usage = Accounting()
        self.ledger = BudgetLedger(limits, self.usage)

    async def generate(
        self, candidate: ModelCandidate, context: ModelRequestContext, task: TaskSpec
    ) -> ProviderResponse:
        inputs = input_bound(context, task)
        async with self.shared.lock:
            if (
                self.shared.exhausted
                or time.monotonic() - self.shared.started > self.shared.max_seconds
            ):
                self.shared.exhausted = True
                raise ModelGatewayError("eval_global_budget_exhausted")
            # Preflight both ledgers on copies: failed child reservation cannot strand root funds.
            BudgetLedger(self.ledger.limits, self.usage.model_copy(deep=True)).reserve_model(
                candidate, inputs, context.max_output_tokens
            )
            try:
                BudgetLedger(
                    self.shared.ledger.limits, self.shared.usage.model_copy(deep=True)
                ).reserve_model(candidate, inputs, context.max_output_tokens)
            except ModelGatewayError:
                self.shared.exhausted = True
                raise ModelGatewayError("eval_global_budget_exhausted") from None
            root = self.shared.ledger.reserve_model(candidate, inputs, context.max_output_tokens)
            child = self.ledger.reserve_model(candidate, inputs, context.max_output_tokens)
        operation = OperationSnapshot(
            kind="model_task",
            name=context.task_type,
            version=task.prompt_version or "unknown",
            input_snapshot=task.inputs,
            input_hash=digest(task.inputs),
            provenance={
                "provider": candidate.provider,
                "model": candidate.model,
                "prompt_name": task.prompt_name,
                "prompt_version": task.prompt_version,
                "workflow_version": context.workflow_version,
                "prompt_hash": task.prompt_hash,
                "input_schema_version": task.input_schema_version,
                "output_schema_version": task.output_schema_version,
                "generation_parameters": {"max_output_tokens": context.max_output_tokens},
                "origin": "evaluation",
            },
        )
        self.operations.append(operation)
        response = None
        usage = None
        started = time.monotonic()
        try:
            try:
                remaining = self.shared.remaining_seconds()
                response = await asyncio.wait_for(
                    self.inner.generate(candidate, context, task),
                    timeout=remaining,
                )
            except TimeoutError:
                self.shared.exhausted = True
                raise ModelGatewayError("eval_deadline_exceeded") from None
            usage = response.usage
            operation.output = response.output
            return response
        except ModelGatewayError as exc:
            usage = exc.usage
            operation.reason_codes.append(exc.code)
            raise
        finally:
            operation.provenance["latency_ms"] = int((time.monotonic() - started) * 1000)
            events = [e for e in self.faults.events if e["operation"] == context.task_type]
            if events and events[-1]["attempt"] == self.faults.attempts[context.task_type]:
                operation.injected_fault = events[-1]["injected_fault"]
            async with self.shared.lock:
                settled = self.shared.ledger.settle(root, usage)
                self.ledger.settle(child, usage)
                operation.provenance["usage"] = settled.model_dump(mode="json")


class ScopedResearch:
    """Search reservations share the trial/root ledgers used by model attempts."""

    def __init__(self, inner: ResearchAdapter, scope: ScopedProvider, cost: Decimal) -> None:
        self.inner, self.scope, self.cost = inner, scope, cost

    async def search(self, query: SearchInput) -> SearchResult:
        scope = self.scope
        async with scope.shared.lock:
            scope.shared.remaining_seconds()
            BudgetLedger(scope.ledger.limits, scope.usage.model_copy(deep=True)).reserve_search(
                self.cost
            )
            try:
                BudgetLedger(
                    scope.shared.ledger.limits, scope.shared.usage.model_copy(deep=True)
                ).reserve_search(self.cost)
            except ModelGatewayError:
                scope.shared.exhausted = True
                raise ModelGatewayError("eval_global_budget_exhausted") from None
            root = scope.shared.ledger.reserve_search(self.cost)
            child = scope.ledger.reserve_search(self.cost)
        from career_agent.preparation.research import SearchToolMetadata

        metadata = SearchToolMetadata()
        operation = OperationSnapshot(
            kind="deterministic_operation",
            name=metadata.tool_name,
            version=metadata.tool_version,
            input_snapshot=query.model_dump(mode="json"),
            input_hash=digest(query.model_dump(mode="json")),
            provenance=metadata.model_dump(mode="json"),
        )
        scope.operations.append(operation)
        succeeded = False
        try:
            try:
                remaining = scope.shared.remaining_seconds()
                result = await asyncio.wait_for(self.inner.search(query), timeout=remaining)
            except TimeoutError:
                scope.shared.exhausted = True
                raise ModelGatewayError("eval_deadline_exceeded") from None
            operation.output = result.model_dump(mode="json")
            succeeded = True
            return result
        except ModelGatewayError as exc:
            operation.reason_codes.append(exc.code)
            raise
        finally:
            events = [
                event for event in scope.faults.events if event["operation"] == "research_search"
            ]
            if events and events[-1]["attempt"] == scope.faults.attempts["research_search"]:
                operation.injected_fault = events[-1]["injected_fault"]
            async with scope.shared.lock:
                settled = scope.shared.ledger.settle_search(root, succeeded=succeeded)
                scope.ledger.settle_search(child, succeeded=succeeded)
                operation.provenance["usage"] = settled.model_dump(mode="json")
