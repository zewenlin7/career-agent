"""Single-process quota coordination. No lock is held across I/O or an await."""

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from career_agent.models.control.contracts import (
    CapacityFeedback,
    ControlPolicy,
    FeedbackBucket,
    TrafficClass,
)
from career_agent.models.control.recovery_contracts import AutomaticPolicy, EffectiveState, utcnow
from career_agent.runtime.contracts import Usage

HEALTH_FAILURES = frozenset(
    {"provider_timeout", "provider_connection", "provider_5xx", "provider_unavailable"}
)
AUTH_FAILURES = frozenset(
    {"provider_authentication_failed", "provider_permission_denied", "provider_model_unavailable"}
)


@dataclass
class Lease:
    id: UUID
    route: str
    provider: str
    tokens: int
    output_reserved: int
    created: float
    low_priority: bool
    probe: bool = False
    dispatched: bool = False
    settled: bool = False
    released: bool = False
    dispatch_time: float | None = None
    sequence: int = 0
    uncertain: bool = False


@dataclass
class Circuit:
    phase: str = "closed"
    observations: list[tuple[float, bool]] = field(default_factory=list)
    opened_at: float = 0
    probes: int = 0
    successes: int = 0
    disabled: bool = False
    epoch: int = 0


@dataclass
class FeedbackState:
    sequence: int = 0
    blocked_until: float = 0
    requests: int | None = None
    tokens: int | None = None
    requests_until: float = 0
    tokens_until: float = 0


class Controller:
    def __init__(
        self,
        policy: ControlPolicy,
        clock: Callable[[], float] = time.monotonic,
        utc_clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.policy = policy.model_copy(deep=True)
        self.clock = clock
        self.utc_clock = utc_clock
        self.effective = EffectiveState(ready=True)
        self.automatic_policy = AutomaticPolicy()
        self._lock = Lock()
        self.leases: dict[UUID, Lease] = {}
        self.circuits: dict[str, Circuit] = defaultdict(Circuit)
        self.feedback: dict[str, FeedbackState] = defaultdict(FeedbackState)
        self.sequence = 0
        self.control_transitions: list[dict[str, Any]] = []
        self.probe_epochs: dict[UUID, int] = {}

    async def wait(self, seconds: float) -> None:
        advance = getattr(self.clock, "advance", None)
        if advance is not None:
            advance(seconds)
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(seconds)

    def _active(self, now: float) -> list[Lease]:
        expired = [
            key
            for key, item in self.leases.items()
            if (item.settled or item.released)
            and now - (item.dispatch_time if item.dispatch_time is not None else item.created)
            >= self.policy.window_seconds
        ]
        for key in expired:
            del self.leases[key]
            self.probe_epochs.pop(key, None)
        return [item for item in self.leases.values() if not item.released]

    def acquire(
        self, provider: str, route: str, inputs: int, outputs: int, traffic: TrafficClass
    ) -> tuple[Lease | None, str, str]:
        with self._lock:
            now = self.clock()
            if not self.effective.ready or self.effective.kill or self.effective.global_kill:
                return (
                    None,
                    "controller_not_ready" if not self.effective.ready else "control_kill_switch",
                    "closed",
                )
            controls = self.effective.values(route, self.utc_clock())
            circuit = self.circuits[route]
            circuit.observations = [
                (t, ok)
                for t, ok in circuit.observations
                if now - t < self.policy.breaker.window_seconds
            ]
            if circuit.disabled:
                return None, "route_configuration_disabled", circuit.phase
            if circuit.phase == "open":
                if now - circuit.opened_at < self.policy.breaker.cooldown_seconds:
                    return None, "circuit_open", "open"
                circuit.phase = "half_open"
                circuit.successes = 0
            if (
                circuit.phase == "half_open"
                and circuit.probes >= self.policy.breaker.max_half_open_probes
            ):
                return None, "half_open_probe_limit", "half_open"
            low = traffic in {"background", "evaluation"}
            active = self._active(now)
            for key, limits, entries in [
                (
                    provider,
                    self.policy.provider,
                    [item for item in active if item.provider == provider],
                ),
                (
                    route,
                    self.policy.routes.get(route, self.policy.default_route),
                    [item for item in active if item.route == route],
                ),
            ]:
                factor = self.policy.headroom_factor * controls.pressure
                if low:
                    factor *= self.policy.background_fraction
                if len(entries) + 1 > int(limits.rpm * factor):
                    return None, "rpm_capacity", circuit.phase
                if sum(item.tokens for item in entries) + inputs + outputs > int(
                    limits.tpm * factor
                ):
                    return None, "tpm_capacity", circuit.phase
                pending = [item for item in entries if not item.settled]
                if key == route and len(pending) + 1 > max(
                    1,
                    int(
                        min(limits.concurrency, controls.concurrency or limits.concurrency) * factor
                    ),
                ):
                    return None, "route_concurrency", circuit.phase
            denial = self._feedback_denial(provider, route, active, inputs + outputs, 1, now)
            if denial:
                return None, denial, circuit.phase
            self.sequence += 1
            lease = Lease(
                uuid4(),
                route,
                provider,
                inputs + outputs,
                outputs,
                now,
                low,
                probe=circuit.phase == "half_open",
                sequence=self.sequence,
            )
            self.leases[lease.id] = lease
            if lease.probe:
                circuit.probes += 1
                self.probe_epochs[lease.id] = circuit.epoch
            return lease, "capacity_admitted", circuit.phase

    @staticmethod
    def feedback_key(provider: str, bucket: FeedbackBucket) -> str:
        return f"{provider}|{bucket.scope}|{bucket.bucket_id}"

    def _feedback_denial(
        self, provider: str, route: str, active: list[Lease], tokens: int, requests: int, now: float
    ) -> str | None:
        buckets = [self.policy.feedback_bucket(provider, route)]
        # Explicit provider-wide observations also constrain routes without an override.
        buckets.extend(
            bucket
            for configured_route, bucket in self.policy.feedback_buckets.items()
            if configured_route.startswith(f"{provider}:") and bucket.scope == "provider_shared"
        )
        # Legacy frozen scenarios explicitly described provider-wide feedback.
        buckets.append(FeedbackBucket(scope="provider_shared", bucket_id=provider))
        seen: set[str] = set()
        for bucket in buckets:
            key = self.feedback_key(provider, bucket)
            if key in seen:
                continue
            seen.add(key)
            state = self.feedback[key]
            if now < state.blocked_until:
                return "provider_rate_limited"
            entries = [
                item
                for item in active
                if item.provider == provider
                and (
                    bucket.scope == "provider_shared"
                    or self.policy.feedback_bucket(item.provider, item.route) == bucket
                )
                and (not item.settled or item.uncertain or item.sequence > state.sequence)
            ]
            if (
                state.requests is not None
                and now < state.requests_until
                and len(entries) + requests > int(state.requests * self.policy.headroom_factor)
            ):
                return "feedback_rpm_capacity"
            if (
                state.tokens is not None
                and now < state.tokens_until
                and sum(item.tokens for item in entries) + tokens
                > int(state.tokens * self.policy.headroom_factor)
            ):
                return "feedback_tpm_capacity"
        return None

    def release(self, id: UUID) -> None:
        with self._lock:
            lease = self.leases.get(id)
            if lease is None or lease.released or lease.settled or lease.dispatched:
                return
            lease.released = True
            if lease.probe:
                self.circuits[lease.route].probes -= 1

    def dispatch(self, id: UUID) -> str | None:
        with self._lock:
            lease = self.leases[id]
            if lease.released or lease.settled or lease.dispatched:
                raise ValueError("invalid_capacity_lease")
            now = self.clock()
            if not self.effective.ready or self.effective.kill or self.effective.global_kill:
                return "controller_not_ready" if not self.effective.ready else "control_kill_switch"
            controls = self.effective.values(lease.route, self.utc_clock())
            circuit = self.circuits[lease.route]
            if circuit.disabled:
                return "route_configuration_disabled"
            if circuit.phase == "open":
                return "circuit_open"
            if circuit.phase == "half_open" and (
                not lease.probe or self.probe_epochs.get(id) != circuit.epoch
            ):
                return "half_open_probe_required"
            # Lease admission may precede an asynchronous financial/DB reservation. New
            # feedback or actual-usage debt during that interval must not be bypassed.
            active = self._active(now)
            for _key, limits, entries in [
                (
                    lease.provider,
                    self.policy.provider,
                    [item for item in active if item.provider == lease.provider],
                ),
                (
                    lease.route,
                    self.policy.routes.get(lease.route, self.policy.default_route),
                    [item for item in active if item.route == lease.route],
                ),
            ]:
                factor = (
                    self.policy.headroom_factor
                    * controls.pressure
                    * (self.policy.background_fraction if lease.low_priority else 1)
                )
                # Existing dispatched calls are never preempted. Earlier pending leases
                # retain deterministic priority when a limit shrinks before dispatch.
                preceding = [
                    item for item in entries if item.dispatched or item.sequence <= lease.sequence
                ]
                if len(preceding) > int(limits.rpm * factor):
                    return "rpm_capacity"
                if _key == lease.route:
                    pending = [item for item in preceding if not item.settled]
                    ceiling = max(
                        1,
                        int(
                            min(limits.concurrency, controls.concurrency or limits.concurrency)
                            * factor
                        ),
                    )
                    if len(pending) > ceiling:
                        return "route_concurrency"
                if sum(item.tokens for item in entries) > int(limits.tpm * factor):
                    return "tpm_capacity"
            denial = self._feedback_denial(lease.provider, lease.route, active, 0, 0, now)
            if denial:
                return denial
            lease.dispatched = True
            lease.dispatch_time = now
            return None

    def settle(
        self,
        id: UUID,
        usage: Usage | None,
        code: str | None,
        feedback: CapacityFeedback | None = None,
    ) -> dict[str, object]:
        with self._lock:
            lease = self.leases.get(id)
            if lease is None or lease.settled or lease.released:
                return {"duplicate_settlement": True}
            if not lease.dispatched:
                raise ValueError("undispatched_capacity_lease")
            now = self.clock()
            reserved = lease.tokens
            if usage and usage.input_tokens is not None and usage.output_tokens is not None:
                lease.tokens = usage.input_tokens + usage.output_tokens
            lease.uncertain = (
                usage is None or usage.input_tokens is None or usage.output_tokens is None
            )
            lease.settled = True
            circuit = self.circuits[lease.route]
            if lease.probe:
                circuit.probes -= 1
            if code in AUTH_FAILURES:
                circuit.disabled = True
            qualifies = code in HEALTH_FAILURES
            healthy = code is None
            if qualifies or healthy:
                circuit.observations = [
                    (t, ok)
                    for t, ok in circuit.observations
                    if now - t < self.policy.breaker.window_seconds
                ]
                circuit.observations.append((now, healthy))
                if circuit.phase == "half_open" and lease.probe:
                    if qualifies:
                        self._open(circuit, now)
                    elif self.probe_epochs.get(id) == circuit.epoch:
                        circuit.successes += 1
                        if circuit.successes >= self.policy.breaker.recovery_successes:
                            circuit.phase = "closed"
                            circuit.observations.clear()
                elif circuit.phase == "closed":
                    observations = circuit.observations
                    consecutive = 0
                    for _, ok in reversed(observations):
                        if ok:
                            break
                        consecutive += 1
                    policy = self.policy.breaker
                    if consecutive >= policy.consecutive_failures or (
                        len(observations) >= policy.minimum_observations
                        and sum(not ok for _, ok in observations) / len(observations)
                        >= policy.failure_rate
                    ):
                        self._open(circuit, now)
            bucket = self.policy.feedback_bucket(lease.provider, lease.route)
            if (
                feedback
                and (
                    feedback.quota_scope is None or feedback.quota_scope == self.policy.quota_scope
                )
                and (feedback.bucket is None or feedback.bucket == bucket)
            ):
                # Bucket identity comes from trusted adapter/config, never raw headers.
                # Legacy unscoped feedback uses the configured bucket (route-local by default).
                state = self.feedback[self.feedback_key(lease.provider, bucket)]
                # A late 429 may tighten admission even when a newer request already
                # completed. Arrival ordering must never erase an explicit cooldown.
                if feedback.retry_after_seconds is not None:
                    state.blocked_until = max(
                        state.blocked_until, now + feedback.retry_after_seconds
                    )
                if lease.sequence >= state.sequence:
                    state.sequence = lease.sequence
                    if (
                        feedback.remaining_requests is not None
                        and feedback.reset_requests_seconds is not None
                    ):
                        state.requests = feedback.remaining_requests
                        state.requests_until = now + feedback.reset_requests_seconds
                    if (
                        feedback.remaining_tokens is not None
                        and feedback.reset_tokens_seconds is not None
                    ):
                        state.tokens = feedback.remaining_tokens
                        state.tokens_until = now + feedback.reset_tokens_seconds
                else:
                    # Older observations may tighten, never replenish, known capacity.
                    for value_attr, until_attr, value, reset in [
                        (
                            "requests",
                            "requests_until",
                            feedback.remaining_requests,
                            feedback.reset_requests_seconds,
                        ),
                        (
                            "tokens",
                            "tokens_until",
                            feedback.remaining_tokens,
                            feedback.reset_tokens_seconds,
                        ),
                    ]:
                        if value is not None and reset is not None:
                            previous = getattr(state, value_attr)
                            setattr(
                                state,
                                value_attr,
                                value if previous is None else min(previous, value),
                            )
                            setattr(state, until_attr, max(getattr(state, until_attr), now + reset))
            return {
                "provider_health": "failure" if qualifies else "success" if healthy else "neutral",
                "reserved_output_tokens": lease.output_reserved,
                "actual_output_tokens": usage.output_tokens if usage else None,
                "output_reservation_ratio": (
                    usage.output_tokens / lease.output_reserved
                    if usage and usage.output_tokens is not None and lease.output_reserved
                    else None
                ),
                "reservation_underestimated": lease.tokens > reserved,
                "capacity_debt_tokens": max(0, lease.tokens - reserved),
                "circuit_state": circuit.phase,
            }

    @staticmethod
    def _open(circuit: Circuit, now: float) -> None:
        circuit.phase = "open"
        circuit.opened_at = now
        circuit.epoch += 1
        circuit.successes = 0


# Process-owned state; request-scoped clients inject this object. No cross-process promise.
_CONTROLLERS: dict[str, Controller] = {}
_OWNERSHIP_LOCK = Lock()


def shared_controller(policy: ControlPolicy) -> Controller:
    with _OWNERSHIP_LOCK:
        existing = _CONTROLLERS.get(policy.quota_scope)
        if existing:
            if existing.policy != policy:
                raise ValueError("quota_scope_policy_conflict")
            return existing
        controller = Controller(policy)
        _CONTROLLERS[policy.quota_scope] = controller
        return controller


def operational_view(controller: Controller) -> dict[str, Any]:
    """Current counters only; no attempt inputs or provider diagnostics."""
    with controller._lock:
        active = controller._active(controller.clock())
        routes = (
            set(controller.policy.routes)
            | set(controller.circuits)
            | set(controller.effective.automatic)
            | set(controller.effective.overrides)
        )
        result = {}
        for route in sorted(routes):
            base = controller.policy.routes.get(route, controller.policy.default_route)
            values = controller.effective.values(route, controller.utc_clock())
            factor = controller.policy.headroom_factor * values.pressure
            entries = [entry for entry in active if entry.route == route]
            result[route] = {
                "effective_rpm": int(base.rpm * factor),
                "effective_tpm": int(base.tpm * factor),
                "effective_concurrency": max(
                    1, int(min(base.concurrency, values.concurrency or base.concurrency) * factor)
                ),
                "reserved_or_consumed_requests": len(entries),
                "reserved_or_consumed_tokens": sum(entry.tokens for entry in entries),
                "active_concurrency": sum(not entry.settled for entry in entries),
                "output_reservation_override": values.output_reservation,
                "sampling_rate_override": values.sampling_rate,
            }
        return {
            "routes": result,
            "outstanding_capacity_leases": sum(not entry.settled for entry in active),
            "global_revision": controller.effective.global_revision,
        }
