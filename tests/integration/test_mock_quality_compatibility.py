"""Prompt-only upgrade preserves accepted v7 decisions; Eval stays honestly offline."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from test_mock_decisions import Decisions, call
from test_preparation import inject
from test_preparation import prep_input as preparation_fixture

from career_agent.config import Settings
from career_agent.evaluation import entities as q
from career_agent.evaluation import recording
from career_agent.evaluation.contracts import EvalRunRequest, EvalSuite
from career_agent.evaluation.mock_quality import quality_cases
from career_agent.evaluation.runner import EvalRunner
from career_agent.evaluation.store import put_case, put_suite
from career_agent.models.gateway import ModelGateway
from career_agent.models.prompts import PromptRegistry, application_prompts
from career_agent.preparation.providers import POLICY, registry
from career_agent.preparation.research import FixtureResearchAdapter

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("decision", ["follow_up", "finish"])
async def test_v7_accepted_decision_recovers_under_v8_without_redispatch(
    client,
    prep_input,
    sessions,
    monkeypatch,
    decision,
):
    old = json.loads((Path(__file__).parents[1] / "fixtures/mock_prompt_v7.json").read_text())
    specs = application_prompts().specs
    current = specs["mock_interview_turn_generation"]
    specs[current.task_type] = replace(
        current,
        instruction=old["mock_instruction"],
        prompt_version=old["mock_metadata"]["prompt_version"],
    )
    assert specs[current.task_type].metadata == old["mock_metadata"]
    provider = Decisions(["primary", decision, "primary"])

    @asynccontextmanager
    async def dependencies(settings, mode):
        yield (
            ModelGateway(
                registry(settings, False),
                POLICY,
                {"fixture": provider},
                prompts=PromptRegistry(list(specs.values())),
            ),
            FixtureResearchAdapter(),
        )

    client._transport.app.state.preparation_dependencies = dependencies
    policy = {
        "mode": "custom",
        "primary_target": 1 if decision == "finish" else 3,
        "followup_max": 1,
    }
    row = (
        await client.post("/api/v1/mock-interviews", json={"context": prep_input, "policy": policy})
    ).json()
    row = await call(client, row, "generate")
    frozen = row["context"]
    original = recording.bind_artifact

    async def fail(*args, **kwargs):
        raise OperationalError("synthetic save fault", {}, None)

    monkeypatch.setattr(recording, "bind_artifact", fail)
    row = await call(
        client,
        row,
        "answers",
        pending_question_id=row["pending_question_id"],
        answer="通过事务和唯一键处理并发与重复请求。",
    )
    assert row["stop_reason"] == "artifact_save_failed"
    assert len(provider.requests) == 2
    async with sessions() as session:
        invocation = await session.scalar(
            select(q.InvocationRow).where(
                q.InvocationRow.data["parent_run_id"].astext == row["run_id"],
                q.InvocationRow.data["output_ref"].astext.is_(None),
            )
        )
        assert invocation is not None
        invocation_id, before = invocation.id, dict(invocation.data)
        assert before["provenance"]["prompt_version"] == "mock_interview_turn_generation_v7"
        assert before["output"]["action"] == ("finish" if decision == "finish" else "ask")
    monkeypatch.setattr(recording, "bind_artifact", original)
    inject(client, provider)
    row = await call(client, row, "recover")
    assert row["status"] == ("completed" if decision == "finish" else "waiting_answer")
    assert len(row["turns"]) == (1 if decision == "finish" else 2)
    assert len(provider.requests) == 2 and row["context"] == frozen
    async with sessions() as session:
        after = (await session.get(q.InvocationRow, invocation_id)).data
        assert {k: v for k, v in after.items() if k != "output_ref"} == {
            k: v for k, v in before.items() if k != "output_ref"
        }
    if decision == "follow_up":
        row = await call(
            client,
            row,
            "answers",
            pending_question_id=row["pending_question_id"],
            answer="已补充边界验证。",
        )
        assert provider.requests[-1][0].prompt_version == "mock_interview_turn_generation_v8"
        assert (
            provider.requests[-1][0].input_schema_version
            == old["mock_metadata"]["input_schema_version"]
        )
        assert row["context"] == frozen


async def test_quality_suite_persists_legal_execution_and_quality_misses_separately(
    sessions, migrated_url
):
    cases = quality_cases()
    suite = EvalSuite(
        suite_id="mock-decision-quality",
        version=1,
        members=[{"case_id": c.case_id, "case_version": c.case_version} for c in cases],
    )
    async with sessions.begin() as session:
        for case in cases:
            await put_case(session, case)
        await put_suite(session, suite)
    runner = EvalRunner(
        sessions, Settings(database_url=SecretStr(migrated_url), live_enabled=False)
    )
    run_id = await runner.create(EvalRunRequest(suite_id=suite.suite_id, suite_version=1))
    await runner.execute(run_id)
    async with sessions() as session:
        trials = list(
            await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == run_id))
        )
        assert len(trials) == 9
        assert sum(t.status == "completed" for t in trials) == 5
        assert sum(t.status == "failed" for t in trials) == 4
        for trial in trials:
            assert trial.result["output"]["valid"] is True
            checks = {c["check_id"]: c for c in trial.result["checks"]}
            assert checks["execution_legal"]["status"] == "pass"
            if trial.status == "failed":
                assert checks["decision_acceptable"]["category"] == "quality"
                assert checks["decision_acceptable"]["status"] == "fail"
        invocations = list(
            await session.scalars(
                select(q.InvocationRow).where(q.InvocationRow.trial_id.in_([t.id for t in trials]))
            )
        )
        assert len(invocations) == 9
        for invocation in invocations:
            assert (
                invocation.data["provenance"]["prompt_version"]
                == "mock_interview_turn_generation_v8"
            )
            assert "decision_quality" not in invocation.data["input_snapshot"]
