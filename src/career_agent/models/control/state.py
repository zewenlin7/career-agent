"""Pure UTC snapshots and deterministic bounded adjustments, shared by live and Eval."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from career_agent.models.control.contracts import ControlPolicy
    from career_agent.models.control.recovery_contracts import OperatorRequest
from uuid import UUID

from career_agent.models.control.controller import Circuit, Controller, FeedbackState, Lease
from career_agent.models.control.recovery_contracts import (
    Adjustment,
    AutomaticPolicy,
    DurableSnapshot,
    EffectiveState,
)


def snapshot(controller: Controller, now: datetime, policy_hash: str) -> DurableSnapshot:
    with controller._lock:
        mono = controller.clock()

        def utc(value: float) -> str:
            return (now + timedelta(seconds=value - mono)).isoformat()

        leases = []
        for lease in controller._active(mono):
            leases.append(
                {
                    "id": str(lease.id),
                    "route": lease.route,
                    "provider": lease.provider,
                    "tokens": lease.tokens,
                    "output_reserved": lease.output_reserved,
                    "created_at": utc(lease.created),
                    "dispatch_at": utc(lease.dispatch_time)
                    if lease.dispatch_time is not None
                    else None,
                    "expires_at": utc(
                        (lease.dispatch_time if lease.dispatch_time is not None else lease.created)
                        + controller.policy.window_seconds
                    ),
                    "low_priority": lease.low_priority,
                    "dispatched": lease.dispatched,
                    "settled": lease.settled,
                    "uncertain": lease.uncertain,
                    "sequence": lease.sequence,
                }
            )
        return DurableSnapshot(
            policy_hash=policy_hash,
            saved_at=now,
            effective=controller.effective.model_copy(deep=True),
            leases=leases,
            sequence=controller.sequence,
            circuits={
                route: {
                    "phase": c.phase,
                    "disabled": c.disabled,
                    "epoch": c.epoch,
                    "opened_at": utc(c.opened_at),
                    "successes": c.successes,
                    "observations": [[utc(t), ok] for t, ok in c.observations],
                }
                for route, c in controller.circuits.items()
            },
            feedback={
                key: {
                    "sequence": f.sequence,
                    "requests": f.requests,
                    "tokens": f.tokens,
                    "blocked_until": utc(f.blocked_until),
                    "requests_until": utc(f.requests_until),
                    "tokens_until": utc(f.tokens_until),
                }
                for key, f in controller.feedback.items()
            },
        )


def restore(controller: Controller, saved: DurableSnapshot, now: datetime) -> None:
    """Unknown execution loses its semaphore, not its capacity/financial uncertainty."""
    with controller._lock:
        mono = controller.clock()
        # Clock rollback never expires debt early. Large forward movement expires time windows only.
        effective_now = max(now, saved.saved_at)

        def relative(value: str) -> float:
            return mono + (datetime.fromisoformat(value) - effective_now).total_seconds()

        controller.leases.clear()
        controller.circuits.clear()
        controller.feedback.clear()
        controller.probe_epochs.clear()
        controller.sequence = saved.sequence
        controller.effective = saved.effective.model_copy(deep=True)
        controller.effective.ready = False
        for item in saved.leases:
            if not item["dispatched"] or relative(item["expires_at"]) <= mono:
                continue
            lease = Lease(
                UUID(item["id"]),
                item["route"],
                item["provider"],
                item["tokens"],
                item["output_reserved"],
                relative(item["created_at"]),
                item["low_priority"],
                dispatched=True,
                settled=True,
                dispatch_time=relative(item["dispatch_at"]),
                sequence=item["sequence"],
                uncertain=item.get("uncertain", False) or not item["settled"],
            )
            controller.leases[lease.id] = lease
        for route, item in saved.circuits.items():
            phase = item["phase"]
            controller.circuits[route] = Circuit(
                phase="open" if phase == "half_open" else phase,
                observations=[
                    (relative(t), ok)
                    for t, ok in item["observations"]
                    if mono - relative(t) < controller.policy.breaker.window_seconds
                ],
                opened_at=mono if phase == "half_open" else relative(item["opened_at"]),
                disabled=item["disabled"],
                epoch=item["epoch"] + 1,
            )
        for key, item in saved.feedback.items():
            controller.feedback[key] = FeedbackState(
                sequence=item["sequence"],
                requests=item["requests"],
                tokens=item["tokens"],
                blocked_until=relative(item["blocked_until"]),
                requests_until=relative(item["requests_until"]),
                tokens_until=relative(item["tokens_until"]),
            )


def adjust(
    state: EffectiveState,
    route: str,
    facts: list[dict[str, Any]],
    policy: AutomaticPolicy,
    now: datetime,
    base_concurrency: int,
) -> str | None:
    if not policy.enabled or state.kill or state.global_kill:
        return None
    if route in state.overrides and state.overrides[route].expires_at > now:
        return None
    last = state.last_adjusted.get(route)
    if last and (now - last).total_seconds() < policy.cooldown_seconds:
        return None
    if len(facts) < policy.min_observations:
        return None
    old = state.automatic.get(route, Adjustment())
    values = old.model_copy(deep=True)
    pressure = sum(
        (
            f.get("outcome")
            in {"provider_429", "provider_timeout", "provider_5xx", "provider_connection"}
            or f.get("capacity_pressure", False)
        )
        for f in facts
    ) / len(facts)
    ceiling = min(base_concurrency, policy.max_concurrency)
    floor = min(ceiling, policy.min_concurrency)
    current = old.concurrency or ceiling
    if pressure >= policy.decrease_threshold:
        values.pressure = max(policy.min_pressure, old.pressure * 0.8)
        values.concurrency = max(floor, current - 1)
        values.sampling_rate = max(
            min(
                policy.sampling_min,
                old.sampling_rate if old.sampling_rate is not None else policy.sampling_default,
            ),
            (old.sampling_rate if old.sampling_rate is not None else policy.sampling_default) / 2,
        )
        reason = "pressure_reduce"
    elif pressure <= policy.increase_threshold:
        values.pressure = min(1, old.pressure + 0.1)
        values.concurrency = min(ceiling, current + 1)
        baseline_rate = (
            old.sampling_rate if old.sampling_rate is not None else policy.sampling_default
        )
        values.sampling_rate = max(
            baseline_rate, min(policy.sampling_max, baseline_rate + Decimal(".01"))
        )
        reason = "pressure_recover"
    else:
        reason = "reservation_adjust"
    outputs = sorted(f["output_tokens"] for f in facts if f.get("output_tokens") is not None)
    if len(outputs) >= policy.min_observations:
        estimate = int(outputs[min(len(outputs) - 1, int(0.9 * len(outputs)))] * 1.2) + 1
        target = min(policy.max_output_reservation, max(policy.min_output_reservation, estimate))
        if old.output_reservation is None or abs(target - old.output_reservation) >= max(
            32, old.output_reservation * 0.2
        ):
            values.output_reservation = target
    sampling_changed = False
    for task in {str(f["task_type"]) for f in facts if f.get("task_type") is not None}:
        key = f"{route}|{task}"
        baseline = policy.sampling_per_task.get(task, policy.sampling_default)
        previous = state.sampling_rates.get(key, baseline)
        rate = previous
        if pressure >= policy.decrease_threshold:
            rate = min(previous, max(policy.sampling_min, previous / 2))
        elif pressure <= policy.increase_threshold:
            rate = max(previous, min(policy.sampling_max, previous + Decimal(".01")))
        if rate != previous:
            state.sampling_rates[key] = rate
            sampling_changed = True
    if values == old and not sampling_changed:
        return None
    state.automatic[route] = values
    state.last_adjusted[route] = now
    return reason


def operator_candidate(
    state: EffectiveState,
    request: "OperatorRequest",
    policy: AutomaticPolicy,
    base: "ControlPolicy",
    now: datetime,
) -> EffectiveState:
    """Pure validation/proposal; publish only after durable CAS commit (or isolated replay)."""
    from career_agent.domain.rules import DomainError
    from career_agent.models.control.recovery_contracts import Override

    if state.revision != request.expected_revision:
        raise DomainError("revision_conflict", 409)
    candidate = state.model_copy(deep=True)
    if request.action == "override":
        assert request.route and request.values and request.ttl_seconds
        v = request.values
        limits = base.routes.get(request.route, base.default_route)
        if (
            v.pressure < policy.min_pressure
            or v.concurrency is not None
            and not policy.min_concurrency
            <= v.concurrency
            <= min(limits.concurrency, policy.max_concurrency)
            or v.output_reservation is not None
            and not policy.min_output_reservation
            <= v.output_reservation
            <= policy.max_output_reservation
            or v.sampling_rate is not None
            and not policy.sampling_min <= v.sampling_rate <= policy.sampling_max
        ):
            raise DomainError("control_bounds_violation")
        candidate.overrides[request.route] = Override(
            values=v, expires_at=now + timedelta(seconds=request.ttl_seconds)
        )
    elif request.action == "clear_override":
        candidate.overrides.pop(request.route or "", None)
    elif request.action in {"kill", "global_kill"}:
        setattr(candidate, request.action, bool(request.enabled))
    return candidate
