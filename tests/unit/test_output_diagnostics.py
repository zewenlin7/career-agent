"""Native SDK parsing with synthetic HTTP responses; no external requests or private body logs."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from career_agent.config import Settings
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext
from career_agent.models.openai_adapter import OpenAIProvider
from career_agent.preparation.contracts import TaskType
from career_agent.preparation.prompts import PromptSpec
from career_agent.preparation.providers import POLICY, registry
from career_agent.resume.schemas import ResumeDocument


@pytest.mark.parametrize(
    "case,expected",
    [
        ("incomplete", "provider_incomplete"),
        ("refusal", "provider_refusal"),
        ("json", "structured_output_invalid"),
        ("short_text", "output_validation_failed"),
        ("duplicate", "output_validation_failed"),
        ("private_extra", "output_validation_failed"),
    ],
)
async def test_safe_native_failure_metadata(case, expected, caplog):
    document = json.loads(
        await asyncio.to_thread(Path("tests/fixtures/resumes/normal_one_page_zh_cn.json").read_text)
    )["document"]
    if case == "short_text":
        document["sections"][0]["items"][0]["short_text"] = document["sections"][0]["items"][0][
            "text"
        ]
    if case == "duplicate":
        document["sections"][1]["section_id"] = document["sections"][0]["section_id"]
    if case == "private_extra":
        document["private-name@example.invalid"] = "PRIVATE_BODY_SENTINEL"
    content = [{"type": "output_text", "text": json.dumps(document), "annotations": []}]
    if case in {"json", "incomplete"}:
        content[0]["text"] = '{"PRIVATE_BODY_SENTINEL":'
    if case == "refusal":
        content = [{"type": "refusal", "refusal": "PRIVATE_BODY_SENTINEL"}]
    payload = {
        "id": "resp_synthetic_failure",
        "object": "response",
        "created_at": 1,
        "model": "synthetic-actual-model",
        "status": "incomplete" if case == "incomplete" else "completed",
        "incomplete_details": {"reason": "max_output_tokens"} if case == "incomplete" else None,
        "output": [
            {
                "id": "msg_synthetic",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": content,
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 40,
            "total_tokens": 140,
            "input_tokens_details": {"cached_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 15},
        },
    }

    def respond(request):
        sent = json.loads(request.content)
        assert sent["text"]["format"]["strict"] is True
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        async with AsyncOpenAI(api_key="synthetic-only", max_retries=0, http_client=http) as sdk:
            ctx = ModelRequestContext(task_type=TaskType.TAILOR.value, output_schema=ResumeDocument)
            with pytest.raises(ModelGatewayError) as caught:
                await OpenAIProvider(sdk).generate(
                    POLICY.select(ctx, registry(Settings(), True)),
                    ctx,
                    PromptSpec(TaskType.TAILOR).task({}),
                )
    error = caught.value
    assert error.code == expected
    assert error.usage.input_tokens == 100 and error.usage.output_tokens == 40
    assert (
        error.usage.reasoning_tokens == 15 and error.usage.actual_model == "synthetic-actual-model"
    )
    assert error.diagnostic.response_id == "resp_synthetic_failure"
    if case == "short_text":
        assert error.diagnostic.validation_issues[0].message == "short_text must be shorter"
    if case == "incomplete":
        assert error.diagnostic.incomplete_reason == "max_output_tokens"
    if expected == "output_validation_failed":
        assert error.diagnostic.validation_issues
    metadata = error.diagnostic.model_dump_json() + caplog.text + str(error)
    for secret in [
        "PRIVATE_BODY_SENTINEL",
        "private-name@example.invalid",
        "input_value",
        '"input":',
    ]:
        assert secret not in metadata
