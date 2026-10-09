from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from career_agent.models.contracts import (
    Complexity,
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ModelTier,
    PrivacyClass,
    TaskSpec,
)
from career_agent.models.fake import FakeProvider
from career_agent.models.gateway import ModelGateway, ModelPolicy
from career_agent.runtime.contracts import Budget


class Output(BaseModel):
    category: str


def candidate(tier=ModelTier.CHEAP, **changes):
    values = dict(
        provider="synthetic",
        model=tier.value,
        tier=tier,
        capabilities={"structured_output"},
        allowed_privacy={PrivacyClass.SYNTHETIC},
        input_cost_per_million=Decimal("0"),
        output_cost_per_million=Decimal("0"),
    )
    values.update(changes)
    return ModelCandidate(**values)


def context(**changes):
    values = dict(task_type="parse", output_schema=Output)
    values.update(changes)
    return ModelRequestContext(**values)


@pytest.fixture
def policy():
    return ModelPolicy(version="test-policy-v1", task_tiers={"parse": ModelTier.CHEAP})


async def test_fake_contract(policy):
    provider = FakeProvider({"category": "synthetic"})
    gateway = ModelGateway([candidate()], policy, {"synthetic": provider})
    result = await gateway.generate(context(), TaskSpec(instruction="Synthetic classification"))
    assert result.validated_output.category == "synthetic"
    assert result.provider == "synthetic" and result.model == "cheap"
    assert result.usage.input_tokens == 0 and result.estimated_cost == 0
    assert result.usage.cached_tokens is None and result.latency_ms >= 0
    assert result.attempts == 1 and result.schema_validation_state == "valid"
    assert result.model_policy_version == "test-policy-v1"
    assert provider.calls == 1


def test_routing_and_complexity(policy):
    registry = [candidate(), candidate(ModelTier.STRONG), candidate(ModelTier.PREMIUM)]
    assert policy.select(context(), registry).tier == ModelTier.CHEAP
    assert policy.select(context(complexity=Complexity.HIGH), registry).tier == ModelTier.STRONG
    assert policy.select(context(task_type="plan"), registry).tier == ModelTier.STRONG


@pytest.mark.parametrize(
    "changes",
    [
        {"required_capabilities": {"unsupported"}},
        {"privacy_class": PrivacyClass.PRIVATE},
        {"budget_remaining": Budget(token_limit=1)},
    ],
)
def test_ineligible_context(policy, changes):
    with pytest.raises(ModelGatewayError):
        policy.select(context(**changes), [candidate()])


def test_budget_and_no_premium_escalation(policy):
    with pytest.raises(ModelGatewayError):
        policy.select(
            context(budget_remaining=Budget(cost_limit=Decimal("0"))),
            [candidate(output_cost_per_million=Decimal("1"))],
        )
    with pytest.raises(ModelGatewayError):
        policy.select(context(), [candidate(ModelTier.PREMIUM)])


async def test_output_validation_and_provider_error(policy):
    gateway = ModelGateway([candidate()], policy, {"synthetic": FakeProvider({"wrong": True})})
    with pytest.raises(ModelGatewayError, match="invalid_model_output"):
        await gateway.generate(context(), TaskSpec(instruction="synthetic"))

    class Broken:
        async def generate(self, *args):
            raise RuntimeError("secret /private/example/resume.txt synthetic@example.invalid")

    gateway = ModelGateway([candidate()], policy, {"synthetic": Broken()})
    with pytest.raises(ModelGatewayError) as error:
        await gateway.generate(context(), TaskSpec(instruction="synthetic"))
    assert str(error.value) == "provider_error"
    assert error.value.__suppress_context__


def test_context_rejects_state_and_missing_schema():
    with pytest.raises(ValidationError):
        ModelRequestContext(task_type="parse", state={"resume": "private"}, output_schema=Output)
    with pytest.raises(ValidationError):
        ModelRequestContext(task_type="parse")
