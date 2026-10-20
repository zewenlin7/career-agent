"""Frozen offline control inputs. These are not production controller reconstruction."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import Field

from career_agent.domain.schemas import Contract
from career_agent.models.control.contracts import CapacityFeedback, ControlPolicy, FeedbackBucket
from career_agent.models.control.controller import Controller, FeedbackState
from career_agent.models.control.recovery_contracts import (
    AutomaticPolicy,
    DurableSnapshot,
    OperatorRequest,
)
from career_agent.models.control.state import adjust, operator_candidate, restore, snapshot


class FrozenClock:
    def __init__(self) -> None:
        self.now = 1000000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class InitialCapacity(Contract):
    provider: str
    route: str
    requests: int = Field(default=1, ge=0, le=1000)
    tokens_per_request: int = Field(default=0, ge=0, le=10000000)
    age_seconds: float = Field(default=0, ge=0, le=3600)


class InitialCircuit(Contract):
    route: str
    state: Literal["closed", "open", "half_open"]
    age_seconds: float = Field(default=0, ge=0, le=3600)


class FrozenControlEvent(Contract):
    advance_seconds: float = Field(default=0, ge=0, le=86400 * 365)
    restart: bool = False
    operator: OperatorRequest | None = None
    observations: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class ControlScenario(Contract):
    recovery_version: Literal["recovery-v1"] = "recovery-v1"
    automatic_policy: AutomaticPolicy | None = None
    persisted_initial_state: DurableSnapshot | None = None
    evaluation_utc: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    control_events: list[FrozenControlEvent] = Field(default_factory=list, max_length=50)
    version: Literal["control-scenario-v1"] = "control-scenario-v1"
    capacity: list[InitialCapacity] = Field(default_factory=list, max_length=20)
    circuits: list[InitialCircuit] = Field(default_factory=list, max_length=20)
    feedback: dict[str, CapacityFeedback] = Field(default_factory=dict)


def isolated_controller(
    policy: ControlPolicy,
    scenario: ControlScenario,
    automatic_policy: AutomaticPolicy | None = None,
) -> Controller:
    from uuid import uuid4

    from career_agent.models.contracts import ModelGatewayError
    from career_agent.models.control.controller import Lease
    from career_agent.models.control.durable import digest

    candidate_policy = automatic_policy or AutomaticPolicy()
    if scenario.automatic_policy is not None and scenario.automatic_policy != candidate_policy:
        raise ModelGatewayError("case_incompatible")
    identity = digest(
        {
            "base": policy.model_dump(mode="json"),
            "automatic": candidate_policy.model_dump(mode="json"),
        }
    )
    if (
        scenario.persisted_initial_state
        and scenario.persisted_initial_state.policy_hash != identity
    ):
        raise ModelGatewayError("case_incompatible")
    clock = FrozenClock()
    epoch = clock()
    controller = Controller(
        policy, clock, lambda: scenario.evaluation_utc + timedelta(seconds=clock() - epoch)
    )
    controller.automatic_policy = candidate_policy.model_copy(deep=True)
    if scenario.persisted_initial_state:
        restore(controller, scenario.persisted_initial_state, controller.utc_clock())
        controller.effective.ready = True
    for item in scenario.capacity:
        for _ in range(item.requests):
            lease = Lease(
                uuid4(),
                item.route,
                item.provider,
                item.tokens_per_request,
                0,
                clock() - item.age_seconds,
                False,
                dispatched=True,
                settled=True,
                dispatch_time=clock() - item.age_seconds,
            )
            controller.leases[lease.id] = lease
    for seed in scenario.circuits:
        circuit = controller.circuits[seed.route]
        circuit.phase = seed.state
        circuit.opened_at = clock() - seed.age_seconds
    for route, feedback in scenario.feedback.items():
        provider = route.split(":", 1)[0]
        bucket = (
            policy.feedback_bucket(provider, route)
            if ":" in route
            else FeedbackBucket(scope="provider_shared", bucket_id=provider)
        )
        if feedback.bucket is not None and feedback.bucket != bucket:
            raise ValueError("feedback_bucket_mismatch")
        if feedback.quota_scope is not None and feedback.quota_scope != policy.quota_scope:
            raise ValueError("feedback_quota_scope_mismatch")
        controller.feedback[controller.feedback_key(provider, bucket)] = FeedbackState(
            blocked_until=clock() + (feedback.retry_after_seconds or 0),
            requests=feedback.remaining_requests,
            tokens=feedback.remaining_tokens,
            requests_until=clock() + (feedback.reset_requests_seconds or 0),
            tokens_until=clock() + (feedback.reset_tokens_seconds or 0),
        )
    for event in scenario.control_events:
        before = controller.effective.revision
        saved = snapshot(controller, controller.utc_clock(), "frozen-eval")
        clock.advance(event.advance_seconds)
        if event.restart:
            restore(controller, saved, controller.utc_clock())
            controller.effective.ready = True
        if event.operator:
            candidate = operator_candidate(
                controller.effective,
                event.operator,
                controller.automatic_policy,
                policy,
                controller.utc_clock(),
            )
            if event.operator.action == "tick":
                for route, facts in event.observations.items():
                    limits = policy.routes.get(route, policy.default_route)
                    adjust(
                        candidate,
                        route,
                        facts,
                        controller.automatic_policy,
                        controller.utc_clock(),
                        limits.concurrency,
                    )
            candidate.revision += 1
            controller.effective = candidate
        controller.control_transitions.append(
            {
                "before_revision": before,
                "after_revision": controller.effective.revision,
                "restart": event.restart,
                "reason": event.operator.action if event.operator else "restart",
                "policy_version": controller.automatic_policy.version,
            }
        )
    return controller
