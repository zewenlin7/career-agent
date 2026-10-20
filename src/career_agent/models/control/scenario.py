"""Frozen offline control inputs. These are not production controller reconstruction."""

from typing import Literal

from pydantic import Field

from career_agent.domain.schemas import Contract
from career_agent.models.control.contracts import CapacityFeedback, ControlPolicy, FeedbackBucket
from career_agent.models.control.controller import Controller, FeedbackState


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


class ControlScenario(Contract):
    version: Literal["control-scenario-v1"] = "control-scenario-v1"
    capacity: list[InitialCapacity] = Field(default_factory=list, max_length=20)
    circuits: list[InitialCircuit] = Field(default_factory=list, max_length=20)
    feedback: dict[str, CapacityFeedback] = Field(default_factory=dict)


def isolated_controller(policy: ControlPolicy, scenario: ControlScenario) -> Controller:
    from uuid import uuid4

    from career_agent.models.control.controller import Lease

    clock = FrozenClock()
    controller = Controller(policy, clock)
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
    return controller
