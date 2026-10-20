import asyncio
from decimal import Decimal

import pytest
from test_models import PROMPTS, SPEC, candidate, context

from career_agent.models.contracts import ModelGatewayError
from career_agent.models.control.contracts import (
    BreakerPolicy,
    CapacityFeedback,
    CapacityLimits,
    ControlPolicy,
    FeedbackBucket,
    RouteApproval,
    TaskControlPolicy,
)
from career_agent.models.control.controller import Controller
from career_agent.models.control.feedback import normalized_feedback
from career_agent.models.fake import FakeProvider
from career_agent.models.gateway import ModelGateway, ModelPolicy
from career_agent.runtime.contracts import Usage


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def controller(**changes):
    clock = Clock()
    values = dict(
        provider=CapacityLimits(rpm=10, tpm=1000, concurrency=10),
        default_route=CapacityLimits(rpm=10, tpm=1000, concurrency=10),
    )
    values.update(changes)
    return Controller(ControlPolicy(**values), clock), clock


def acquire(c, route="p:a", inputs=10, output=10, traffic="normal_user"):
    return c.acquire("p", route, inputs, output, traffic)


def test_headroom_reservation_debt_expiry_and_idempotence():
    c, clock = controller()
    lease, _, _ = acquire(c, inputs=400, output=100)
    assert lease
    c.dispatch(lease.id)
    first = c.settle(lease.id, Usage(input_tokens=400, output_tokens=450), None)
    assert first["reservation_underestimated"] and first["capacity_debt_tokens"] == 350
    assert acquire(c, inputs=50, output=1)[0] is None
    assert c.settle(lease.id, Usage(input_tokens=0, output_tokens=0), None)["duplicate_settlement"]
    clock.advance(61)
    assert acquire(c, inputs=50, output=1)[0]


def test_provider_shared_routes_rpm_and_traffic_protection():
    c, _ = controller()
    held = []
    for i in range(4):
        lease, _, _ = acquire(c, route=f"p:{i}", traffic="evaluation")
        assert lease
        held.append(lease)
    assert acquire(c, route="p:last", traffic="evaluation")[0] is None
    assert acquire(c, route="p:last", traffic="interactive_user")[0]
    for lease in held:
        c.release(lease.id)
    assert acquire(c, traffic="evaluation")[0]


async def test_concurrent_atomic_admission_and_release():
    c, _ = controller(provider=CapacityLimits(rpm=2, tpm=1000, concurrency=10))

    async def admit():
        await asyncio.sleep(0)
        return acquire(c)

    results = await asyncio.gather(*[admit() for _ in range(10)])
    leases = [r[0] for r in results if r[0]]
    assert len(leases) == 1
    c.release(leases[0].id)
    assert acquire(c)[0]


def test_breaker_attempts_rolling_half_open_probes_and_recovery():
    c, clock = controller(breaker=BreakerPolicy(consecutive_failures=3, cooldown_seconds=5))
    for _ in range(3):
        lease, _, _ = acquire(c)
        assert lease
        c.dispatch(lease.id)
        c.settle(lease.id, None, "provider_5xx")
    assert c.circuits["p:a"].phase == "open"
    assert acquire(c)[1] == "circuit_open"
    clock.advance(6)
    probe, _, _ = acquire(c)
    assert probe
    assert acquire(c)[1] == "half_open_probe_limit"
    c.dispatch(probe.id)
    c.settle(probe.id, Usage(input_tokens=1, output_tokens=1), None)
    assert c.circuits["p:a"].phase == "closed"
    clock.advance(61)
    assert acquire(c)[0]


def test_business_failure_neutral_auth_disables_and_429_feedback():
    c, clock = controller()
    lease, _, _ = acquire(c)
    c.dispatch(lease.id)
    c.settle(lease.id, None, "output_validation_failed")
    assert not c.circuits["p:a"].observations
    lease, _, _ = acquire(c)
    c.dispatch(lease.id)
    c.settle(lease.id, None, "provider_429", CapacityFeedback(retry_after_seconds=5))
    assert not c.circuits["p:a"].observations
    assert acquire(c)[1] == "provider_rate_limited"
    clock.advance(6)
    lease, _, _ = acquire(c)
    c.dispatch(lease.id)
    c.settle(lease.id, None, "provider_authentication_failed")
    assert acquire(c)[1] == "route_configuration_disabled"


def test_feedback_order_does_not_erase_inflight_reservation():
    c, clock = controller()
    first, _, _ = acquire(c)
    second, _, _ = acquire(c)
    c.dispatch(first.id)
    c.dispatch(second.id)
    c.settle(
        second.id,
        None,
        "provider_429",
        CapacityFeedback(remaining_requests=0, reset_requests_seconds=5),
    )
    c.settle(
        first.id, None, None, CapacityFeedback(remaining_requests=100, reset_requests_seconds=5)
    )
    assert acquire(c)[0] is None
    clock.advance(6)
    assert acquire(c)[0]


def test_feedback_parser_allowlist():
    value = normalized_feedback(
        {
            "x-ratelimit-reset-tokens": "1m2s",
            "retry-after": "bad",
            "x-ratelimit-remaining-tokens": "20",
            "authorization": "secret",
        }
    )
    assert value.reset_tokens_seconds == 62 and value.retry_after_seconds is None
    assert "secret" not in str(value)


def gateway(c=None):
    a = candidate(model="a")
    b = candidate(model="b", input_cost_per_million=Decimal("2"))
    entries = [
        RouteApproval(provider="synthetic", model="a", priority=0, qualification_ref="approved-a"),
        RouteApproval(
            provider="synthetic",
            model="b",
            priority=1,
            qualification_ref="approved-b",
            roles={"capacity_overflow", "runtime_fallback"},
        ),
    ]
    policy = ModelPolicy(
        "test-v2",
        {"parse": a.tier},
        {"parse": TaskControlPolicy(candidates=entries, max_wait_seconds=0, max_route_attempts=1)},
    )
    return ModelGateway(
        [a, b], policy, {"synthetic": FakeProvider({"category": "test"})}, PROMPTS, controller=c
    )


async def test_bound_selection_overflow_no_skipped_call_and_unknown_task():
    c, _ = controller(
        default_route=CapacityLimits(rpm=1, tpm=1000, concurrency=1),
        headroom_factor=1,
        routes={"synthetic:b": CapacityLimits(rpm=100, tpm=1000000, concurrency=10)},
        provider=CapacityLimits(rpm=100, tpm=1000000, concurrency=10),
    )
    held, _, _ = c.acquire("synthetic", "synthetic:a", 1, 1, "normal_user")
    assert held
    g = gateway(c)
    request = await g.prepare(context(), SPEC.task({}))
    assert request.selection.model == "b" and request.selection.routing_role == "capacity_overflow"
    assert g.trace_metadata(request, SPEC.task({})).model == "b"
    result = await g.generate(request, SPEC.task({}))
    assert result.model == "b" and g.adapters["synthetic"].calls == 1
    with pytest.raises(ModelGatewayError, match="unregistered_model_task"):
        g.policy.select(context(task_type="unknown"), g.registry)


async def test_capacity_estimate_independent_hard_output_and_cancel():
    g = gateway()
    request = await g.prepare(context(max_output_tokens=3000), SPEC.task({}))
    assert request.selection.reserved_output_tokens == 512
    assert request.max_output_tokens == 3000
    g.cancel_prepared(request)
    assert g.controller.leases[request.selection.lease_id].released
    assert g.adapters["synthetic"].calls == 0


async def test_retry_switch_and_total_amplification_bounds():
    class Fails:
        def __init__(self):
            self.routes = []

        async def generate(self, selected, request, task):
            self.routes.append(selected.model)
            raise ModelGatewayError("provider_5xx", retryable=True)

    g = gateway()
    provider = Fails()
    g.adapters["synthetic"] = provider
    request = context()
    for _ in range(2):
        with pytest.raises(ModelGatewayError, match="provider_5xx"):
            await g.generate(request, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="model_admission_denied"):
        await g.generate(request, SPEC.task({}))
    assert provider.routes == ["a", "b"]
    assert sum(len(c.observations) for c in g.controller.circuits.values()) == 2
    assert g.operations[request.logical_operation_id].switches == 1


async def test_schema_repair_counts_towards_total_and_does_not_poison_breaker():
    g = gateway()
    g.policy.task_policies["parse"].max_route_attempts = 5
    g.policy.task_policies["parse"].max_total_attempts = 2
    g.adapters["synthetic"] = FakeProvider({"invalid": True})
    request = context()
    for _ in range(2):
        with pytest.raises(ModelGatewayError, match="output_validation_failed"):
            await g.generate(request, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="operation_attempt_limit"):
        await g.generate(request, SPEC.task({}))
    assert g.adapters["synthetic"].calls == 2
    assert all(ok for _, ok in g.controller.circuits["synthetic:a"].observations)


async def test_scheduled_retry_observes_circuit_opened_by_other_request():
    g = gateway()
    g.policy.task_policies["parse"].max_route_attempts = 5
    g.policy.task_policies["parse"].candidates = g.policy.task_policies["parse"].candidates[:1]

    class Fails:
        calls = 0

        async def generate(self, *args):
            self.calls += 1
            raise ModelGatewayError("provider_timeout", retryable=True)

    provider = Fails()
    g.adapters["synthetic"] = provider
    original = context()
    for request in [original, context(), context()]:
        with pytest.raises(ModelGatewayError, match="provider_timeout"):
            await g.generate(request, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="model_admission_denied") as error:
        await g.generate(original, SPEC.task({}))
    assert provider.calls == 3
    assert any(d["reason"] == "circuit_open" for d in error.value.control_decisions)


async def test_shared_operation_deadline_not_reset_after_failure():
    from career_agent.models.control.scenario import ControlScenario, isolated_controller

    c = isolated_controller(ControlPolicy(), ControlScenario())
    g = gateway(c)
    g.policy.task_policies["parse"].operation_seconds = 2

    class Fails:
        async def generate(self, *args):
            c.clock.advance(3)
            raise ModelGatewayError("provider_timeout", retryable=True)

    g.adapters["synthetic"] = Fails()
    request = context()
    with pytest.raises(ModelGatewayError, match="provider_timeout"):
        await g.generate(request, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="operation_deadline_exhausted"):
        await g.generate(request, SPEC.task({}))
    assert sum(g.operations[request.logical_operation_id].attempts.values()) == 1


async def test_bound_selection_cannot_be_replayed_or_double_prepared():
    g = gateway()
    initial = context()
    prepared = await g.prepare(initial, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="operation_attempt_inflight"):
        await g.prepare(initial, SPEC.task({}))
    await g.generate(prepared, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="attempt_already_dispatched"):
        await g.generate(prepared, SPEC.task({}))
    assert g.adapters["synthetic"].calls == 1


async def test_financial_admission_denial_never_dispatches_provider_or_rpm():
    from career_agent.evaluation.contracts import FaultPlan
    from career_agent.evaluation.execution import ScopedProvider, SharedEvalBudget
    from career_agent.evaluation.faults import FaultController
    from career_agent.preparation.contracts import RunLimits

    g = gateway()
    limits = RunLimits(max_input_tokens=1)
    shared = SharedEvalBudget(limits)
    underlying = FakeProvider({"category": "ok"})
    wrapped = ScopedProvider(underlying, shared, limits, [], FaultController(FaultPlan()))
    g.adapters["synthetic"] = wrapped
    with pytest.raises(ModelGatewayError, match="budget_exhausted"):
        await g.generate(context(), SPEC.task({}))
    assert underlying.calls == shared.usage.model_calls == 0
    assert all(lease.released and not lease.dispatched for lease in g.controller.leases.values())
    assert not g.controller.circuits["synthetic:a"].observations


async def test_cancel_after_dispatch_keeps_unknown_capacity_and_releases_concurrency():
    g = gateway()
    entered = asyncio.Event()

    class Slow:
        async def generate(self, *args):
            entered.set()
            await asyncio.Event().wait()

    g.adapters["synthetic"] = Slow()
    task = asyncio.create_task(g.generate(context(), SPEC.task({})))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    lease = next(iter(g.controller.leases.values()))
    assert lease.settled and lease.dispatched and lease.tokens > 512
    assert not g.controller.circuits[lease.route].observations
    assert list(g.outcomes.values())[0]["provider_health"] == "neutral"


async def test_hard_limit_never_returns_complete_even_if_json_valid():
    from career_agent.models.contracts import ProviderResponse

    class Truncated:
        async def generate(self, *args):
            return ProviderResponse(
                output={"category": "valid"},
                usage=Usage(input_tokens=10, output_tokens=512),
                finish_reason="max_output_tokens",
            )

    g = gateway()
    g.adapters["synthetic"] = Truncated()
    with pytest.raises(ModelGatewayError, match="provider_incomplete") as error:
        await g.generate(context(), SPEC.task({}))
    assert error.value.usage.output_tokens == 512


def test_route_concurrency_and_provider_tpm_are_independent():
    c, _ = controller(
        headroom_factor=1, default_route=CapacityLimits(rpm=100, tpm=1000, concurrency=1)
    )
    lease, _, _ = acquire(c, inputs=400, output=100)
    assert lease
    assert acquire(c)[1] == "route_concurrency"
    assert acquire(c, route="p:b", inputs=500, output=1)[1] == "tpm_capacity"
    c.dispatch(lease.id)
    c.settle(lease.id, Usage(input_tokens=1, output_tokens=1), None)
    assert acquire(c)[0]


def test_rolling_failures_expire_instead_of_accumulating_forever():
    c, clock = controller()
    for _ in range(4):
        lease, _, _ = acquire(c)
        assert lease
        c.dispatch(lease.id)
        c.settle(lease.id, None, "provider_5xx")
        clock.advance(61)
    assert c.circuits["p:a"].phase == "closed"
    assert len(c.circuits["p:a"].observations) == 1


def test_threaded_admission_does_not_oversell_shared_provider():
    from concurrent.futures import ThreadPoolExecutor

    c, _ = controller(headroom_factor=1, provider=CapacityLimits(rpm=3, tpm=60, concurrency=20))
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda i: acquire(c, route=f"p:{i}"), range(40)))
    assert sum(lease is not None for lease, _, _ in results) == 3
    assert sum(item.tokens for item in c.leases.values()) == 60


def test_feedback_remaining_is_consumed_by_subsequent_settled_calls():
    c, _ = controller(headroom_factor=1)
    first, _, _ = acquire(c)
    c.dispatch(first.id)
    c.settle(
        first.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(remaining_requests=1, reset_requests_seconds=30),
    )
    second, _, _ = acquire(c)
    assert second
    c.dispatch(second.id)
    c.settle(second.id, Usage(input_tokens=1, output_tokens=1), None)
    assert acquire(c)[1] == "feedback_rpm_capacity"


async def test_429_readmission_without_health_failure():
    shared = FeedbackBucket(scope="provider_shared", bucket_id="test-provider")
    g = gateway(
        Controller(
            ControlPolicy(
                feedback_buckets={
                    "synthetic:a": shared,
                    "synthetic:b": shared,
                }
            )
        )
    )
    g.policy.task_policies["parse"].max_route_attempts = 3

    class RateLimited:
        calls = 0

        async def generate(self, *args):
            self.calls += 1
            raise ModelGatewayError(
                "provider_429",
                retryable=True,
                capacity_feedback=CapacityFeedback(retry_after_seconds=10),
            )

    provider = RateLimited()
    g.adapters["synthetic"] = provider
    request = context()
    with pytest.raises(ModelGatewayError, match="provider_429"):
        await g.generate(request, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="model_admission_denied"):
        await g.generate(request, SPEC.task({}))
    assert provider.calls == 1
    assert all(not value.observations for value in g.controller.circuits.values())


async def test_control_state_changes_do_not_reroute_bound_trace_or_price():
    g = gateway()
    prepared = await g.prepare(context(), SPEC.task({}))
    original = g.candidate(prepared)
    g.registry[0].input_cost_per_million = Decimal("999")
    g.controller.circuits["synthetic:a"].phase = "open"
    # Provenance never performs eligibility/routing again.
    assert g.trace_metadata(prepared, SPEC.task({})).model == original.model
    assert g.candidate(prepared).input_cost_per_million == original.input_cost_per_million
    g.cancel_prepared(prepared)


async def test_committed_explicit_retry_cannot_reset_amplification_or_deadline():
    g = gateway()
    request = context()
    g.seed_operation(
        request.logical_operation_id, [("synthetic:a", "provider_timeout")] * 3, 1, request
    )
    with pytest.raises(ModelGatewayError, match="operation_attempt_limit"):
        await g.prepare(request, SPEC.task({}))
    fresh = context()
    g.seed_operation(fresh.logical_operation_id, [("synthetic:a", "provider_timeout")], 1000, fresh)
    with pytest.raises(ModelGatewayError, match="operation_deadline_exhausted"):
        await g.prepare(fresh, SPEC.task({}))
    assert not g.controller.leases


async def test_eval_isolates_live_state_dispatches_correct_adapter_and_records_control():
    from career_agent.config import Settings
    from career_agent.evaluation.contracts import EvalRunRequest
    from career_agent.evaluation.execution import SharedEvalBudget
    from career_agent.evaluation.fixtures import initial_cases
    from career_agent.evaluation.runner import EvalRunner
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

    settings = Settings(live_enabled=False)

    class Decoy:
        async def generate(self, *args):
            raise AssertionError("wrong_adapter_selected")

    base = ModelGateway(
        registry(settings, False),
        POLICY,
        {"unselected_adapter": Decoy(), "fixture": FixtureTaskProvider()},
    )
    case = initial_cases()[0]
    selected = base.policy.select(context(task_type=case.entrypoint.name), base.registry)
    route = f"{selected.provider}:{selected.model}"
    base.controller.circuits[route].phase = "open"
    base.controller.circuits[route].opened_at = base.controller.clock()
    runner = EvalRunner(None, settings, base)
    request = EvalRunRequest(suite_id="test", suite_version=1)
    result, operations = await runner.run_case(case, request, SharedEvalBudget(request.limits))
    assert result.status == "completed"
    assert operations[0].provenance["provider"] == "fixture"
    assert operations[0].provenance["control_selection"]["traffic_class"] == "evaluation"
    assert operations[0].provenance["control_outcome"]["provider_health"] == "success"
    assert base.controller.circuits[route].phase == "open" and not base.controller.leases
    from career_agent.models.control.scenario import ControlScenario, InitialCircuit

    case.control_scenario = ControlScenario(circuits=[InitialCircuit(route=route, state="open")])
    result, denied = await runner.run_case(case, request, SharedEvalBudget(request.limits))
    assert result.reason_code == "model_admission_denied"
    assert denied and all(op.kind != "model_task" for op in denied)
    assert denied[0].provenance["control_decisions"]


def test_candidate_manifest_freezes_policies_not_mutable_capacity():
    from career_agent.config import Settings
    from career_agent.evaluation.identity import candidate_config

    g = gateway()
    before = candidate_config(Settings(), g)
    g.controller.circuits["synthetic:a"].phase = "open"
    assert candidate_config(Settings(), g).config_hash == before.config_hash
    g.policy.task_policies["parse"].output.reservation_output_tokens += 1
    assert candidate_config(Settings(), g).config_hash != before.config_hash


async def test_budget_cancel_before_dispatch_restores_both_eval_projections():
    from career_agent.evaluation.contracts import FaultPlan
    from career_agent.evaluation.execution import ScopedProvider, SharedEvalBudget
    from career_agent.evaluation.faults import FaultController
    from career_agent.preparation.contracts import RunLimits

    g = gateway()
    limits = RunLimits()
    shared = SharedEvalBudget(limits)
    wrapped = ScopedProvider(
        FakeProvider({"category": "ok"}), shared, limits, [], FaultController(FaultPlan())
    )
    g.adapters["synthetic"] = wrapped
    request = await g.prepare(context(), SPEC.task({}))
    await g.admit_adapter(request, SPEC.task({}))
    assert shared.usage.model_calls == wrapped.usage.model_calls == 1
    g.cancel_prepared(request)
    g.cancel_prepared(request)
    assert shared.usage.model_calls == wrapped.usage.model_calls == 0
    assert shared.usage.reserved_input_tokens == 0
    assert wrapped.usage.reserved_output_tokens == 0


async def test_circuit_open_between_selection_and_dispatch_refunds_without_attempt():
    from career_agent.evaluation.contracts import FaultPlan
    from career_agent.evaluation.execution import ScopedProvider, SharedEvalBudget
    from career_agent.evaluation.faults import FaultController
    from career_agent.preparation.contracts import RunLimits

    g = gateway()
    limits = RunLimits()
    shared = SharedEvalBudget(limits)
    inner = FakeProvider({"category": "ok"})
    scope = ScopedProvider(inner, shared, limits, [], FaultController(FaultPlan()))
    g.adapters["synthetic"] = scope
    request = await g.prepare(context(), SPEC.task({}))
    await g.admit_adapter(request, SPEC.task({}))
    g.controller.circuits[request.selection.route].phase = "open"
    with pytest.raises(ModelGatewayError, match="model_admission_denied"):
        await g.generate(request, SPEC.task({}))
    assert shared.usage.model_calls == scope.usage.model_calls == inner.calls == 0
    assert not g.was_dispatched(request)
    assert g.controller.leases[request.selection.lease_id].released
    assert g.operations[request.logical_operation_id].attempts == {}


async def test_concurrent_same_bound_attempt_dispatches_only_once():
    g = gateway()
    entered = asyncio.Event()
    release = asyncio.Event()

    class Slow(FakeProvider):
        async def generate(self, *args):
            entered.set()
            await release.wait()
            return await super().generate(*args)

    provider = Slow({"category": "ok"})
    g.adapters["synthetic"] = provider
    request = await g.prepare(context(), SPEC.task({}))
    first = asyncio.create_task(g.generate(request, SPEC.task({})))
    await entered.wait()
    with pytest.raises(ModelGatewayError, match="attempt_already_dispatched"):
        await g.generate(request, SPEC.task({}))
    release.set()
    await first
    assert provider.calls == 1


async def test_route_switch_bound_and_role_restriction():
    g = gateway()
    g.policy.task_policies["parse"].max_route_switches = 0

    class Failure:
        calls = 0

        async def generate(self, *args):
            self.calls += 1
            raise ModelGatewayError("provider_5xx", retryable=True)

    provider = Failure()
    g.adapters["synthetic"] = provider
    request = context()
    with pytest.raises(ModelGatewayError, match="provider_5xx"):
        await g.generate(request, SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="model_admission_denied"):
        await g.generate(request, SPEC.task({}))
    assert provider.calls == 1
    assert all(selection.model == "a" for selection in g.selections.values())


def test_late_429_tightens_instead_of_being_dropped_as_old_feedback():
    c, clock = controller(headroom_factor=1)
    old, _, _ = acquire(c)
    newer, _, _ = acquire(c)
    c.dispatch(old.id)
    c.dispatch(newer.id)
    c.settle(
        newer.id, None, None, CapacityFeedback(remaining_requests=100, reset_requests_seconds=5)
    )
    c.settle(
        old.id,
        None,
        "provider_429",
        CapacityFeedback(retry_after_seconds=10, remaining_requests=0, reset_requests_seconds=10),
    )
    assert acquire(c)[1] == "provider_rate_limited"
    clock.advance(11)
    assert acquire(c)[0]


def test_new_registry_route_is_not_implicitly_task_qualified():
    a = candidate(model="first")
    b = candidate(model="unqualified")
    with pytest.raises(ValueError, match="explicit_task_candidates_required"):
        ModelGateway(
            [a, b],
            ModelPolicy("test-v1", {"parse": a.tier}),
            {"synthetic": FakeProvider({"category": "ok"})},
            PROMPTS,
        )


async def test_explicit_live_eval_composition_shares_quota_but_rejects_synthetic_faults():
    # A fixture adapter under the real-provider route identity: zero network/API calls.
    from career_agent.config import Settings
    from career_agent.evaluation.contracts import EvalRunRequest, Fault, FaultPlan
    from career_agent.evaluation.execution import SharedEvalBudget
    from career_agent.evaluation.fixtures import initial_cases
    from career_agent.evaluation.runner import EvalRunner
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

    settings = Settings(live_enabled=True)
    candidates = [c.model_copy(update={"provider": "openai"}) for c in registry(settings, False)]
    base = ModelGateway(candidates, POLICY, {"openai": FixtureTaskProvider()})
    runner = EvalRunner(None, settings, base, allow_paid_models=True)
    case = initial_cases()[0].model_copy(deep=True)
    request = EvalRunRequest(suite_id="test", suite_version=1)
    result, operations = await runner.run_case(case, request, SharedEvalBudget(request.limits))
    assert result.status == "completed"
    assert len(base.controller.leases) == 1
    assert next(iter(base.controller.leases.values())).settled
    assert operations[0].provenance["control_selection"]["traffic_class"] == "evaluation"
    case.fault_plan = FaultPlan(
        faults=[Fault(operation=case.entrypoint.name, attempt=1, kind="5xx")]
    )
    result, operations = await runner.run_case(case, request, SharedEvalBudget(request.limits))
    assert result.reason_code == "eval_live_control_scenario_forbidden"
    assert not operations and len(base.controller.leases) == 1
    assert all(all(ok for _, ok in c.observations) for c in base.controller.circuits.values())


async def test_parent_time_budget_caps_admission_wait_before_dispatch():
    from career_agent.models.control.scenario import ControlScenario, isolated_controller

    c = isolated_controller(ControlPolicy(provider=CapacityLimits(rpm=1)), ControlScenario())
    g = gateway(c)
    g.policy.task_policies["parse"].max_wait_seconds = 10
    start = c.clock()
    with pytest.raises(ModelGatewayError, match="operation_deadline_exhausted"):
        await g.generate(context(execution_seconds_remaining=0.02), SPEC.task({}))
    assert c.clock() - start <= 0.021
    assert not c.leases and g.adapters["synthetic"].calls == 0


def test_interview_preflight_validates_affordability_without_selecting_route(monkeypatch):
    from career_agent.config import Settings
    from career_agent.evaluation.fixtures import initial_cases
    from career_agent.interview.calls import InterviewCalls
    from career_agent.interview.policy import CallPolicy
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

    base = ModelGateway(registry(Settings(), False), POLICY, {"fixture": FixtureTaskProvider()})
    case = next(
        c
        for c in initial_cases()
        if c.entrypoint.name == "mock_interview_turn_generation" and c.model_input
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight_must_not_select_an_attempt_route")

    monkeypatch.setattr(ModelPolicy, "select", forbidden)
    calls = InterviewCalls(None, base)
    assert calls.preflight(case.entrypoint.name, "fixture", case.model_input, CallPolicy()) > 0
    assert not base.selections and not base.controller.leases


def test_independent_route_feedback_cannot_replenish_another_route():
    c, _ = controller()
    a, _, _ = acquire(c, route="p:a")
    b, _, _ = acquire(c, route="p:b")
    c.dispatch(a.id)
    c.dispatch(b.id)
    c.settle(
        a.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(remaining_tokens=0, reset_tokens_seconds=60),
    )
    c.settle(
        b.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(remaining_tokens=1000, reset_tokens_seconds=60),
    )
    assert acquire(c, route="p:a")[1] == "feedback_tpm_capacity"
    assert acquire(c, route="p:b")[0] is not None


@pytest.mark.parametrize("scope", ["provider_shared", "shared_group"])
def test_explicit_shared_bucket_feedback_shares_and_preserves_reservations(scope):
    bucket = FeedbackBucket(scope=scope, bucket_id="approved-shared")
    c, _ = controller(
        feedback_buckets={"p:a": bucket, "p:b": bucket},
        provider=CapacityLimits(rpm=100, tpm=10000),
        default_route=CapacityLimits(rpm=100, tpm=10000),
    )
    a, _, _ = acquire(c, route="p:a")
    b, _, _ = acquire(c, route="p:b", inputs=100, output=100)
    c.dispatch(a.id)
    c.dispatch(b.id)
    c.settle(
        a.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(bucket=bucket, remaining_tokens=0, reset_tokens_seconds=60),
    )
    assert acquire(c, route="p:b")[1] == "feedback_tpm_capacity"
    # A newer same-bucket counter may replenish; it does not erase other leases.
    c.settle(
        b.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(bucket=bucket, remaining_tokens=1000, reset_tokens_seconds=60),
    )
    held, _, _ = acquire(c, route="p:a", inputs=800, output=0)
    assert held is not None
    assert acquire(c, route="p:b", inputs=101, output=0)[1] == "feedback_tpm_capacity"
    c.release(held.id)
    assert acquire(c, route="p:b", inputs=101, output=0)[0] is not None


def test_untrusted_feedback_bucket_cannot_clear_route_limit():
    c, _ = controller()
    a, _, _ = acquire(c)
    b, _, _ = acquire(c)
    c.dispatch(a.id)
    c.dispatch(b.id)
    c.settle(
        a.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(remaining_tokens=0, reset_tokens_seconds=60),
    )
    c.settle(
        b.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(
            bucket=FeedbackBucket(scope="provider_shared", bucket_id="fake"),
            remaining_tokens=1000,
            reset_tokens_seconds=60,
        ),
    )
    assert acquire(c)[1] == "feedback_tpm_capacity"


async def test_operation_deadline_is_neutral_and_cannot_enable_fallback():
    c = Controller(ControlPolicy())
    g = gateway(c)

    class Slow:
        async def generate(self, *args):
            await asyncio.sleep(1)

    g.adapters["synthetic"] = Slow()
    request = await g.prepare(context(execution_seconds_remaining=0.01), SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="operation_deadline_exceeded"):
        await g.generate(request, SPEC.task({}))
    metadata = g.trace_metadata(request, SPEC.task({})).control_metadata
    assert metadata["attempt_outcome"] == "operation_deadline_exceeded"
    assert metadata["provider_health"] == "neutral"
    assert c.circuits[request.selection.route].observations == []
    assert g.operations[request.logical_operation_id].failure == "operation_deadline_exceeded"
    with pytest.raises(ModelGatewayError, match="operation_deadline_exhausted"):
        await g.prepare(request.model_copy(update={"selection": None}), SPEC.task({}))
    assert len(g.outcomes) == 1


async def test_provider_timeout_classification_trace_and_health_agree():
    c = Controller(ControlPolicy())
    g = gateway(c)

    class Timeout:
        async def generate(self, *args):
            raise ModelGatewayError("provider_timeout", retryable=True)

    g.adapters["synthetic"] = Timeout()
    request = await g.prepare(context(), SPEC.task({}))
    with pytest.raises(ModelGatewayError, match="provider_timeout"):
        await g.generate(request, SPEC.task({}))
    metadata = g.trace_metadata(request, SPEC.task({})).control_metadata
    assert metadata["attempt_outcome"] == "provider_request_timeout"
    assert metadata["provider_health"] == "failure"
    assert [ok for _, ok in c.circuits[request.selection.route].observations] == [False]
    assert g.operations[request.logical_operation_id].failure == "provider_timeout"


async def test_external_cancellation_is_neutral_and_trace_preserves_classification():
    c = Controller(ControlPolicy())
    g = gateway(c)
    started = asyncio.Event()

    class Slow:
        async def generate(self, *args):
            started.set()
            await asyncio.sleep(1)

    g.adapters["synthetic"] = Slow()
    request = await g.prepare(context(), SPEC.task({}))
    pending = asyncio.create_task(g.generate(request, SPEC.task({})))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    metadata = g.trace_metadata(request, SPEC.task({})).control_metadata
    assert metadata["attempt_outcome"] == "execution_cancelled"
    assert metadata["provider_health"] == "neutral"
    assert c.circuits[request.selection.route].observations == []


def test_provider_shared_feedback_also_protects_unmapped_routes():
    bucket = FeedbackBucket(scope="provider_shared", bucket_id="account-shared")
    c, _ = controller(feedback_buckets={"p:a": bucket})
    a, _, _ = acquire(c, route="p:a")
    c.dispatch(a.id)
    c.settle(
        a.id,
        Usage(input_tokens=1, output_tokens=1),
        None,
        CapacityFeedback(bucket=bucket, remaining_tokens=0, reset_tokens_seconds=60),
    )
    assert acquire(c, route="p:b")[1] == "feedback_tpm_capacity"


def test_legacy_frozen_provider_feedback_remains_conservative():
    from career_agent.models.control.scenario import ControlScenario, isolated_controller

    c = isolated_controller(
        ControlPolicy(),
        ControlScenario(
            feedback={"p": CapacityFeedback(remaining_tokens=0, reset_tokens_seconds=60)}
        ),
    )
    assert acquire(c, route="p:a")[1] == "feedback_tpm_capacity"
    assert acquire(c, route="p:b")[1] == "feedback_tpm_capacity"
