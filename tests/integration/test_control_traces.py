"""Control decisions use real DB traces, with synthetic providers only."""

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import prep_input as preparation_fixture

from career_agent.infrastructure import entities as e
from career_agent.models.control.contracts import CapacityLimits, ControlPolicy
from career_agent.models.control.controller import Controller
from career_agent.models.control.scenario import FrozenClock
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.preparation.research import FixtureResearchAdapter

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


def deny_capacity(client):
    control = Controller(ControlPolicy(provider=CapacityLimits(rpm=1)))

    @asynccontextmanager
    async def dependencies(settings, mode):
        yield (
            ModelGateway(
                registry(settings, False),
                POLICY,
                {"fixture": FixtureTaskProvider()},
                controller=control,
            ),
            FixtureResearchAdapter(),
        )

    client._transport.app.state.preparation_dependencies = dependencies
    return control


async def test_preparation_admission_denial_has_step_without_fake_model_call(
    client, sessions, prep_input
):
    control = deny_capacity(client)
    response = await client.post(
        "/api/v1/workflows/prepare_application",
        json={**prep_input, "targets": ["fit_analysis"]},
    )
    assert response.status_code == 201, response.text
    state = response.json()["state"]
    assert state["status"] == "failed"
    assert state["usage"]["model_calls"] == 0
    async with sessions() as session:
        assert list(await session.scalars(select(e.ModelCall))) == []
        steps = list(
            await session.scalars(
                select(e.AgentStep).where(e.AgentStep.run_id == UUID(state["run_id"]))
            )
        )
        assert any(step.versions.get("control_decisions") for step in steps)
    assert not control.leases
    assert all(not value.observations for value in control.circuits.values())


async def test_mock_admission_denied_can_retry_without_duplicate_step_sequence(
    client, sessions, prep_input
):
    control = deny_capacity(client)
    response = await client.post("/api/v1/mock-interviews", json={"context": prep_input})
    assert response.status_code == 201, response.text
    row = response.json()
    path = f"/api/v1/mock-interviews/{row['id']}/generate"
    for _ in range(2):
        response = await client.post(
            path, json={"expected_revision": row["revision"], "request_id": str(uuid4())}
        )
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["status"] == "ready_to_generate"
    async with sessions() as session:
        assert list(await session.scalars(select(e.ModelCall))) == []
        steps = list(
            await session.scalars(
                select(e.AgentStep).where(e.AgentStep.run_id == UUID(row["run_id"]))
            )
        )
        assert len(steps) == 2
        assert len({s.sequence for s in steps}) == 2
        assert all(s.versions["control_decisions"] for s in steps)
    assert not control.leases


async def test_preparation_trace_binds_actual_route_and_private_control_snapshot(
    client, sessions, prep_input
):
    response = await client.post(
        "/api/v1/workflows/prepare_application",
        json={**prep_input, "targets": ["fit_analysis"]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["state"]["status"] == "completed"
    from career_agent.evaluation.entities import InvocationRow

    async with sessions() as session:
        calls = list(await session.scalars(select(e.ModelCall)))
        assert calls
        for call in calls:
            metadata = call.versions["control_metadata"]
            assert metadata["route"] == f"{call.provider}:{call.model}"
            assert metadata["logical_operation_id"] == str(call.logical_operation_id)
            assert metadata["attempt_index"] == call.attempts
            assert metadata["provider_health"] == "success"
            assert call.versions["control_decisions"]
            invocation = await session.scalar(
                select(InvocationRow).where(InvocationRow.model_call_id == call.id)
            )
            contract = invocation.data["provenance"]["control_contract"]
            assert contract["selection"]["attempt_id"] == metadata["attempt_id"]
            assert "inputs" not in call.versions and "control_contract" not in call.versions


async def test_explicit_mock_retry_keeps_active_deadline_not_user_wait(
    client, sessions, prep_input
):
    from datetime import timedelta

    from test_preparation import inject

    from career_agent.models.contracts import ModelGatewayError

    class FirstFailure(FixtureTaskProvider):
        count = 0

        async def generate(self, *args):
            self.count += 1
            if self.count == 1:
                raise ModelGatewayError("provider_timeout", retryable=True)
            return await super().generate(*args)

    provider = FirstFailure()
    inject(client, provider)
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}/generate"
    row = (
        await client.post(
            path, json={"expected_revision": row["revision"], "request_id": str(uuid4())}
        )
    ).json()
    assert row["status"] == "ready_to_generate"
    async with sessions.begin() as session:
        call = await session.scalar(select(e.ModelCall))
        call.created_at = e.utcnow() - timedelta(days=30)
    response = await client.post(
        path, json={"expected_revision": row["revision"], "request_id": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["status"] == "waiting_answer" and provider.count == 2
    async with sessions() as session:
        calls = list(await session.scalars(select(e.ModelCall).order_by(e.ModelCall.attempts)))
        assert [c.attempts for c in calls] == [1, 2]
        assert calls[-1].versions["control_metadata"]["attempt_index"] == 2
        assert row["turns"][0]["accepted_model_call_id"] == str(calls[-1].id)


@pytest.mark.parametrize("failure_kind", ["operation", "provider", "cancel"])
async def test_interview_timeout_classification_matches_persisted_call_and_breaker(
    client, sessions, prep_input, failure_kind
):
    from career_agent.models.contracts import ModelGatewayError

    # Keep admission/DB latency outside this in-flight classification test. The real
    # asyncio timeout still starts at provider dispatch with the unchanged 100 ms limit.
    control = Controller(ControlPolicy(), clock=FrozenClock())
    started = asyncio.Event()

    class Provider(FixtureTaskProvider):
        async def generate(self, *args):
            started.set()
            if failure_kind == "provider":
                raise ModelGatewayError("provider_timeout", retryable=True)
            await asyncio.Event().wait()
            raise AssertionError("must not complete")

    @asynccontextmanager
    async def dependencies(settings, mode):
        yield (
            ModelGateway(
                registry(settings, False), POLICY, {"fixture": Provider()}, controller=control
            ),
            FixtureResearchAdapter(),
        )

    app = client._transport.app
    app.state.preparation_dependencies = dependencies
    app.state.settings.interview_policy.mock_generation.max_seconds = (
        0.1 if failure_kind == "operation" else 5
    )
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    task = asyncio.create_task(
        client.post(
            f"/api/v1/mock-interviews/{row['id']}/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        if failure_kind == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            response = await task
            assert response.status_code == 200, response.text
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    expected = {
        "operation": "operation_deadline_exceeded",
        "provider": "provider_timeout",
        "cancel": "execution_cancelled",
    }[failure_kind]
    async with sessions() as session:
        call = await session.scalar(select(e.ModelCall))
        assert started.is_set()
        assert call is not None
        assert call.error_code == expected
        metadata = call.versions["control_metadata"]
        assert metadata["attempt_outcome"] == (
            "provider_request_timeout" if failure_kind == "provider" else expected
        )
        assert metadata["provider_health"] == (
            "failure" if failure_kind == "provider" else "neutral"
        )
        observations = control.circuits[metadata["route"]].observations
        assert [ok for _, ok in observations] == ([False] if failure_kind == "provider" else [])
        assert len(control.leases) == 1
        lease = next(iter(control.leases.values()))
        assert lease.settled and lease.dispatched
        assert call.usage["budget_reserved_usd"] is not None
        assert call.usage["measurement"] == "unknown"
        assert call.usage["input_tokens"] is None and call.usage["output_tokens"] is None
        step = await session.get(e.AgentStep, call.step_id)
        assert step.status == call.status
        assert step.reason_code == call.error_code
        observation = await session.scalar(
            select(e.Observation).where(e.Observation.model_call_id == call.id)
        )
        assert observation.error_code == expected
        mock = await session.get(e.MockInterviewSession, UUID(row["id"]))
        assert mock.usage["model_calls"] == 1
        assert mock.usage["unknown_usage_attempts"] == 1
        assert mock.usage["reserved_seconds"] == 0
        for field in ("reserved_input_tokens", "reserved_output_tokens", "budget_reserved_usd"):
            assert mock.usage[field] == call.usage[field]
        assert list(await session.scalars(select(e.MockInterviewTurn))) == []
        assert mock.primary_question_count == mock.followup_count == 0


@pytest.mark.parametrize("stage", ["before_generate", "after_admission", "after_intent"])
async def test_interview_deadline_before_dispatch_releases_call_and_reservation(
    client, sessions, prep_input, monkeypatch, stage
):
    from decimal import Decimal

    from career_agent.models.control.durable import DurableControl
    from career_agent.models.control.recovery_contracts import AutomaticPolicy, OperatorRequest
    from career_agent.ops.entities import AttemptJournal

    clock = FrozenClock()
    control = Controller(ControlPolicy(quota_scope=str(uuid4())), clock=clock)
    durable = DurableControl(sessions.kw["bind"], control, AutomaticPolicy())
    provider_calls = 0

    class Provider(FixtureTaskProvider):
        async def generate(self, *args):
            nonlocal provider_calls
            provider_calls += 1
            raise AssertionError("expired operation must not dispatch")

    app = client._transport.app
    gateway = ModelGateway(
        registry(app.state.settings, False),
        POLICY,
        {"fixture": Provider()},
        controller=control,
        durable=durable,
    )

    @asynccontextmanager
    async def dependencies(settings, mode):
        yield gateway, FixtureResearchAdapter()

    async def expire(context):
        # Reservation is genuinely committed; expiry must undo it, not fabricate a call.
        async with sessions() as session:
            call = await session.scalar(select(e.ModelCall))
            assert call is not None and call.status.value == "running"
        assert not gateway.was_dispatched(context)
        clock.advance(gateway.operations[context.logical_operation_id].deadline - clock() + 0.001)

    if stage == "before_generate":
        generate = gateway.generate

        async def delayed_generate(context, task):
            await expire(context)
            return await generate(context, task)

        monkeypatch.setattr(gateway, "generate", delayed_generate)
    elif stage == "after_admission":
        admit = gateway.admit_adapter

        async def delayed_admit(context, task):
            await admit(context, task)
            await expire(context)

        monkeypatch.setattr(gateway, "admit_adapter", delayed_admit)
    else:
        intent = durable.intent

        async def delayed_intent(context):
            await intent(context)
            await expire(context)

        monkeypatch.setattr(durable, "intent", delayed_intent)

    app.state.preparation_dependencies = dependencies
    app.state.settings.interview_policy.mock_generation.max_seconds = 0.1
    await durable.start()
    try:
        created = await client.post("/api/v1/mock-interviews", json={"context": prep_input})
        assert created.status_code == 201, created.text
        row = created.json()
        response = await client.post(
            f"/api/v1/mock-interviews/{row['id']}/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ready_to_generate"
        assert response.json()["stop_reason"] == "operation_deadline_exceeded"
        await asyncio.gather(*durable.ack_tasks)
        await durable.operate(
            OperatorRequest(
                request_id=uuid4(), expected_revision=control.effective.revision, action="tick"
            )
        )
        assert provider_calls == 0 and not gateway.outcomes
        assert len(control.leases) == 1
        assert all(lease.released and not lease.dispatched for lease in control.leases.values())
        assert all(not circuit.observations for circuit in control.circuits.values())
        async with sessions() as session:
            assert list(await session.scalars(select(e.ModelCall))) == []
            assert list(await session.scalars(select(e.Observation))) == []
            steps = list(await session.scalars(select(e.AgentStep)))
            assert steps and all(
                step.reason_code == "operation_deadline_exceeded" for step in steps
            )
            mock = await session.get(e.MockInterviewSession, UUID(row["id"]))
            assert list(await session.scalars(select(e.MockInterviewTurn))) == []
            assert mock.primary_question_count == mock.followup_count == 0
            for field in (
                "model_calls",
                "unknown_usage_attempts",
                "reserved_input_tokens",
                "reserved_output_tokens",
                "reserved_seconds",
            ):
                assert mock.usage[field] == 0
            assert Decimal(mock.usage["budget_reserved_usd"]) == 0
            journal = (await session.scalars(select(AttemptJournal))).one()
            assert journal.status == "not_dispatched"
            assert journal.data["dispatch_confirmed"] is False
            assert journal.data["model_call_id"] is None
            assert journal.data["provider_outcome"] == (
                "operation_deadline_exceeded"
                if stage == "after_intent"
                else "cancelled_before_dispatch"
            )
    finally:
        await durable.close()


async def test_judge_late_admission_denial_preserves_ordered_decisions(
    client, sessions, prep_input
):
    from decimal import Decimal

    from career_agent.evaluation import entities as q
    from career_agent.evaluation.contracts import JudgeSamplingPolicy, Subject
    from career_agent.evaluation.judge import JudgeRunner
    from career_agent.evaluation.monitoring import enqueue

    response = await client.post(
        "/api/v1/workflows/prepare_application", json={**prep_input, "targets": ["fit_analysis"]}
    )
    assert response.status_code == 201, response.text
    async with sessions.begin() as session:
        invocation = await session.scalar(
            select(q.InvocationRow).where(q.InvocationRow.data["name"].astext == "fit_analysis")
        )
        assert invocation.data["output_ref"]
        await enqueue(
            session,
            Subject(
                subject_id=UUID(invocation.data["output_ref"]),
                task_type="fit_analysis",
                accepted_model_call_id=invocation.model_call_id,
            ),
            JudgeSamplingPolicy(version="late-denial-test-v1", default_rate=Decimal(1)),
        )

    class LateDenial(Controller):
        def dispatch(self, id):
            self.circuits[self.leases[id].route].phase = "open"
            return super().dispatch(id)

    control = LateDenial(ControlPolicy())
    settings = client._transport.app.state.settings
    gateway = ModelGateway(
        registry(settings, False), POLICY, {"fixture": FixtureTaskProvider()}, controller=control
    )
    result = await JudgeRunner(sessions, settings, gateway).drain()
    assert result["results"][0]["reason_code"] == "model_admission_denied"
    assert result["usage"]["model_calls"] == 0
    async with sessions() as session:
        judge = await session.scalar(select(q.JudgeRow))
        assert judge.status == "failed" and judge.model_call_id is None
        calls = list(
            await session.scalars(
                select(e.ModelCall).where(e.ModelCall.task_type == "quality_judgement")
            )
        )
        assert calls == []
        step = await session.scalar(
            select(e.AgentStep).where(e.AgentStep.node == "quality_judgement")
        )
        decisions = step.versions["control_decisions"]
        assert [d["disposition"] for d in decisions] == ["admitted", "denied"]
        assert decisions[-1]["reason"] == "circuit_open"
        assert [d["sequence"] for d in decisions] == [1, 2]
        assert all("inputs" not in d and "output" not in d for d in decisions)
    assert all(lease.released and not lease.dispatched for lease in control.leases.values())
