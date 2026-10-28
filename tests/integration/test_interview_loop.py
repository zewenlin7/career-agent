from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import prep_input as preparation_fixture

from career_agent.infrastructure import entities as e

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


async def actual_session(client):
    job = (
        await client.post(
            "/api/v1/jobs",
            json={"company_name": "合成公司", "title": "开发", "jd_text": "熟悉 Python。"},
        )
    ).json()
    response = await client.post(
        "/api/v1/interviews",
        json={"application_id": job["application_id"], "round_name": "技术一面"},
    )
    assert response.status_code == 201, response.text
    return response.json(), job


async def append(client, row, order, parent=None, answer="使用测试验证实现。"):
    response = await client.post(
        f"/api/v1/interviews/{row['id']}/entries",
        json={
            "expected_revision": row["content_revision"],
            "entry": {
                "entry_id": str(uuid4()),
                "order": order,
                "kind": "follow_up" if parent else "primary",
                "primary_entry_id": parent,
                "question": "如何验证设计？",
                "answer": answer,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_actual_cas_relations_and_snapshot(client):
    row, job = await actual_session(client)
    row = await append(client, row, 1)
    primary = row["entries"][0]["entry_id"]
    row = await append(client, row, 2, primary)
    row = await append(client, row, 3)
    for parent in [str(uuid4()), row["entries"][1]["entry_id"]]:
        bad = await client.post(
            f"/api/v1/interviews/{row['id']}/entries",
            json={
                "expected_revision": row["content_revision"],
                "entry": {
                    "order": 4,
                    "kind": "follow_up",
                    "primary_entry_id": parent,
                    "question": "追问",
                    "answer": None,
                },
            },
        )
        assert bad.status_code == 422
    note = await client.post(
        f"/api/v1/interviews/{row['id']}/notes",
        json={"expected_revision": row["content_revision"], "text": "保留原始笔记。"},
    )
    assert note.status_code in (200, 201), note.text
    row = (await client.get(f"/api/v1/interviews/{row['id']}")).json()
    debrief = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "actual",
            "interview_id": row["id"],
            "expected_source_revision": row["content_revision"],
            "question_analysis": "all",
            "overall_analysis": True,
        },
    )
    assert debrief.status_code == 201, debrief.text
    frozen = debrief.json()
    update = {"expected_revision": row["content_revision"], "entries": [], "status": "draft"}
    assert (await client.patch(f"/api/v1/interviews/{row['id']}", json=update)).status_code == 200
    assert (await client.patch(f"/api/v1/interviews/{row['id']}", json=update)).status_code == 409
    historical = (await client.get(f"/api/v1/interview-debriefs/{frozen['id']}")).json()
    assert historical["snapshot"] == frozen["snapshot"]
    assert len(historical["snapshot"]["entries"]) == 3
    assert historical["snapshot"]["notes"]
    stream = await client.post(f"/api/v1/interview-debriefs/{frozen['id']}/execute")
    assert stream.status_code == 200, stream.text
    result = (await client.get(f"/api/v1/interview-debriefs/{frozen['id']}")).json()
    assert result["status"] == "completed", result
    assert [a["kind"] for a in result["artifacts"]] == ["group", "group", "overall"]
    events = (await client.get(f"/api/v1/interview-debriefs/{frozen['id']}/events")).json()
    assert events[-1]["event"] == "run_completed"
    assert (await client.get(f"/api/v1/applications/{job['application_id']}")).json()[
        "status"
    ] == "tracking"
    listed = (
        await client.get(
            "/api/v1/interviews",
            params={"application_id": job["application_id"], "status": "draft"},
        )
    ).json()
    assert len(listed) == 1 and listed[0]["entries"] == []


@pytest.mark.parametrize(
    "mode,primary,follow", [("quick", 3, 1), ("standard", 5, 3), ("long", 8, 5), ("custom", 2, 0)]
)
async def test_mock_exact_target_and_idempotency(
    client, sessions, prep_input, mode, primary, follow
):
    policy = {"mode": mode}
    if mode == "custom":
        policy.update(primary_target=primary, followup_max=follow)
    response = await client.post(
        "/api/v1/mock-interviews", json={"context": prep_input, "policy": policy}
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["status"] == "ready_to_generate" and row["turns"] == []
    path = f"/api/v1/mock-interviews/{row['id']}"
    payload = {"expected_revision": row["revision"], "request_id": str(uuid4())}
    response = await client.post(path + "/generate", json=payload)
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["status"] == "waiting_answer", row
    duplicate = (await client.post(path + "/generate", json=payload)).json()
    assert duplicate == row
    for index in range(primary + follow):
        assert row["status"] == "waiting_answer", row
        payload = {
            "expected_revision": row["revision"],
            "request_id": str(uuid4()),
            "pending_question_id": row["pending_question_id"],
            "answer": f"我使用测试验证第{index}项设计。",
        }
        response = await client.post(path + "/answers", json=payload)
        assert response.status_code == 200, response.text
        row = response.json()
        assert (await client.post(path + "/answers", json=payload)).json() == row
    assert row["status"] == "completed" and row["completion_type"] == "target_reached"
    assert row["primary_question_count"] == primary
    assert row["followup_count"] == follow
    assert row["interviewer_turn_count"] == primary + follow
    assert all(t["answer"] for t in row["turns"])
    async with sessions() as session:
        calls = list(
            await session.scalars(
                select(e.ModelCall)
                .join(e.AgentStep)
                .where(e.AgentStep.run_id == UUID(row["run_id"]))
            )
        )
        assert len(calls) == primary + follow
        assert all(c.task_type == "mock_interview_turn_generation" for c in calls)


async def test_mock_failure_preserves_answer_and_explicit_retry(client, prep_input):
    from test_preparation import inject

    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        count = 0
        inputs = []

        async def generate(self, candidate, context, task):
            self.count += 1
            self.inputs.append(task.inputs)
            if self.count == 2:
                raise ModelGatewayError("provider_timeout", retryable=True)
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}"
    row = (
        await client.post(
            path + "/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    ).json()
    request = {
        "expected_revision": row["revision"],
        "request_id": str(uuid4()),
        "pending_question_id": row["pending_question_id"],
        "answer": "这是不可变的首次回答。",
    }
    row = (await client.post(path + "/answers", json=request)).json()
    assert row["status"] == "ready_to_generate", row
    assert row["turns"][0]["answer"] == request["answer"]
    assert provider.count == 2
    assert (await client.post(path + "/answers", json=request)).json() == row
    row = (
        await client.post(
            path + "/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    ).json()
    assert row["status"] == "waiting_answer" and provider.count == 3
    calls = (await client.get(f"/api/v1/runs/{row['run_id']}/calls")).json()["model_calls"]
    turn = row["turns"][-1]
    attempts = sorted(
        [c for c in calls if c["logical_operation_id"] == turn["logical_operation_id"]],
        key=lambda c: c["attempts"],
    )
    assert [c["attempts"] for c in attempts] == [1, 2]
    assert [c["status"] for c in attempts] == ["failed", "succeeded"]
    assert turn["accepted_model_call_id"] == attempts[-1]["id"]
    assert attempts[-1]["versions"]["retry_reason"] == "explicit_generation_retry"

    row = (
        await client.post(
            path + "/answers",
            json={
                "expected_revision": row["revision"],
                "request_id": str(uuid4()),
                "pending_question_id": row["pending_question_id"],
                "answer": "这是追问的回答。",
            },
        )
    ).json()
    assert "这是不可变的首次回答。" not in str(provider.inputs[-1])
    assert "这是追问的回答。" in str(provider.inputs[-1])
    row = (
        await client.post(
            path + "/end", json={"expected_revision": row["revision"], "request_id": str(uuid4())}
        )
    ).json()
    assert row["completion_type"] == "user_ended_early"
    debrief = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "mock",
            "interview_id": row["id"],
            "expected_source_revision": row["revision"],
            "overall_analysis": True,
        },
    )
    assert debrief.status_code == 201, debrief.text
    assert debrief.json()["snapshot"]["completion_type"] == "user_ended_early"


@pytest.mark.parametrize(
    "analysis,overall,count",
    [
        ("single", False, 1),
        ("all", False, 2),
        ("none", True, 1),
        ("single", True, 2),
        ("all", True, 3),
    ],
)
async def test_debrief_independent_targets(client, analysis, overall, count):
    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    row = await append(client, row, 2, answer=None)
    payload = {
        "source_kind": "actual",
        "interview_id": row["id"],
        "expected_source_revision": row["content_revision"],
        "question_analysis": analysis,
        "overall_analysis": overall,
    }
    if analysis == "single":
        payload["primary_entry_id"] = row["entries"][0]["entry_id"]
    response = await client.post("/api/v1/interview-debriefs", json=payload)
    assert response.status_code == 201, response.text
    run = response.json()
    assert len(run["artifacts"]) == count
    stream = await client.post(f"/api/v1/interview-debriefs/{run['id']}/execute")
    assert "run_completed" in stream.text, stream.text
    run = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    assert run["status"] == "completed"
    assert all(a["status"] == "completed" for a in run["artifacts"])


async def test_debrief_retry_partial_and_shared_quota(client, sessions):
    from test_preparation import inject

    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        calls = 0

        async def generate(self, candidate, context, task):
            self.calls += 1
            if context.task_type == "interview_group_debrief":
                raise ModelGatewayError("provider_timeout", retryable=True)
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    payload = {
        "source_kind": "actual",
        "interview_id": row["id"],
        "expected_source_revision": row["content_revision"],
        "question_analysis": "all",
        "overall_analysis": True,
    }
    run = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    stream = await client.post(f"/api/v1/interview-debriefs/{run['id']}/execute")
    assert "group_retrying" in stream.text and "run_partial" in stream.text, stream.text
    result = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    assert [a["status"] for a in result["artifacts"]] == ["failed", "completed"]
    assert provider.calls == 3
    inject(client)
    payload.update(
        question_analysis="single",
        overall_analysis=False,
        primary_entry_id=row["entries"][0]["entry_id"],
    )
    retry = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    assert (
        "run_completed"
        in (await client.post(f"/api/v1/interview-debriefs/{retry['id']}/execute")).text
    )
    payload.update(question_analysis="all", overall_analysis=True)
    payload.pop("primary_entry_id")
    # Ordinary duplicate create is idempotent; another execution is explicit regeneration.
    capped = (
        await client.post(
            f"/api/v1/interview-debriefs/{run['id']}/regenerate",
            json={"question_analysis": "all", "overall_analysis": True},
        )
    ).json()
    async with sessions.begin() as session:
        stored = await session.get(e.DebriefRun, UUID(capped["id"]))
        stored.limits = {**stored.limits, "max_model_calls": 1}
    await client.post(f"/api/v1/interview-debriefs/{capped['id']}/execute")
    capped = (await client.get(f"/api/v1/interview-debriefs/{capped['id']}")).json()
    assert capped["status"] == "partial"
    assert capped["usage"]["model_calls"] == 1


async def test_bounded_concurrency_commit_before_event_and_display_order(client, sessions):
    import asyncio

    from test_preparation import inject

    from career_agent.interview.debrief import DebriefService
    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        active = 0
        maximum = 0
        overlap = asyncio.Event()

        async def generate(self, candidate, context, task):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            if self.active == 2:
                self.overlap.set()
            try:
                await asyncio.wait_for(self.overlap.wait(), timeout=5)
                await asyncio.sleep(
                    0.01 if context.task_type == "interview_overall_debrief" else 0.15
                )
                return await super().generate(candidate, context, task)
            finally:
                self.active -= 1

    provider = Provider()
    inject(client, provider)
    app = client._transport.app
    app.state.settings.interview_policy.concurrency = 2
    row, _ = await actual_session(client)
    for index in range(1, 5):
        row = await append(client, row, index)
    run = (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                "source_kind": "actual",
                "interview_id": row["id"],
                "expected_source_revision": row["content_revision"],
                "question_analysis": "all",
                "overall_analysis": True,
            },
        )
    ).json()
    events = []
    async with app.state.preparation_dependencies(app.state.settings, "fixture") as (gateway, _):
        service = DebriefService(sessions, app.state.settings, gateway)
        async for event in service.execute(UUID(run["id"])):
            events.append(event)
            if event["event"] in {"group_completed", "overall_completed"}:
                async with sessions() as session:
                    artifact = await session.get(e.DebriefArtifact, UUID(event["artifact_id"]))
                    assert artifact.status == "completed" and artifact.data is not None
                    call = await session.get(e.ModelCall, artifact.accepted_model_call_id)
                    assert call.status.value == "succeeded"
                    assert call.logical_operation_id == artifact.logical_operation_id
                    assert call.task_type == (
                        "interview_overall_debrief"
                        if artifact.kind == "overall"
                        else "interview_group_debrief"
                    )

    assert provider.maximum == 2
    completed = [v for v in events if v["event"] in {"group_completed", "overall_completed"}]
    assert completed[0]["event"] == "overall_completed"
    assert completed[0]["display_order"] == 5
    result = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    assert [a["group_index"] for a in result["artifacts"]] == [1, 2, 3, 4, None]
    assert result["usage"]["model_calls"] == 5
    assert result["usage"]["reserved_seconds"] == 0
    async with sessions() as session:
        parent = await session.get(e.AgentRun, UUID(result["run_id"]))
        assert parent.consumed_usage["input_tokens"] == result["usage"]["input_tokens"] == 500


async def test_debrief_context_limit_and_missing_resume(client, prep_input):
    from career_agent.interview.policy import CallPolicy

    app = client._transport.app
    # Reject the complete oversized source before creating a run; never silently truncate.
    app.state.settings.interview_policy.actual_group = CallPolicy(max_input_tokens=1000)
    row, _ = await actual_session(client)
    row = await append(client, row, 1, answer="合成回答" * 1000)
    response = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "actual",
            "interview_id": row["id"],
            "expected_source_revision": row["content_revision"],
            "question_analysis": "all",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "debrief_input_too_large"
    context = dict(prep_input)
    context.pop("resume_revision_id")
    assert (
        await client.post("/api/v1/mock-interviews", json={"context": context})
    ).status_code == 422


async def test_migration_backfills_legacy_interviews(client, sessions, migrated_url):
    import asyncio

    from alembic import command
    from alembic.config import Config

    row, _ = await actual_session(client)
    await client.post(
        f"/api/v1/interviews/{row['id']}/notes",
        json={"expected_revision": 1, "text": "保留历史自由笔记。"},
    )
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "f730b2c01231")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    result = (await client.get(f"/api/v1/interviews/{row['id']}")).json()
    assert result["content_revision"] == 1 and result["entries"] == []
    assert result["notes"][0]["text"] == "保留历史自由笔记。"
    await asyncio.to_thread(command.check, cfg)


async def test_illegal_model_kind_no_turn_and_trace_private(client, sessions, prep_input):
    from test_preparation import inject

    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            response.output["kind"] = "follow_up"
            return response

    inject(client, Provider())
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    row = (
        await client.post(
            f"/api/v1/mock-interviews/{row['id']}/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    ).json()
    assert row["status"] == "ready_to_generate" and row["turns"] == []
    assert row["stop_reason"] == "illegal_question_kind"
    async with sessions() as session:
        calls = list(
            await session.scalars(
                select(e.ModelCall)
                .join(e.AgentStep)
                .where(e.AgentStep.run_id == UUID(row["run_id"]))
            )
        )
        assert len(calls) == 1
        metadata = calls[0].versions
        assert metadata["output_diagnostic"]["failure_kind"] == "output_guardrail_failed"
        assert metadata["prompt_hash"] and metadata["prompt_version"]
        trace = str(metadata) + str(calls[0].usage)
        assert "隐私姓名" not in trace and "synthetic-pii" not in trace
        assert "13800138000" not in trace and "如何" not in trace


async def test_debrief_schema_repair_and_disconnect(client, sessions):
    import asyncio

    from test_preparation import inject

    from career_agent.interview.debrief import DebriefService
    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        calls = 0
        active = 0

        async def generate(self, candidate, context, task):
            self.calls += 1
            self.active += 1
            try:
                if self.calls > 2:
                    await asyncio.sleep(10)
                response = await super().generate(candidate, context, task)
                if self.calls == 1:
                    response.output = {}
                return response
            finally:
                self.active -= 1

    provider = Provider()
    inject(client, provider)
    app = client._transport.app
    app.state.settings.interview_policy.concurrency = 1
    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    row = await append(client, row, 2)
    run = (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                "source_kind": "actual",
                "interview_id": row["id"],
                "expected_source_revision": row["content_revision"],
                "question_analysis": "all",
            },
        )
    ).json()
    async with app.state.preparation_dependencies(app.state.settings, "fixture") as (gateway, _):
        service = DebriefService(sessions, app.state.settings, gateway)
        stream = service.execute(UUID(run["id"]))
        events = []
        async for event in stream:
            events.append(event)
            if event["event"] == "group_completed":
                break
        await stream.aclose()
    assert any(event["event"] == "group_retrying" for event in events)
    assert provider.active == 0
    result = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    assert result["status"] == "partial"
    assert sorted(a["status"] for a in result["artifacts"]) == ["completed", "failed"]
    assert result["usage"]["model_calls"] >= 2
    accepted = next(a for a in result["artifacts"] if a["status"] == "completed")
    calls = (await client.get(f"/api/v1/runs/{result['run_id']}/calls")).json()["model_calls"]
    attempts = sorted(
        [c for c in calls if c["logical_operation_id"] == accepted["logical_operation_id"]],
        key=lambda c: c["attempts"],
    )
    assert [c["attempts"] for c in attempts] == [1, 2]
    assert attempts[0]["status"] == "failed"
    assert attempts[1]["status"] == "succeeded"
    assert accepted["accepted_model_call_id"] == attempts[1]["id"]
    assert attempts[1]["versions"]["repair_reason"] == "schema_invalid"
    assert all(
        a["accepted_model_call_id"] is None for a in result["artifacts"] if a["status"] == "failed"
    )


async def test_concurrent_cost_reservations_cannot_overspend(client, sessions):
    import asyncio
    from contextlib import asynccontextmanager
    from decimal import Decimal

    from test_preparation import inject

    from career_agent.interview.calls import InterviewCalls
    from career_agent.interview.contracts import SourceSnapshot
    from career_agent.interview.debrief import call_policy, inputs_for, task_type
    from career_agent.interview.policy import InterviewPolicy
    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        count = 0

        async def generate(self, candidate, context, task):
            self.count += 1
            await asyncio.sleep(0.3)
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    app = client._transport.app
    original = app.state.preparation_dependencies

    @asynccontextmanager
    async def priced(settings, mode):
        async with original(settings, mode) as (gateway, research):
            gateway.registry = [
                c.model_copy(
                    update={
                        "input_cost_per_million": Decimal(1),
                        "output_cost_per_million": Decimal(1),
                    }
                )
                for c in gateway.registry
            ]
            yield gateway, research

    app.state.preparation_dependencies = priced
    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    run = (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                "source_kind": "actual",
                "interview_id": row["id"],
                "expected_source_revision": row["content_revision"],
                "question_analysis": "all",
                "overall_analysis": True,
            },
        )
    ).json()
    async with priced(app.state.settings, "fixture") as (gateway, _):
        async with sessions.begin() as session:
            stored = await session.get(e.DebriefRun, UUID(run["id"]))
            snapshot = SourceSnapshot.model_validate(stored.snapshot)
            policy = InterviewPolicy.model_validate(stored.execution_policy)
            calls = InterviewCalls(sessions, gateway)
            costs = []
            for kind, ref in [("group", UUID(row["entries"][0]["entry_id"])), ("overall", None)]:
                limits = call_policy(policy, snapshot, kind)
                tokens = calls.preflight(
                    task_type(kind), "fixture", inputs_for(snapshot, ref), limits
                )
                costs.append(Decimal(tokens + limits.max_output_tokens) / 1000000)
            stored.limits = {**stored.limits, "max_estimated_cost": str(max(costs))}
    await client.post(f"/api/v1/interview-debriefs/{run['id']}/execute")
    result = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    assert result["status"] == "partial", result
    assert provider.count == 1 and result["usage"]["model_calls"] == 1
    assert Decimal(result["usage"]["budget_reserved_usd"]) == 0
    assert any(a["error_code"] == "budget_exhausted" for a in result["artifacts"])


async def test_mock_frozen_context_and_exhausted_quota(client, sessions, prep_input):
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    before = row["context"]
    profile = (await client.get("/api/v1/profile")).json()
    await client.put(
        "/api/v1/profile",
        json={
            "expected_revision": profile["revision"],
            "data": {**profile["data"], "display_name": "更新后的合成姓名"},
        },
    )
    async with sessions.begin() as session:
        stored = await session.get(e.MockInterviewSession, UUID(row["id"]))
        stored.limits = {**stored.limits, "max_model_calls": 0}
    path = f"/api/v1/mock-interviews/{row['id']}"
    row = (
        await client.post(
            path + "/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    ).json()
    assert row["status"] == "ready_to_generate" and row["stop_reason"] == "budget_exhausted"
    assert row["context"] == before and row["turns"] == []
    assert row["usage"]["model_calls"] == 0


async def test_accepted_call_binding_and_historical_migration(client, sessions, migrated_url):
    import asyncio

    from alembic import command
    from alembic.config import Config

    from career_agent.domain.rules import DomainError
    from career_agent.interview.calls import AcceptedCall, validate_accepted_call
    from career_agent.interview.contracts import OverallEvaluation

    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    run = (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                "source_kind": "actual",
                "interview_id": row["id"],
                "expected_source_revision": row["content_revision"],
                "overall_analysis": True,
            },
        )
    ).json()
    await client.post(f"/api/v1/interview-debriefs/{run['id']}/execute")
    result = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    artifact = result["artifacts"][0]
    async with sessions.begin() as session:
        call = await session.get(e.ModelCall, UUID(artifact["accepted_model_call_id"]))
        accepted = AcceptedCall(
            OverallEvaluation.model_validate(artifact["data"]["overall"]),
            call.id,
            call.logical_operation_id,
        )
        await validate_accepted_call(
            session, accepted, UUID(run["run_id"]), call.logical_operation_id
        )
        for run_id, operation in [
            (uuid4(), call.logical_operation_id),
            (UUID(run["run_id"]), uuid4()),
        ]:
            with pytest.raises(DomainError, match="model_call_provenance_mismatch"):
                await validate_accepted_call(session, accepted, run_id, operation)
        original_status = call.status
        call.status = e.CallStatus.FAILED
        with pytest.raises(DomainError, match="model_call_provenance_mismatch"):
            await validate_accepted_call(
                session, accepted, UUID(run["run_id"]), call.logical_operation_id
            )
        call.status = original_status
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "a841c3d12342")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    historical = (await client.get(f"/api/v1/interview-debriefs/{run['id']}")).json()
    old = historical["artifacts"][0]
    assert old["status"] == "completed" and old["data"] == artifact["data"]
    assert old["logical_operation_id"] is None and old["accepted_model_call_id"] is None
    await asyncio.to_thread(command.check, cfg)
