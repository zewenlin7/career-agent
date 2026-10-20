from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from career_agent.models.control.contracts import ControlPolicy
from career_agent.models.control.controller import Controller
from career_agent.models.control.recovery_contracts import Adjustment, AutomaticPolicy, Override
from career_agent.models.control.scenario import FrozenClock
from career_agent.models.control.state import adjust, restore, snapshot
from career_agent.runtime.contracts import Usage


def test_restart_utc_unknown_window_and_auth_state():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    clock = FrozenClock()
    c = Controller(ControlPolicy(), clock, lambda: now)
    lease, _, _ = c.acquire("fixture", "fixture:a", 100, 50, "normal_user")
    assert lease
    c.dispatch(lease.id)
    c.circuits["fixture:disabled"].disabled = True
    c.circuits["fixture:probe"].phase = "half_open"
    saved = snapshot(c, now, "pinned")
    assert "deadline" not in saved.model_dump_json()
    other = Controller(c.policy, lambda: 10.0, lambda: now + timedelta(seconds=5))
    restore(other, saved, now + timedelta(seconds=5))
    assert not other.effective.ready
    assert other.leases[lease.id].tokens == 150
    assert other.leases[lease.id].settled  # rebuild semaphore, preserve quota debt
    assert other.circuits["fixture:disabled"].disabled
    assert other.circuits["fixture:probe"].phase == "open"
    assert other.leases[lease.id].dispatch_time == 5.0
    restore(other, saved, now + timedelta(days=1))
    assert not other.leases
    assert other.circuits["fixture:disabled"].disabled
    restore(other, saved, now - timedelta(seconds=20))
    assert other.leases[lease.id].dispatch_time == 10.0  # no early expiry on rollback


def test_effective_controls_kill_ttl_bounds_and_no_base_mutation():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    c = Controller(ControlPolicy(), utc_clock=lambda: now)
    baseline = c.policy.model_dump()
    c.effective.overrides["fixture:a"] = Override(
        values=Adjustment(concurrency=1), expires_at=now + timedelta(seconds=2)
    )
    first, _, _ = c.acquire("fixture", "fixture:a", 1, 1, "normal_user")
    assert first
    assert c.acquire("fixture", "fixture:a", 1, 1, "normal_user")[1] == "route_concurrency"
    c.effective.kill = True
    assert c.dispatch(first.id) == "control_kill_switch"
    c.release(first.id)
    c.effective.kill = False
    now += timedelta(seconds=3)
    assert c.effective.values("fixture:a", now).concurrency is None
    assert c.policy.model_dump() == baseline


def test_tick_hysteresis_cooldown_and_override_precedence():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    c = Controller(ControlPolicy())
    p = AutomaticPolicy()
    failures = [{"outcome": "provider_429", "output_tokens": 2000}] * 5
    assert adjust(c.effective, "fixture:a", failures[:4], p, now, 10) is None
    assert adjust(c.effective, "fixture:a", failures, p, now, 10) == "pressure_reduce"
    value = c.effective.automatic["fixture:a"].model_copy(deep=True)
    assert value.concurrency == 9 and value.pressure == 0.8
    assert adjust(c.effective, "fixture:a", failures, p, now + timedelta(seconds=1), 10) is None
    for i in range(1, 50):
        adjust(c.effective, "fixture:a", failures, p, now + timedelta(seconds=60 * i), 10)
    v = c.effective.automatic["fixture:a"]
    assert v.concurrency == 1 and v.pressure == p.min_pressure
    assert p.sampling_min <= v.sampling_rate <= p.sampling_max
    later = now + timedelta(hours=2)
    c.effective.overrides["fixture:a"] = Override(
        values=Adjustment(sampling_rate=Decimal(".1")), expires_at=later + timedelta(seconds=60)
    )
    assert adjust(c.effective, "fixture:a", failures, p, later, 10) is None
    assert c.effective.values("fixture:a", later).sampling_rate == Decimal(".1")
    c.effective.global_kill = True
    assert adjust(c.effective, "fixture:b", failures, p, later, 10) is None


def test_settled_actual_survives_restart_without_charging_twice():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    c = Controller(ControlPolicy())
    lease, _, _ = c.acquire("fixture", "fixture:a", 100, 50, "normal_user")
    assert lease
    c.dispatch(lease.id)
    c.settle(lease.id, Usage(input_tokens=110, output_tokens=120), None)
    saved = snapshot(c, now, "base")
    restored = Controller(c.policy)
    restore(restored, saved, now)
    assert restored.leases[lease.id].tokens == 230
    assert restored.settle(lease.id, Usage(input_tokens=110, output_tokens=120), None) == {
        "duplicate_settlement": True
    }
    assert len(restored.circuits["fixture:a"].observations) == 1


def test_eval_restart_operator_scenario_uses_frozen_clock_and_no_live_state():
    from career_agent.models.control.recovery_contracts import OperatorRequest
    from career_agent.models.control.scenario import (
        ControlScenario,
        FrozenControlEvent,
        isolated_controller,
    )

    scenario = ControlScenario(
        control_events=[
            FrozenControlEvent(
                operator=OperatorRequest(
                    request_id=uuid4(),
                    expected_revision=0,
                    action="override",
                    route="fixture:a",
                    values=Adjustment(concurrency=1),
                    ttl_seconds=30,
                )
            ),
            FrozenControlEvent(advance_seconds=10, restart=True),
        ]
    )
    first = isolated_controller(ControlPolicy(), scenario)
    second = isolated_controller(ControlPolicy(), scenario)
    assert first.effective == second.effective or first.effective.model_dump(
        exclude={"generation"}
    ) == second.effective.model_dump(exclude={"generation"})
    assert first.control_transitions == second.control_transitions
    assert first.effective.values("fixture:a", first.utc_clock()).concurrency == 1
    first.clock.advance(21)
    assert first.effective.values("fixture:a", first.utc_clock()).concurrency is None
    assert second.effective.values("fixture:a", second.utc_clock()).concurrency == 1
    first.effective.kill = True
    assert second.acquire("fixture", "fixture:a", 1, 1, "normal_user")[0]


def test_candidate_freezes_algorithm_not_dynamic_effective_state():
    from career_agent.config import Settings
    from career_agent.evaluation.identity import candidate_config
    from career_agent.models.gateway import ModelGateway
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

    settings = Settings(_env_file=None)
    gateway = ModelGateway(registry(settings, False), POLICY, {"fixture": FixtureTaskProvider()})
    before = candidate_config(settings, gateway)
    gateway.controller.effective.revision += 1
    gateway.controller.effective.automatic["fixture:strong"] = Adjustment(concurrency=1)
    assert candidate_config(settings, gateway).config_hash == before.config_hash
    gateway.controller.automatic_policy.cooldown_seconds += 1
    assert candidate_config(settings, gateway).config_hash != before.config_hash


def test_dispatch_rechecks_new_concurrency_and_rpm():
    c = Controller(ControlPolicy())
    leases = [c.acquire("fixture", "fixture:a", 1, 1, "normal_user")[0] for _ in range(2)]
    c.effective.automatic["fixture:a"] = Adjustment(concurrency=1)
    assert c.dispatch(leases[0].id) is None
    assert c.dispatch(leases[1].id) == "route_concurrency"
    assert leases[0].dispatched and not leases[1].dispatched
    c = Controller(ControlPolicy(provider={"rpm": 4, "tpm": 10000}))
    leases = [c.acquire("fixture", "fixture:a", 1, 1, "normal_user")[0] for _ in range(2)]
    c.effective.automatic["fixture:a"] = Adjustment(pressure=0.5)
    assert c.dispatch(leases[0].id) is None
    assert c.dispatch(leases[1].id) == "rpm_capacity"


def test_sampling_adjustments_start_from_task_baseline():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    p = AutomaticPolicy(sampling_per_task={"fit": Decimal(".4")})
    c = Controller(ControlPolicy())
    bad = [{"outcome": "provider_429", "task_type": "fit"}] * 5
    adjust(c.effective, "fixture:a", bad, p, now, 10)
    assert c.effective.sampling_rates["fixture:a|fit"] == Decimal(".2")
    assert c.effective.automatic["fixture:a"].sampling_rate == Decimal(".05")
    fresh = Controller(ControlPolicy())
    adjust(
        fresh.effective, "fixture:a", [{"outcome": "completed", "task_type": "fit"}] * 5, p, now, 10
    )
    assert fresh.effective.sampling_rates["fixture:a|fit"] == Decimal(".41")
    assert fresh.effective.automatic["fixture:a"].sampling_rate == Decimal(".11")


def test_eval_uses_candidate_policy_and_rejects_incompatible_snapshot():
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.models.control.durable import digest
    from career_agent.models.control.scenario import ControlScenario, isolated_controller

    policy = ControlPolicy()
    candidate = AutomaticPolicy(cooldown_seconds=99)
    c = isolated_controller(policy, ControlScenario(), candidate)
    assert c.automatic_policy == candidate
    with pytest.raises(ModelGatewayError, match="case_incompatible"):
        isolated_controller(policy, ControlScenario(automatic_policy=AutomaticPolicy()), candidate)
    image = snapshot(c, c.utc_clock(), "wrong")
    with pytest.raises(ModelGatewayError, match="case_incompatible"):
        isolated_controller(policy, ControlScenario(persisted_initial_state=image), candidate)
    image.policy_hash = digest(
        {"base": policy.model_dump(mode="json"), "automatic": candidate.model_dump(mode="json")}
    )
    assert (
        isolated_controller(
            policy, ControlScenario(persisted_initial_state=image), candidate
        ).automatic_policy
        == candidate
    )
