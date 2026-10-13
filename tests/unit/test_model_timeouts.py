"""Real SDK over mock HTTP: per-task overrides, error mapping, no body leakage/retry."""

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from career_agent.config import Settings
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext
from career_agent.models.openai_adapter import OpenAIProvider
from career_agent.models.timeouts import ModelTimeoutPolicy
from career_agent.preparation.contracts import TaskType
from career_agent.preparation.prompts import OUTPUTS, PromptSpec
from career_agent.preparation.providers import POLICY, dependencies, registry


def test_timeout_policy_configuration_and_budget_independence(monkeypatch):
    monkeypatch.setenv("CAREER_AGENT_MODEL_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("CAREER_AGENT_MODEL_TASK_TIMEOUT_SECONDS", '{"interview_preparation":120}')
    settings = Settings()
    policy = ModelTimeoutPolicy(
        default_seconds=settings.model_timeout_seconds,
        task_seconds=settings.model_task_timeout_seconds,
    )
    assert policy.for_task("interview_preparation") == 120
    assert policy.for_task("greeting_generation") == 45
    ctx = ModelRequestContext(
        task_type="interview_preparation", output_schema=OUTPUTS[TaskType.INTERVIEW]
    )
    before = ctx.budget_remaining.model_dump()
    policy.for_task(ctx.task_type)
    assert ctx.budget_remaining.model_dump() == before


@pytest.mark.parametrize("value", [0, -1, 301, float("inf"), float("nan")])
def test_invalid_timeout_rejected(value):
    with pytest.raises(ValidationError):
        ModelTimeoutPolicy(task_seconds={"interview_preparation": value})


@pytest.mark.parametrize("task,seconds", [(TaskType.INTERVIEW, 120), (TaskType.GREETING, 60)])
@pytest.mark.parametrize(
    "error,phase",
    [
        (httpx.ReadTimeout, "read"),
        (httpx.ConnectTimeout, "connect"),
        (httpx.WriteTimeout, "write"),
        (httpx.PoolTimeout, "pool"),
    ],
)
async def test_per_request_timeout_native_sdk_and_safe_diagnostic(task, seconds, error, phase):
    requests = []

    def fail(request):
        requests.append(request)
        assert request.extensions["timeout"] == dict(
            connect=seconds, read=seconds, write=seconds, pool=seconds
        )
        raise error("secret /private/path synthetic@example.invalid", request=request)

    ctx = ModelRequestContext(task_type=task.value, output_schema=OUTPUTS[task])
    candidate = POLICY.select(ctx, registry(Settings(), True))
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
        async with AsyncOpenAI(
            api_key="synthetic", http_client=http, timeout=60, max_retries=0
        ) as sdk:
            provider = OpenAIProvider(
                sdk, ModelTimeoutPolicy(task_seconds={"interview_preparation": 120})
            )
            with pytest.raises(ModelGatewayError) as caught:
                await provider.generate(candidate, ctx, PromptSpec(task).task({}))
    exc = caught.value
    assert exc.code == "provider_timeout" and exc.retryable
    assert exc.usage is None
    diagnostic = exc.diagnostic
    assert diagnostic.failure_kind == "provider_timeout"
    assert diagnostic.request_timeout_seconds == seconds
    assert diagnostic.timeout_phase == phase
    assert diagnostic.timeout_policy_version == "model-request-timeout-v1"
    assert diagnostic.actual_model is None and diagnostic.response_id is None
    assert all(value not in diagnostic.model_dump_json() for value in ["secret", "/private", "@"])
    assert len(requests) == 1


async def test_composition_injects_policy_without_network():
    settings = Settings(
        live_enabled=True,
        openai_api_key="synthetic",
        tavily_api_key="synthetic",
        model_timeout_seconds=50,
        model_task_timeout_seconds={"interview_preparation": 120},
    )
    async with dependencies(settings, "live") as (gateway, _):
        provider = gateway.adapters["openai"]
        assert provider.timeout_policy.for_task("interview_preparation") == 120
        assert provider.timeout_policy.for_task("resume_tailoring") == 50
        assert provider.client.max_retries == 0
