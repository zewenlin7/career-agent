"""Composition root; model names/pricing never appear in workflow business logic."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import httpx
from openai import AsyncOpenAI

from career_agent.config import Settings
from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ModelTier,
    PrivacyClass,
    ProviderResponse,
    TaskSpec,
)
from career_agent.models.control.controller import shared_controller
from career_agent.models.gateway import ModelGateway, ModelPolicy
from career_agent.models.openai_adapter import OpenAIProvider
from career_agent.models.timeouts import ModelTimeoutPolicy
from career_agent.preparation.contracts import TaskType
from career_agent.preparation.research import (
    FixtureResearchAdapter,
    ResearchAdapter,
    TavilyResearchAdapter,
)
from career_agent.runtime.contracts import Usage

POLICY = ModelPolicy(
    version="career-model-policy-v5",
    task_tiers={
        **{
            t.value: ModelTier.CHEAP if t == TaskType.EXTRACTION else ModelTier.STRONG
            for t in TaskType
        },
        "quality_judgement": ModelTier.STRONG,
        "goal_planning": ModelTier.STRONG,
        "goal_replanning": ModelTier.STRONG,
        "mock_interview_turn_generation": ModelTier.STRONG,
        "interview_group_debrief": ModelTier.STRONG,
        "interview_overall_debrief": ModelTier.STRONG,
    },
)


class FixtureTaskProvider:
    """Deterministic synthetic behavior, never advertised as real model capability."""

    async def generate(
        self, candidate: ModelCandidate, context: ModelRequestContext, task: TaskSpec
    ) -> ProviderResponse:
        if context.task_type == "quality_judgement":
            return ProviderResponse(
                output={
                    "criteria": [
                        {
                            "criterion": name,
                            "rating": "pass",
                            "confidence": "low",
                            "uncertainty_reasons": ["fixture_not_quality_evidence"],
                            "reason": "合成评估结果仅验证基础设施。",
                            "evidence_refs": task.inputs["evidence"][:1],
                        }
                        for name in task.inputs["rubric"]["criteria"]
                    ]
                },
                usage=Usage(input_tokens=100, output_tokens=100, estimated_cost=0),
                finish_reason="fixture_completed",
            )
        if context.task_type in {
            "mock_interview_turn_generation",
            "interview_group_debrief",
            "interview_overall_debrief",
        }:
            from career_agent.interview.fixture import output as fixture_output

            return ProviderResponse(
                output=fixture_output(context.task_type, task.inputs),
                usage=Usage(
                    input_tokens=100,
                    output_tokens=100,
                    cached_tokens=0,
                    cache_write_tokens=0,
                    reasoning_tokens=0,
                    estimated_cost=Decimal(0),
                    measurement="reported",
                ),
                finish_reason="fixture_completed",
            )
        if context.task_type in {"goal_planning", "goal_replanning"}:
            from career_agent.runtime.planner import fixture_plan

            return ProviderResponse(
                output=fixture_plan(task.inputs),
                usage=Usage(
                    input_tokens=100,
                    output_tokens=100,
                    estimated_cost=Decimal(0),
                    measurement="reported",
                ),
                finish_reason="fixture_completed",
            )
        c = task.inputs["context"]
        t = TaskType(context.task_type)
        output: dict[str, Any]
        if t == TaskType.EXTRACTION:
            output = {
                "requirements": [
                    {
                        "evidence_span": c["job"]["jd_text"].splitlines()[0],
                        "normalized_requirement": "岗位要求："
                        + c["job"]["jd_text"].splitlines()[0],
                        "requirement_kind": "must",
                        "category": "engineering",
                        "skills": [],
                    }
                ]
            }
        elif t == TaskType.RESEARCH:
            output = {
                "locale": "zh-CN",
                "conclusions": [
                    {
                        "text": "公开材料介绍开发工具与数据服务。",
                        "evidence_refs": [c["evidence"][0]["id"]],
                    }
                ],
                "unknowns": ["团队内部情况未知。"],
                "inference": [],
            }
        elif t == TaskType.FIT:
            output = {
                "locale": "zh-CN",
                "items": [
                    {
                        "requirement_ref": r["id"],
                        "status": "partial",
                        "fact_refs": [c["facts"][0]["id"]],
                        "explanation": "已有相关工程证据，仍需补充岗位特定信息。",
                        "missing_evidence": "需要进一步确认具体职责。",
                    }
                    for r in c["requirements"]
                ],
                "strong_matches": [],
                "partial_matches": [r["id"] for r in c["requirements"]],
                "evidence_missing": [],
                "clear_gaps": [],
            }
        elif t == TaskType.TAILOR:
            import copy

            output = {**copy.deepcopy(c["base_resume"]), **c["identity"]}
            for section in output["sections"]:
                for item in section["items"]:
                    item["requirement_refs"] = [c["requirements"][0]["id"]]
        elif t == TaskType.COMPRESS:
            import copy

            output = copy.deepcopy(c["variant"])
            for section in output["sections"]:
                for item in section["items"]:
                    if item.get("short_text"):
                        item["text"] = item["short_text"]
                        item["short_text"] = None
        elif t == TaskType.GREETING:
            output = {
                "locale": "zh-CN",
                "greeting_text": "您好，希望进一步交流岗位要求。"
                + c["facts"][0]["statement"][:300],
                "fact_refs": [c["facts"][0]["id"]],
                "requirement_refs": [r["id"] for r in c["requirements"][:1]],
            }
        else:
            q = {
                "question": "如何解释项目中的一致性设计？",
                "why_likely": "岗位涉及工程实践。",
                "what_is_being_tested": "设计与验证能力。",
                "answer_outline": ["结合已验证项目说明设计与测试。"],
                "related_fact_refs": [c["facts"][0]["id"]],
                "related_project_refs": [],
                "related_requirement_refs": [c["requirements"][0]["id"]],
            }
            output = {
                "locale": "zh-CN",
                "likely_topics": ["工程设计"],
                "technical_questions": [q],
                "project_deep_dive_questions": [q],
                "behavioral_questions": [],
                "company_specific_questions": [],
                "knowledge_gaps": ["确认团队技术细节。"],
                "questions_to_ask_interviewer": ["团队如何验证系统可靠性？"],
            }
        return ProviderResponse(
            output=output,
            usage=Usage(
                input_tokens=100,
                output_tokens=100,
                estimated_cost=Decimal(0),
                measurement="reported",
            ),
            finish_reason="fixture_completed",
        )


def registry(settings: Settings, live: bool) -> list[ModelCandidate]:
    return [
        ModelCandidate(
            provider="openai" if live else "fixture",
            model=model if live else f"fixture-{tier}",
            tier=tier,
            capabilities=frozenset({"structured_output"}),
            allowed_privacy=frozenset({PrivacyClass.SYNTHETIC, PrivacyClass.PRIVATE}),
            input_cost_per_million=inp if live else Decimal(0),
            cached_input_cost_per_million=cached if live else Decimal(0),
            output_cost_per_million=out if live else Decimal(0),
            pricing_version=settings.pricing_version,
        )
        for tier, model, inp, cached, out in [
            (
                ModelTier.CHEAP,
                settings.cheap_model,
                settings.cheap_input_price,
                settings.cheap_cached_price,
                settings.cheap_output_price,
            ),
            (
                ModelTier.STRONG,
                settings.strong_model,
                settings.strong_input_price,
                settings.strong_cached_price,
                settings.strong_output_price,
            ),
        ]
    ]


@asynccontextmanager
async def dependencies(
    settings: Settings, mode: str, *, require_research: bool = True
) -> AsyncIterator[tuple[ModelGateway, ResearchAdapter]]:
    if mode == "fixture":
        yield (
            ModelGateway(registry(settings, False), POLICY, {"fixture": FixtureTaskProvider()}),
            FixtureResearchAdapter(),
        )
        return
    if (
        not settings.live_enabled
        or not settings.openai_api_key
        or (require_research and not settings.tavily_api_key)
    ):
        raise ModelGatewayError("live_configuration_missing")
    # Only two tiers registered. Premium flag is reserved and never enables automatic routing.
    async with (
        AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            base_url="https://api.openai.com/v1",
            max_retries=0,
            timeout=settings.model_timeout_seconds,
        ) as client,
        httpx.AsyncClient(follow_redirects=False, trust_env=False) as http,
    ):
        yield (
            ModelGateway(
                registry(settings, True),
                ModelPolicy(POLICY.version, POLICY.task_tiers, settings.task_model_policies),
                {
                    "openai": OpenAIProvider(
                        client,
                        ModelTimeoutPolicy(
                            default_seconds=settings.model_timeout_seconds,
                            task_seconds=settings.model_task_timeout_seconds,
                        ),
                        control_policy=settings.runtime_control,
                    )
                },
                controller=shared_controller(settings.runtime_control),
            ),
            TavilyResearchAdapter(
                settings.tavily_api_key.get_secret_value(), http, settings.search_timeout_seconds
            )
            if require_research and settings.tavily_api_key
            else FixtureResearchAdapter(),
        )
