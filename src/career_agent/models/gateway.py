import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    from career_agent.models.control.durable import DurableControl
from uuid import UUID, uuid4

from pydantic import ValidationError

from career_agent.models.contracts import (
    AttemptAdmission,
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ModelResult,
    ModelTier,
    ProviderAdapter,
    TaskSpec,
)
from career_agent.models.control.contracts import (
    AttemptSelection,
    ControlDecision,
    ControlPolicy,
    RouteApproval,
    RoutingRole,
    TaskControlPolicy,
    TrafficClass,
)
from career_agent.models.control.controller import HEALTH_FAILURES, Controller
from career_agent.models.diagnostics import validation_issues
from career_agent.models.prompts import PromptRegistry, application_prompts
from career_agent.runtime.contracts import OutputDiagnostic, VersionMetadata

ROUTING_ROLES: tuple[RoutingRole, ...] = ("primary", "capacity_overflow", "runtime_fallback")


@dataclass(frozen=True)
class ModelPolicy:
    version: str
    task_tiers: dict[str, ModelTier]
    task_policies: dict[str, TaskControlPolicy] = field(default_factory=dict)

    def bind(self, registry: list[ModelCandidate]) -> "ModelPolicy":
        approved = dict(self.task_policies)
        for task, tier in self.task_tiers.items():
            if task not in approved:
                routes = [
                    RouteApproval(
                        provider=c.provider,
                        model=c.model,
                        priority=i,
                        qualification_ref=f"{self.version}:{task}",
                    )
                    for i, c in enumerate(registry)
                    if c.tier == tier
                ]
                if len(routes) > 1:
                    raise ValueError("explicit_task_candidates_required")
                if routes:
                    approved[task] = TaskControlPolicy(
                        candidates=routes,
                        max_total_attempts=1 if task == "resume_compression" else 3,
                    )
        return replace(self, task_policies=approved)

    def approved(
        self, context: ModelRequestContext, registry: list[ModelCandidate]
    ) -> TaskControlPolicy:
        policy = self.bind(registry).task_policies.get(context.task_type)
        if policy is None:
            raise ModelGatewayError("unregistered_model_task")
        return policy

    def eligible(
        self, context: ModelRequestContext, candidate: ModelCandidate, inputs: int = 0
    ) -> bool:
        budget = context.budget_remaining
        if (
            budget.token_limit is not None
            and budget.token_limit < inputs + context.max_output_tokens
        ):
            raise ModelGatewayError("insufficient_token_budget")
        minimum = (
            candidate.input_cost_per_million * inputs
            + candidate.output_cost_per_million * context.max_output_tokens
        ) / Decimal(1000000)
        return (
            context.required_capabilities <= candidate.capabilities
            and context.privacy_class in candidate.allowed_privacy
            and (budget.cost_limit is None or minimum <= budget.cost_limit)
        )

    def select(
        self, context: ModelRequestContext, registry: list[ModelCandidate]
    ) -> ModelCandidate:
        """Pure preflight only. Dispatch consumes an immutable admitted selection."""
        policy = self.approved(context, registry)
        candidates = {(c.provider, c.model): c for c in registry}
        for entry in sorted(policy.candidates, key=lambda c: (c.priority, c.route)):
            candidate = candidates.get((entry.provider, entry.model))
            if candidate and "primary" in entry.roles and self.eligible(context, candidate):
                return candidate
        raise ModelGatewayError("no_eligible_model")


@dataclass
class Operation:
    deadline: float
    attempts: dict[str, int] = field(default_factory=dict)
    switches: int = 0
    previous: str | None = None
    previous_role: RoutingRole = "primary"
    failure: str | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    pending: UUID | None = None
    executing: bool = False


class ModelGateway:
    def __init__(
        self,
        registry: list[ModelCandidate],
        policy: ModelPolicy,
        adapters: dict[str, ProviderAdapter],
        prompts: PromptRegistry | None = None,
        controller: Controller | None = None,
        traffic_class: TrafficClass | None = None,
        durable: "DurableControl | None" = None,
        budget_owner_refs: tuple[UUID, ...] = (),
    ) -> None:
        if len({(c.provider, c.model) for c in registry}) != len(registry):
            raise ValueError("duplicate model candidate")
        if any(c.provider not in adapters for c in registry):
            raise ValueError("missing provider adapter")
        self.durable = durable
        self.budget_owner_refs = budget_owner_refs
        self.traffic_class = traffic_class
        self.registry = [candidate.model_copy(deep=True) for candidate in registry]
        self.policy = policy.bind(self.registry)
        self.adapters = dict(adapters)
        self.prompts = prompts if prompts is not None else application_prompts()
        # Offline callers get isolated state. Live composition must inject process-owned state.
        self.controller = controller or Controller(ControlPolicy(quota_scope="isolated"))
        self.operations: dict[UUID, Operation] = {}
        self.selections: dict[UUID, AttemptSelection] = {}
        self.outcomes: dict[UUID, dict[str, Any]] = {}
        self.selected_candidates: dict[UUID, ModelCandidate] = {}
        self.admitted_adapters: set[UUID] = set()
        self.prepared_contexts: dict[UUID, ModelRequestContext] = {}

    def seed_operation(
        self,
        identity: UUID,
        attempts: list[tuple[str, str | None]],
        elapsed_seconds: float,
        context: ModelRequestContext,
    ) -> None:
        """Resume explicit Interview retry from committed attempt metadata, never reset it."""
        if identity in self.operations:
            return
        policy = self.policy.approved(context, self.registry)
        operation = Operation(self.controller.clock() + policy.operation_seconds - elapsed_seconds)
        for route, failure in attempts:
            if operation.previous is not None and operation.previous != route:
                operation.switches += 1
            approval = next((entry for entry in policy.candidates if entry.route == route), None)
            if approval is not None:
                operation.previous_role = next(
                    role for role in ROUTING_ROLES if role in approval.roles
                )
            operation.previous, operation.failure = route, failure
            operation.attempts[route] = operation.attempts.get(route, 0) + 1
        self.operations[identity] = operation

    async def prepare(self, context: ModelRequestContext, task: TaskSpec) -> ModelRequestContext:
        try:
            return await self._prepare(context, task)
        except ModelGatewayError as exc:
            operation = self.operations.get(context.logical_operation_id)
            decisions = list(operation.decisions) if operation else []
            decisions.append(
                ControlDecision(
                    sequence=len(decisions) + 1,
                    route="unselected",
                    reason=exc.code,
                    disposition="denied",
                    logical_operation_id=context.logical_operation_id,
                ).model_dump(mode="json", exclude_none=True)
            )
            exc.control_decisions = decisions
            if self.durable:
                await self.durable.admission_denied(context, decisions)
            raise

    async def _prepare(self, context: ModelRequestContext, task: TaskSpec) -> ModelRequestContext:
        from career_agent.preparation.budget import input_bound

        if self.traffic_class is not None:
            context = context.model_copy(update={"traffic_class": self.traffic_class})
        context = context.model_copy(
            update={
                "budget_owner_refs": list(
                    dict.fromkeys((*self.budget_owner_refs, *context.budget_owner_refs))
                )
            }
        )
        self.prompts.trace_metadata(context, task)
        policy = self.policy.approved(context, self.registry)
        now = self.controller.clock()
        op = self.operations.setdefault(
            context.logical_operation_id, Operation(now + policy.operation_seconds)
        )
        if context.execution_seconds_remaining is not None:
            op.deadline = min(op.deadline, now + context.execution_seconds_remaining)
        if op.pending is not None or op.executing:
            raise ModelGatewayError("operation_attempt_inflight")
        if sum(op.attempts.values()) >= policy.max_total_attempts:
            raise ModelGatewayError("operation_attempt_limit")
        hard = min(context.max_output_tokens, policy.output.hard_max_output_tokens)
        context = context.model_copy(update={"max_output_tokens": hard})
        inputs = input_bound(context, task)
        output = min(hard, policy.output.reservation_output_tokens)
        routes = {(c.provider, c.model): c for c in self.registry}
        wait_until = min(op.deadline, now + policy.max_wait_seconds)
        while True:
            if op.pending is not None or op.executing:
                raise ModelGatewayError("operation_attempt_inflight")
            if self.controller.clock() >= op.deadline:
                raise ModelGatewayError("operation_deadline_exceeded")
            overflow = False
            for entry in sorted(policy.candidates, key=lambda c: (c.priority, c.route)):
                candidate = routes.get((entry.provider, entry.model))
                role: RoutingRole = op.previous_role if op.previous == entry.route else "primary"
                if op.previous and op.previous != entry.route:
                    role = "runtime_fallback"
                    if op.failure not in HEALTH_FAILURES | {
                        "provider_429",
                        "provider_rate_limited",
                    }:
                        continue
                    if op.switches >= policy.max_route_switches:
                        continue
                elif overflow and op.previous != entry.route:
                    role = "capacity_overflow"
                if (
                    role not in entry.roles
                    or candidate is None
                    or not self.policy.eligible(context, candidate, inputs)
                ):
                    continue
                if op.attempts.get(entry.route, 0) >= policy.max_route_attempts:
                    continue
                adapter = self.adapters[entry.provider]
                if isinstance(adapter, AttemptAdmission):
                    # Root Eval/Judge deadline also bounds waiting, not just the later HTTP call.
                    op.deadline = min(
                        op.deadline, self.controller.clock() + adapter.remaining_seconds()
                    )
                    wait_until = min(wait_until, op.deadline)
                controls = self.controller.effective.values(
                    entry.route, self.controller.utc_clock()
                )
                output = min(
                    hard, controls.output_reservation or policy.output.reservation_output_tokens
                )
                lease, reason, circuit = self.controller.acquire(
                    entry.provider, entry.route, inputs, output, context.traffic_class
                )
                decision = {
                    "route": entry.route,
                    "reason": reason,
                    "disposition": "admitted" if lease else "denied",
                }
                previous_decision = next(
                    (item for item in reversed(op.decisions) if item["route"] == entry.route), None
                )
                if (
                    lease
                    or previous_decision is None
                    or any(previous_decision.get(key) != value for key, value in decision.items())
                ):
                    op.decisions.append(
                        ControlDecision.model_validate(
                            {"sequence": len(op.decisions) + 1, **decision}
                        ).model_dump(mode="json", exclude_none=True)
                    )
                if lease is None:
                    overflow = True
                    continue
                selection = AttemptSelection(
                    controller_generation=self.controller.effective.generation,
                    automatic_policy_version=self.controller.automatic_policy.version,
                    effective_state_revision=self.controller.effective.revision,
                    global_control_revision=self.controller.effective.global_revision,
                    effective_sampling_rate=(
                        controls.sampling_rate
                        if entry.route in self.controller.effective.overrides
                        and self.controller.effective.overrides[entry.route].expires_at
                        > self.controller.utc_clock()
                        else self.controller.effective.sampling_rates.get(
                            f"{entry.route}|{context.task_type}"
                        )
                    ),
                    task_type=context.task_type,
                    input_hash=hashlib.sha256(
                        json.dumps(task.inputs, sort_keys=True, ensure_ascii=False).encode()
                    ).hexdigest(),
                    logical_operation_id=context.logical_operation_id,
                    attempt_id=uuid4(),
                    lease_id=lease.id,
                    route=entry.route,
                    provider=entry.provider,
                    model=entry.model,
                    attempt_index=sum(op.attempts.values()) + 1,
                    task_policy_version=policy.version,
                    model_policy_version=self.policy.version,
                    qualification_ref=entry.qualification_ref,
                    routing_role=role,
                    traffic_class=context.traffic_class,
                    control_policy_version=self.controller.policy.version,
                    output_policy_version=policy.output.version,
                    hard_output_tokens=hard,
                    reserved_output_tokens=output,
                    deadline=op.deadline,
                    circuit_disposition="half_open" if circuit == "half_open" else "closed",
                )
                op.pending = selection.attempt_id
                self.selections[selection.attempt_id] = selection
                self.selected_candidates[selection.attempt_id] = candidate.model_copy(deep=True)
                prepared = context.model_copy(
                    update={
                        "selection": selection,
                        "control_snapshot": {
                            "schema_version": "attempt-control-snapshot-v1",
                            "task_policy": policy.model_dump(mode="json"),
                            "controller_policy": self.controller.policy.model_dump(mode="json"),
                            "effective_state": self.controller.effective.model_dump(mode="json"),
                            "automatic_policy": self.controller.automatic_policy.model_dump(
                                mode="json"
                            ),
                            "control_transitions": list(self.controller.control_transitions),
                            "candidate": candidate.model_dump(mode="json"),
                            "selection": selection.model_dump(mode="json"),
                        },
                    }
                )
                self.prepared_contexts[selection.attempt_id] = prepared
                if self.durable:
                    try:
                        await self.durable.prepare(prepared, candidate, task)
                    except BaseException:
                        self.cancel_prepared(prepared)
                        raise
                return prepared
            if self.controller.clock() >= wait_until:
                raise ModelGatewayError("model_admission_denied")
            await self.controller.wait(min(0.01, wait_until - self.controller.clock()))

    async def admit_adapter(self, context: ModelRequestContext, task: TaskSpec) -> None:
        candidate = self.candidate(context)
        assert context.selection is not None
        adapter = self.adapters[candidate.provider]
        if context.selection.attempt_id not in self.admitted_adapters:
            try:
                if isinstance(adapter, AttemptAdmission):
                    await adapter.admit(candidate, context, task)
            except BaseException:
                self.cancel_prepared(context)
                raise
            self.admitted_adapters.add(context.selection.attempt_id)

    async def wait_retry(self, context: ModelRequestContext, seconds: float) -> None:
        operation = self.operations[context.logical_operation_id]
        remaining = operation.deadline - self.controller.clock()
        if remaining <= 0:
            raise ModelGatewayError("operation_deadline_exceeded")
        await self.controller.wait(min(seconds, remaining))

    def was_dispatched(self, context: ModelRequestContext) -> bool:
        selection = context.selection
        if selection is None:
            return False
        lease = self.controller.leases.get(selection.lease_id)
        return selection.attempt_id in self.outcomes or bool(lease and lease.dispatched)

    def cancel_pending(self, logical_operation_id: UUID) -> None:
        operation = self.operations.get(logical_operation_id)
        if operation and operation.pending:
            context = self.prepared_contexts.get(operation.pending)
            if context is not None:
                self.cancel_prepared(context)

    def cancel_prepared(self, context: ModelRequestContext) -> None:
        if (
            context.selection
            and self.selections.get(context.selection.attempt_id) == context.selection
        ):
            lease = self.controller.leases.get(context.selection.lease_id)
            if lease is not None and lease.dispatched:
                return
            if lease is not None:
                adapter = self.adapters[context.selection.provider]
                if isinstance(adapter, AttemptAdmission):
                    adapter.cancel_admission(context)
            self.controller.release(context.selection.lease_id)
            op = self.operations.get(context.logical_operation_id)
            if op and op.pending == context.selection.attempt_id:
                op.pending = None

    def candidate(self, context: ModelRequestContext) -> ModelCandidate:
        selection = context.selection
        if selection is None or self.selections.get(selection.attempt_id) != selection:
            raise ModelGatewayError("invalid_attempt_selection")
        if (
            context.task_type != selection.task_type
            or context.logical_operation_id != selection.logical_operation_id
            or context.max_output_tokens != selection.hard_output_tokens
            or context.traffic_class != selection.traffic_class
        ):
            raise ModelGatewayError("attempt_selection_mismatch")
        candidate = self.selected_candidates[selection.attempt_id]
        if (
            not context.required_capabilities <= candidate.capabilities
            or context.privacy_class not in candidate.allowed_privacy
        ):
            raise ModelGatewayError("attempt_selection_mismatch")
        return candidate.model_copy(deep=True)

    def trace_metadata(self, context: ModelRequestContext, task: TaskSpec) -> VersionMetadata:
        versions = self.prompts.trace_metadata(context, task)
        selection = context.selection
        if selection is None:
            return versions.model_copy(update={"model_policy_version": self.policy.version})
        self.candidate(context)
        metadata = {
            k: str(v) if isinstance(v, UUID) else v for k, v in selection.model_dump().items()
        }
        metadata.update(self.outcomes.get(selection.attempt_id, {}))
        return versions.model_copy(
            update={
                "model_policy_version": self.policy.version,
                "provider": selection.provider,
                "model": selection.model,
                "control_metadata": metadata,
                "control_decisions": list(self.operations[context.logical_operation_id].decisions),
            }
        )

    async def generate(
        self,
        context: ModelRequestContext,
        task: TaskSpec,
        *,
        remaining_seconds: float | None = None,
    ) -> ModelResult:
        if remaining_seconds is not None:
            # A trusted outer budget may tighten, never reset, the shared operation deadline.
            if context.selection is None:
                context = context.model_copy(
                    update={
                        "execution_seconds_remaining": min(
                            remaining_seconds,
                            context.execution_seconds_remaining
                            if context.execution_seconds_remaining is not None
                            else remaining_seconds,
                        )
                    }
                )
            else:
                self.candidate(context)
                operation = self.operations[context.logical_operation_id]
                operation.deadline = min(
                    operation.deadline, self.controller.clock() + remaining_seconds
                )
        if context.selection is None:
            context = await self.prepare(context, task)
        try:
            candidate = self.candidate(context)
            self.prompts.trace_metadata(context, task)
        except BaseException:
            self.cancel_prepared(context)
            raise
        if (
            context.selection
            and context.selection.input_hash
            != hashlib.sha256(
                json.dumps(task.inputs, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
        ):
            self.cancel_prepared(context)
            raise ModelGatewayError("attempt_input_mismatch")
        selection = context.selection
        assert selection is not None
        op = self.operations[context.logical_operation_id]
        if (
            op.executing
            or selection.attempt_id in self.outcomes
            or op.pending != selection.attempt_id
        ):
            raise ModelGatewayError("attempt_already_dispatched")
        if self.controller.clock() >= op.deadline:
            self.cancel_prepared(context)
            raise ModelGatewayError("operation_deadline_exceeded")
        adapter = self.adapters[candidate.provider]
        op.executing = True
        try:
            await self.admit_adapter(context, task)
        except BaseException:
            op.executing = False
            raise
        if self.controller.clock() >= op.deadline:
            op.executing = False
            self.cancel_prepared(context)
            raise ModelGatewayError("operation_deadline_exceeded")
        if self.durable:
            try:
                await self.durable.intent(context)
            except BaseException:
                op.executing = False
                self.cancel_prepared(context)
                raise
        started = time.perf_counter()
        denial = (
            "operation_deadline_exceeded"
            if self.controller.clock() >= op.deadline
            else self.controller.dispatch(selection.lease_id)
        )
        if denial:
            op.executing = False
            op.decisions.append(
                ControlDecision(
                    sequence=len(op.decisions) + 1,
                    route=selection.route,
                    reason=denial,
                    disposition="denied",
                ).model_dump(mode="json", exclude_none=True)
            )
            self.cancel_prepared(context)
            if self.durable:
                await self.durable.finish(context, None, denial, False, 0)
            error = ModelGatewayError(
                denial if denial == "operation_deadline_exceeded" else "model_admission_denied"
            )
            error.control_decisions = list(op.decisions)
            raise error
        if op.previous is not None and op.previous != selection.route:
            op.switches += 1
        op.previous = selection.route
        op.previous_role = selection.routing_role
        op.attempts[selection.route] = op.attempts.get(selection.route, 0) + 1
        usage = None
        feedback = None
        code = None
        diagnostic = None
        finish_reason = None
        try:
            response = await asyncio.wait_for(
                adapter.generate(candidate, context, task),
                timeout=op.deadline - self.controller.clock(),
            )
            usage, feedback = response.usage, response.capacity_feedback
            diagnostic, finish_reason = response.diagnostic, response.finish_reason
        except asyncio.CancelledError:
            code = "execution_cancelled"
            raise
        except TimeoutError:
            code = "operation_deadline_exceeded"
            raise ModelGatewayError(code) from None
        except ModelGatewayError as exc:
            code, usage, feedback = exc.code, exc.usage, exc.capacity_feedback
            diagnostic = exc.diagnostic
            raise
        except Exception:
            code = "provider_error"
            raise ModelGatewayError(code) from None
        finally:
            op.failure = code
            op.pending = None
            op.executing = False
            self.outcomes[selection.attempt_id] = self.controller.settle(
                selection.lease_id, usage, code, feedback
            )
            self.outcomes[selection.attempt_id]["attempt_outcome"] = (
                "provider_request_timeout" if code == "provider_timeout" else code or "completed"
            )
            self.outcomes[selection.attempt_id]["output_hard_limit_hit"] = finish_reason in {
                "length",
                "max_output_tokens",
            } or bool(diagnostic and diagnostic.incomplete_reason == "max_output_tokens")
            self.outcomes[selection.attempt_id]["completion_disposition"] = (
                "incomplete"
                if code == "provider_incomplete"
                or finish_reason in {"length", "max_output_tokens", "incomplete"}
                else "failed"
                if code
                else "complete"
            )
            policy = self.policy.approved(context, self.registry)
            self.outcomes[selection.attempt_id]["operation_active_seconds"] = max(
                0.0, policy.operation_seconds - (op.deadline - self.controller.clock())
            )
            with anyio.CancelScope(shield=True):
                if isinstance(adapter, AttemptAdmission):
                    await adapter.finish_admission(context)
                if self.durable:
                    try:
                        await self.durable.finish(
                            context, usage, code, True, int((time.perf_counter() - started) * 1000)
                        )
                    except ModelGatewayError as failure:
                        failure.usage = usage
                        raise
        try:
            if response.finish_reason in {"length", "max_output_tokens", "incomplete"} or (
                response.diagnostic and response.diagnostic.response_status == "incomplete"
            ):
                raise ModelGatewayError(
                    "provider_incomplete", usage=response.usage, diagnostic=response.diagnostic
                )
            output = context.output_schema.model_validate(response.output)
        except ValidationError as exc:
            diagnostic = response.diagnostic or OutputDiagnostic()
            diagnostic.failure_kind = "output_validation_failed"
            diagnostic.validation_issues = validation_issues(exc, context.output_schema)
            raise ModelGatewayError(
                "output_validation_failed", usage=response.usage, diagnostic=diagnostic
            ) from None
        versions = self.trace_metadata(context, task)
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
