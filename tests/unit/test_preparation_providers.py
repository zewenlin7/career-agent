"""Offline HTTP contracts: never make a paid API request."""

import json
from decimal import Decimal

import httpx
import pytest
from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema

from career_agent.config import Settings
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, ModelTier
from career_agent.models.openai_adapter import OpenAIProvider
from career_agent.preparation.budget import BudgetLedger, input_bound
from career_agent.preparation.contracts import Accounting, RunLimits, TaskType
from career_agent.preparation.prompts import OUTPUTS, PromptSpec
from career_agent.preparation.providers import POLICY, registry
from career_agent.preparation.research import SearchInput, TavilyResearchAdapter
from career_agent.runtime.contracts import Usage


def context(task=TaskType.EXTRACTION):
    return ModelRequestContext(
        task_type=task.value, workflow="prepare_application", output_schema=OUTPUTS[task]
    )


@pytest.mark.parametrize("task", list(TaskType))
def test_native_schema_and_static_routing(task):
    schema = to_strict_json_schema(OUTPUTS[task])
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(schema["required"])
    candidate = POLICY.select(context(task), registry(Settings(), True))
    assert candidate.tier == (ModelTier.CHEAP if task == TaskType.EXTRACTION else ModelTier.STRONG)
    assert all(c.tier != ModelTier.PREMIUM for c in registry(Settings(premium_enabled=True), True))
    spec = PromptSpec(task)
    assert spec.digest == PromptSpec(task).digest and len(spec.digest) == 64
    assert "quoted data/evidence" in spec.instruction
    with pytest.raises(ValueError, match="invalid_context_block"):
        spec.task({"output_path": "/private/forbidden"})


def test_unsupported_capability_and_context_size():
    ctx = context().model_copy(update={"required_capabilities": frozenset({"shell"})})
    with pytest.raises(ModelGatewayError, match="no_eligible_model"):
        POLICY.select(ctx, registry(Settings(), True))
    task = PromptSpec(TaskType.EXTRACTION).task({"job": {"jd_text": "中" * 80000}})
    with pytest.raises(ModelGatewayError, match="context_too_large"):
        input_bound(context(), task)


def test_budget_unknown_usage_is_reserved_not_zero():
    accounting = Accounting()
    ledger = BudgetLedger(RunLimits(max_model_calls=1), accounting)
    candidate = POLICY.select(context(), registry(Settings(), True))
    reservation = ledger.reserve_model(candidate, 1000, 100)
    result = ledger.settle(reservation, Usage())
    assert result.measurement == "unknown"
    assert result.input_tokens is None and result.estimated_cost is None
    assert result.actual_billed_cost_usd is None
    assert result.budget_reserved_usd > 0
    assert accounting.unknown_usage_attempts == 1
    assert accounting.input_tokens == 0 and accounting.estimated_cost == 0
    assert accounting.reserved_input_tokens == 1000 and accounting.budget_reserved_usd > 0
    with pytest.raises(ModelGatewayError, match="budget_exhausted"):
        ledger.reserve_model(candidate, 1000, 100)


def test_cost_and_search_hard_limits():
    usage = Accounting()
    ledger = BudgetLedger(RunLimits(max_estimated_cost=Decimal("0.01")), usage)
    ledger.reserve_search(Decimal("0.008"))
    with pytest.raises(ModelGatewayError, match="budget_exhausted"):
        ledger.reserve_search(Decimal("0.008"))
    assert usage.search_calls == 1


@pytest.mark.parametrize("cached_price", [Decimal("0"), Decimal("0.01")])
async def test_responses_native_schema_and_usage(cached_price):
    output = {
        "requirements": [
            {
                "evidence_span": "Python",
                "normalized_requirement": "掌握 Python",
                "requirement_kind": "must",
                "category": "skill",
                "skills": ["Python"],
            }
        ]
    }
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/responses"
        assert body["store"] is False and "tools" not in body
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "id": "resp_synthetic",
                "created_at": 1,
                "model": body["model"],
                "object": "response",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_synthetic",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(output), "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "input_tokens_details": {"cached_tokens": 10},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        async with AsyncOpenAI(
            api_key="synthetic-not-a-key", max_retries=0, http_client=http
        ) as sdk:
            candidate = POLICY.select(context(), registry(Settings(), True))
            candidate = candidate.model_copy(update={"cached_input_cost_per_million": cached_price})
            result = await OpenAIProvider(sdk).generate(
                candidate,
                context(),
                PromptSpec(TaskType.EXTRACTION).task({"job": {"jd_text": "Python"}}),
            )
    assert result.output == output
    assert result.usage.input_tokens == 100 and result.usage.cached_tokens == 10
    assert result.usage.reasoning_tokens == 0
    assert result.usage.actual_model == candidate.model
    assert result.usage.measurement == "reported" and result.usage.estimated_cost > 0
    assert result.usage.estimated_cost == (
        90 * candidate.input_cost_per_million
        + 10 * cached_price
        + 20 * candidate.output_cost_per_million
    ) / Decimal(1000000)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "status,code,retryable",
    [(429, "provider_429", True), (500, "provider_5xx", True), (400, "provider_rejected", False)],
)
async def test_provider_raw_error_redacted(status, code, retryable):
    def respond(request):
        return httpx.Response(
            status,
            json={"error": {"message": "/private/person/key secret synthetic-pii@example.invalid"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        async with AsyncOpenAI(
            api_key="synthetic-not-a-key", max_retries=0, http_client=http
        ) as sdk:
            with pytest.raises(ModelGatewayError) as error:
                await OpenAIProvider(sdk).generate(
                    POLICY.select(context(), registry(Settings(), True)),
                    context(),
                    PromptSpec(TaskType.EXTRACTION).task({"job": {}}),
                )
    assert str(error.value) == code and error.value.retryable == retryable


async def test_tavily_normalization_and_no_provider_leak():
    def respond(request):
        body = json.loads(request.content)
        assert body["search_depth"] == "basic" and body["max_results"] == 5
        assert body["include_raw_content"] is False and body["include_answer"] is False
        return httpx.Response(
            200,
            json={
                "answer": "never use this",
                "results": [
                    {
                        "url": "https://example.invalid/about",
                        "title": "公司",
                        "content": "公开合成资料",
                        "score": 0.9,
                        "raw_content": "do not leak",
                    },
                    {"url": "file:///private/data", "content": "blocked"},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await TavilyResearchAdapter("synthetic-key", http).search(
            SearchInput(query="公司")
        )
    assert len(result.evidence) == 1
    assert result.evidence[0].trust_level == "untrusted_external"
    assert "score" not in result.model_dump_json() and "raw_content" not in result.model_dump_json()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, text="private secret"),
        httpx.Response(200, json={"wrong": []}),
        httpx.Response(200, content=b"x" * 200001),
    ],
)
async def test_tavily_failure_safe(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as http:
        with pytest.raises(ModelGatewayError) as error:
            await TavilyResearchAdapter("synthetic", http).search(SearchInput(query="公司"))
    assert str(error.value) in {"research_failed", "research_response_too_large"}


def test_reported_usage_releases_reservation_without_claiming_invoice():
    accounting = Accounting()
    ledger = BudgetLedger(RunLimits(), accounting)
    candidate = POLICY.select(context(), registry(Settings(), True))
    reserved = ledger.reserve_model(candidate, 1000, 100)
    actual = Usage(
        input_tokens=100, output_tokens=20, estimated_cost=Decimal("0.001"), measurement="reported"
    )
    settled = ledger.settle(reserved, actual)
    assert accounting.reserved_input_tokens == accounting.reserved_output_tokens == 0
    assert accounting.budget_reserved_usd == 0
    assert accounting.input_tokens == 100 and accounting.output_tokens == 20
    assert accounting.estimated_cost == accounting.budget_consumed_usd == Decimal("0.001")
    assert settled.actual_billed_cost_usd is None and settled.billing_tier == "unknown"


def test_unknown_cost_still_blocks_budget_and_keeps_usage_unknown():
    accounting = Accounting()
    candidate = POLICY.select(context(), registry(Settings(), True))
    ledger = BudgetLedger(RunLimits(max_estimated_cost=Decimal("0.00015")), accounting)
    reserved = ledger.reserve_model(candidate, 1000, 100)
    ledger.settle(reserved, None)
    assert accounting.estimated_cost == 0
    assert accounting.budget_consumed_usd == Decimal("0.00015")
    with pytest.raises(ModelGatewayError, match="budget_exhausted"):
        ledger.reserve_model(candidate, 1, 1)


@pytest.mark.parametrize("succeeded", [True, False])
def test_tavily_call_retail_estimate_is_not_credits_or_cash(succeeded):
    accounting = Accounting()
    ledger = BudgetLedger(RunLimits(), accounting)
    reserved = ledger.reserve_search(Decimal("0.008"))
    result = ledger.settle_search(reserved, succeeded=succeeded)
    assert result.search_calls == accounting.search_calls == 1
    assert result.credits_used is None and result.actual_billed_cost_usd is None
    assert result.billing_tier == "unknown"
    assert result.estimated_cost == (Decimal("0.008") if succeeded else None)
    assert result.budget_reserved_usd == (Decimal(0) if succeeded else Decimal("0.008"))
    assert accounting.budget_consumed_usd == Decimal("0.008")
