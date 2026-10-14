"""Real PostgreSQL trace/resume checks; HTTP responses are synthetic in-memory fixtures."""

import copy
import json
from dataclasses import replace
from uuid import UUID

import httpx
import pytest
from openai import AsyncOpenAI
from sqlalchemy import select
from test_agent_runtime import create, payload, resume
from test_preparation import inject
from test_preparation import prep_input as preparation_fixture

from career_agent.config import Settings
from career_agent.domain.rules import RunStatus
from career_agent.infrastructure import entities as e
from career_agent.models.gateway import ModelGateway
from career_agent.models.openai_adapter import OpenAIProvider
from career_agent.models.prompts import application_prompts
from career_agent.preparation.contracts import WorkflowRequest, WorkflowState
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.preparation.research import FixtureResearchAdapter
from career_agent.preparation.workflows import PreparationWorkflow
from career_agent.runtime.contracts import OutputDiagnostic
from career_agent.runtime.registry import REGISTRY

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("change", ["version", "missing_version"])
async def test_resume_rejects_changed_or_legacy_action_contract(
    client, prep_input, sessions, monkeypatch, change
):
    result = await create(
        client,
        payload(
            prep_input,
            goal="分别分析匹配，再生成招呼语。",
            authorized_scope={"targets": ["fit_analysis", "greeting_generation"]},
            action_slice=1,
        ),
    )
    assert result["state"]["phase"] == "ready"
    calls = result["state"]["usage"]["model_calls"]
    async with sessions.begin() as session:
        if change == "missing_version":
            checkpoint = await session.scalar(
                select(e.AgentCheckpoint)
                .where(e.AgentCheckpoint.run_id == UUID(result["run_id"]))
                .order_by(e.AgentCheckpoint.revision.desc())
            )
            data = copy.deepcopy(checkpoint.state)
            for progress in data["progress"]["actions"].values():
                progress["action"].pop("action_version", None)
            checkpoint.state = data
        else:
            monkeypatch.setitem(
                REGISTRY,
                "prepare_application",
                replace(REGISTRY["prepare_application"], version="business-action-v999"),
            )
    continued = await resume(client, result)
    assert continued["state"]["phase"] == "waiting_input"
    assert continued["state"]["pending_reason"] == "action_version_mismatch"
    assert continued["state"]["usage"]["model_calls"] == calls
    assert continued["state"]["usage"]["business_actions"] == 1
    assert (
        continued["state"]["progress"]["requested_targets"]["fit_analysis"]["status"] == "completed"
    )
    plans = (await client.get(f"/api/v1/agent-runs/{result['run_id']}/plans")).json()
    assert len(plans) == 1  # mismatch never silently replans under a newer contract


async def test_planning_replanning_success_trace_has_shared_metadata_and_diagnostic(
    client, prep_input, sessions
):
    class DiagnosticFixture(FixtureTaskProvider):
        async def generate(self, *args):
            result = await super().generate(*args)
            result.diagnostic = OutputDiagnostic(
                response_id="resp_synthetic_governance",
                actual_model="fixture-strong",
                response_status="completed",
                request_timeout_seconds=60,
                timeout_policy_version="model-timeouts-v1",
            )
            result.usage.cache_write_tokens = 17
            return result

    inject(client, DiagnosticFixture())
    data = payload(prep_input, targets=["greeting_generation"], goal="生成招呼语。")
    data["bindings"] = {k: v for k, v in prep_input.items() if k != "resume_revision_id"}
    result = await create(client, data)
    assert result["state"]["phase"] == "waiting_input"
    continued = await resume(client, result, resume_revision_id=prep_input["resume_revision_id"])
    assert continued["state"]["phase"] == "completed"
    async with sessions() as session:
        calls = list(await session.scalars(select(e.ModelCall)))
        assert {"goal_planning", "goal_replanning"} <= {c.task_type for c in calls}
        for call in calls:
            spec = application_prompts().resolve(call.task_type)
            assert all(call.versions[k] == v for k, v in spec.metadata.items())
            assert call.versions["provider"] == call.provider
            assert call.versions["model"] == call.model
            assert call.versions["model_policy_version"] == POLICY.version
            assert call.versions["workflow_version"]
            assert call.versions["output_diagnostic"]["response_id"] == "resp_synthetic_governance"
            assert call.usage["cache_write_tokens"] == 17
        steps = list(
            await session.scalars(select(e.AgentStep).where(e.AgentStep.action_id.is_not(None)))
        )
        assert steps
        for step in steps:
            spec = REGISTRY[step.action]
            assert step.versions["action_version"] == spec.version
            assert step.versions["input_schema_version"] == spec.args_schema_version
            assert step.versions["output_schema_version"] == spec.result_schema_version


async def test_mock_openai_cache_write_and_search_schema_reach_persisted_trace(
    client, prep_input, sessions, tmp_path
):
    # Run actual feature nodes: normal input validation, extraction, then explicit research.
    # Research is not added to the public deterministic orchestrator's target plan.
    def respond(request):
        body = json.loads(request.content)
        context = json.loads(body["input"][1]["content"])["context"]
        if "job" in context:
            output = {
                "requirements": [
                    {
                        "evidence_span": context["job"]["jd_text"].splitlines()[0],
                        "normalized_requirement": "具备 Python 开发经验",
                        "requirement_kind": "must",
                        "category": "engineering",
                        "skills": ["Python"],
                    }
                ]
            }
        else:
            output = {
                "locale": "zh-CN",
                "conclusions": [
                    {
                        "text": "公司提供开发工具服务。",
                        "evidence_refs": [context["evidence"][0]["id"]],
                    }
                ],
                "unknowns": [],
                "inference": [],
            }
        return httpx.Response(
            200,
            json={
                "id": "resp_synthetic_cache",
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
                    "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 40},
                    "output_tokens_details": {"reasoning_tokens": 5},
                },
            },
        )

    settings = Settings(_env_file=None, data_dir=tmp_path, live_enabled=False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        async with AsyncOpenAI(
            api_key="synthetic-not-a-key", max_retries=0, http_client=http
        ) as sdk:
            gateway = ModelGateway(
                registry(settings, False), POLICY, {"fixture": OpenAIProvider(sdk)}
            )
            async with sessions.begin() as session:
                request = WorkflowRequest(**prep_input, targets=["fit_analysis"])
                workflow = PreparationWorkflow(
                    session, settings, gateway, FixtureResearchAdapter(), request
                )
                workflow.run = e.AgentRun(
                    workflow="prepare_application",
                    workflow_version="preparation-v2",
                    status=RunStatus.RUNNING,
                )
                session.add(workflow.run)
                await session.flush()
                workflow.state = WorkflowState(
                    run_id=workflow.run.id,
                    workflow="prepare_application",
                    job_revision_id=request.job_revision_id,
                    profile_id=request.profile_id,
                    requested_outputs=[],
                )
                for node in ["validate_inputs", "extract_requirements", "research_company"]:
                    await workflow.node(node)
                assert not workflow.state.errors
                assert not workflow.state.warnings
                run_id = workflow.run.id
    trace = (await client.get(f"/api/v1/runs/{run_id}/calls")).json()
    assert len(trace["model_calls"]) == 2
    for call in trace["model_calls"]:
        assert call["status"] == "succeeded"
        assert call["usage"]["cache_write_tokens"] == 40
        assert call["usage"]["cached_tokens"] == 10
        assert call["usage"]["reasoning_tokens"] == 5
        assert call["usage"]["input_tokens"] == 100
        assert call["usage"]["output_tokens"] == 20
        spec = application_prompts().resolve(call["task_type"])
        assert all(call["versions"][k] == v for k, v in spec.metadata.items())
    assert trace["tool_calls"]
    for call in trace["tool_calls"]:
        assert call["tool_name"] == "company_search"
        assert call["tool_version"] == "company-search-v1"
        assert call["input_schema_version"] == "search-input-v1"
        assert call["output_schema_version"] == "search-result-v1"
