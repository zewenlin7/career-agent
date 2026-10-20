"""Control decisions use real DB traces, with synthetic providers only."""

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import prep_input as preparation_fixture

from career_agent.infrastructure import entities as e
from career_agent.models.control.contracts import CapacityLimits, ControlPolicy
from career_agent.models.control.controller import Controller
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
    import asyncio

    from career_agent.models.contracts import ModelGatewayError

    control = Controller(ControlPolicy())
    started = asyncio.Event()

    class Provider(FixtureTaskProvider):
        async def generate(self, *args):
            started.set()
            if failure_kind == "provider":
                raise ModelGatewayError("provider_timeout", retryable=True)
            await asyncio.sleep(10)
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
    if failure_kind == "cancel":
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        response = await task
        assert response.status_code == 200, response.text
    expected = {
        "operation": "operation_deadline_exceeded",
        "provider": "provider_timeout",
        "cancel": "execution_cancelled",
    }[failure_kind]
    async with sessions() as session:
        call = await session.scalar(select(e.ModelCall))
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
