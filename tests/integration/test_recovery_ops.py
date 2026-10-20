"""Real PostgreSQL crash boundaries; synthetic provider, no external network."""

import asyncio
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from career_agent.domain.rules import DomainError
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelCandidate, ModelRequestContext, ModelTier
from career_agent.models.control.contracts import ControlPolicy
from career_agent.models.control.controller import Controller
from career_agent.models.control.durable import DurableControl
from career_agent.models.control.recovery_contracts import (
    AutomaticPolicy,
    OperatorRequest,
    ReconcileRequest,
)
from career_agent.models.fake import FakeProvider
from career_agent.models.gateway import ModelGateway, ModelPolicy
from career_agent.models.inputs import InputContract
from career_agent.models.prompts import PromptRegistry, PromptSpec
from career_agent.ops.entities import (
    AttemptJournal,
    ControlEvent,
    ControllerState,
    RecoveryIncident,
)
from career_agent.ops.query import metrics


class Output(BaseModel):
    category: str


SPEC = PromptSpec(
    prompt_name="recovery-synthetic",
    prompt_version="recovery-v1",
    task_type="parse",
    input_schema_version="input-v1",
    output_schema_version="output-v1",
    instruction="Classify synthetic input",
    input_contract={},
    executable_input=InputContract(),
    output_schema=Output,
)
PROMPTS = PromptRegistry([SPEC])


def candidate():
    return ModelCandidate(
        input_cost_per_million=0,
        output_cost_per_million=0,
        provider="synthetic",
        model="cheap",
        tier="cheap",
        capabilities={"structured_output"},
        allowed_privacy={"synthetic"},
    )


def context(**kwargs):
    return ModelRequestContext(task_type="parse", output_schema=Output, **SPEC.metadata, **kwargs)


pytestmark = pytest.mark.integration


def make(sessions, scope=None):
    c = Controller(ControlPolicy(quota_scope=scope or str(uuid4())))
    owner = DurableControl(sessions.kw["bind"], c, AutomaticPolicy())
    gateway = ModelGateway(
        [candidate()],
        ModelPolicy("synthetic-v1", {"parse": ModelTier.CHEAP}),
        {"synthetic": FakeProvider({"category": "synthetic"})},
        prompts=PROMPTS,
        controller=c,
        durable=owner,
    )
    return owner, gateway


@pytest.mark.parametrize("boundary", ["reserved", "dispatch_intent", "settled"])
async def test_restart_boundaries_no_auto_replay(sessions, boundary):
    owner, gateway = make(sessions)
    await owner.start()
    ctx = await gateway.prepare(context(), SPEC.task({}))
    if boundary == "dispatch_intent":
        await owner.intent(ctx)  # crash could precede OR follow network send; always uncertain
    elif boundary == "settled":
        await gateway.generate(ctx, SPEC.task({}))
    await owner.close()
    second, second_gateway = make(sessions, owner.scope)
    try:
        await second.start()
        assert second.controller.effective.ready
        async with sessions() as session:
            journal = await session.scalar(select(AttemptJournal))
            assert (
                journal.status
                == {
                    "reserved": "not_dispatched",
                    "dispatch_intent": "unknown",
                    "settled": "settled",
                }[boundary]
            )
            incidents = list(await session.scalars(select(RecoveryIncident)))
            assert len(incidents) == (0 if boundary == "reserved" else 1)
            report = await metrics(session, owner.scope, 3600)
            assert report["attempts"] == (1 if boundary == "settled" else 0)
            if boundary == "dispatch_intent":
                assert report["unknown_usage_attempts"] == 1
                assert second.controller.leases[ctx.selection.lease_id].settled
                request = ReconcileRequest(
                    request_id=uuid4(), expected_revision=incidents[0].revision
                )
                first = await second.reconcile(ctx.selection.attempt_id, request)
                duplicate = await second.reconcile(ctx.selection.attempt_id, request)
                assert first["replayed"] is False and duplicate["idempotent"]
        assert second_gateway.adapters["synthetic"].calls == 0
    finally:
        await second.close()


async def test_journal_independent_of_uncommitted_business_and_owner_guard(sessions):
    owner, gateway = make(sessions)
    await owner.start()
    contender, _ = make(sessions, owner.scope)
    try:
        with pytest.raises(DomainError, match="controller_owner_exists"):
            await contender.start()
        async with sessions() as session:
            await session.begin()
            run = e.AgentRun(workflow="synthetic")
            session.add(run)
            await session.flush()
            ctx = await asyncio.wait_for(
                gateway.prepare(context(budget_owner_refs=[run.id]), SPEC.task({})), 2
            )
            async with sessions() as independent:
                assert await independent.get(e.AgentRun, run.id) is None
                record = await independent.scalar(select(AttemptJournal))
                assert record.data["budget_owner_refs"] == [str(run.id)]
                assert "deadline" not in record.data["selection"]
            await session.rollback()
            gateway.cancel_prepared(ctx)
    finally:
        await owner.close()


async def test_control_cas_idempotency_kill_restart_and_event_projection(sessions):
    owner, gateway = make(sessions)
    await owner.start()
    request = OperatorRequest(
        request_id=uuid4(),
        expected_revision=owner.controller.effective.revision,
        action="kill",
        enabled=True,
    )
    result = await owner.operate(request)
    assert owner.controller.effective.kill
    assert (await owner.operate(request))["idempotent"]
    with pytest.raises(DomainError, match="revision_conflict"):
        await owner.operate(request.model_copy(update={"request_id": uuid4(), "enabled": False}))
    assert owner.controller.effective.kill
    async with sessions.begin() as session:
        state = await session.scalar(select(ControllerState))
        # Drop only the projection; restart reconstructs from events.
        await session.delete(state)
    await owner.close()
    restarted, _ = make(sessions, owner.scope)
    try:
        await restarted.start()
        assert restarted.controller.effective.kill
        assert restarted.controller.effective.revision > result["revision"]
        assert (
            restarted.controller.acquire("synthetic", "synthetic:cheap", 1, 1, "normal_user")[1]
            == "control_kill_switch"
        )
    finally:
        await restarted.close()


async def test_global_kill_cross_controller_and_restart(sessions):
    from career_agent.models.contracts import ModelGatewayError

    first, _ = make(sessions)
    second, gateway = make(sessions)
    await first.start()
    await second.start()
    try:
        await first.operate(
            OperatorRequest(
                request_id=uuid4(),
                expected_revision=first.controller.effective.revision,
                action="global_kill",
                expected_global_revision=first.controller.effective.global_revision,
                enabled=True,
            )
        )
        assert first.controller.effective.global_kill and second.controller.effective.global_kill
        with pytest.raises(ModelGatewayError, match="model_admission_denied"):
            await gateway.prepare(context(), SPEC.task({}))
        assert gateway.adapters["synthetic"].calls == 0
        await second.close()
        second, _ = make(sessions, second.scope)
        await second.start()
        assert second.controller.effective.global_kill
        await first.operate(
            OperatorRequest(
                request_id=uuid4(),
                expected_revision=first.controller.effective.revision,
                action="global_kill",
                expected_global_revision=first.controller.effective.global_revision,
                enabled=False,
            )
        )
        assert not second.controller.effective.global_kill
    finally:
        await first.close()
        await second.close()


async def test_tick_override_race_rollback_and_ttl(sessions, monkeypatch):
    from career_agent.models.control.recovery_contracts import Adjustment

    owner, _ = make(sessions)
    await owner.start()
    try:
        revision = owner.controller.effective.revision
        override = OperatorRequest(
            request_id=uuid4(),
            expected_revision=revision,
            action="override",
            route="synthetic:cheap",
            values=Adjustment(concurrency=1),
            ttl_seconds=60,
        )
        tick = OperatorRequest(request_id=uuid4(), expected_revision=revision, action="tick")
        results = await asyncio.gather(
            owner.operate(override), owner.operate(tick), return_exceptions=True
        )
        assert sum(isinstance(r, DomainError) for r in results) == 1
        assert owner.controller.effective.revision == revision + 1
        before = owner.controller.effective.model_copy(deep=True)
        real_event = owner._event

        async def fail_after_flush(*args, **kwargs):
            await real_event(*args, **kwargs)
            # Candidate kill state must remain invisible even while the event has flushed.
            assert owner.controller.effective == before
            raise DomainError("synthetic_rollback")

        monkeypatch.setattr(owner, "_event", fail_after_flush)
        with pytest.raises(DomainError, match="synthetic_rollback"):
            await owner.operate(
                OperatorRequest(
                    request_id=uuid4(),
                    expected_revision=before.revision,
                    action="kill",
                    enabled=True,
                )
            )
        assert owner.controller.effective == before
        async with sessions() as session:
            state = await session.scalar(select(ControllerState))
            assert state.revision == before.revision and not state.data["effective"]["kill"]
    finally:
        await owner.close()


async def test_journal_settlement_duplicate_cancel_and_metrics(sessions):
    from career_agent.models.control.recovery_contracts import JournalData

    owner, gateway = make(sessions)
    await owner.start()
    try:
        request = await gateway.prepare(context(), SPEC.task({}))
        result = await gateway.generate(request, SPEC.task({}))
        revision = owner.controller.effective.revision
        await owner.finish(request, result.usage, None, True, 123)
        assert owner.controller.effective.revision == revision
        unused = await gateway.prepare(context(), SPEC.task({}))
        gateway.cancel_prepared(unused)
        await owner.operate(
            OperatorRequest(
                request_id=uuid4(),
                expected_revision=owner.controller.effective.revision,
                action="tick",
            )
        )
        async with sessions() as session:
            rows = list(await session.scalars(select(AttemptJournal)))
            assert sorted(r.status for r in rows) == ["not_dispatched", "settled"]
            d = JournalData.model_validate(next(r for r in rows if r.status == "settled").data)
            assert d.dispatch_confirmed and d.usage.input_tokens == 0
            assert d.selection["hard_output_tokens"] >= d.selection["reserved_output_tokens"]
            report = await metrics(session, owner.scope, 3600)
            assert report["attempts"] == 1 and report["logical_operations"] == 1
            assert report["unknown_dispatch_intents"] == 0
            assert report["unknown_usage_attempts"] == 0
            assert report["estimated_cost_usd_known"] == "0"
            assert report["actual_billed_cost_usd"] is None
            assert "category" not in str(report)
    finally:
        await owner.close()


async def test_unknown_blocks_same_owner_without_replay(sessions):
    from career_agent.models.contracts import ModelGatewayError

    owner, gateway = make(sessions)
    await owner.start()
    parent = uuid4()
    request = await gateway.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
    await owner.intent(request)
    await owner.close()
    restarted, gateway = make(sessions, owner.scope)
    try:
        await restarted.start()
        with pytest.raises(ModelGatewayError, match="recovery_decision_required"):
            await gateway.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
        assert restarted.controller.effective.ready  # unrelated owner can still execute
        result = await gateway.generate(context(budget_owner_refs=[uuid4()]), SPEC.task({}))
        assert result.validated_output.category == "synthetic"
        assert gateway.adapters["synthetic"].calls == 1
    finally:
        await restarted.close()


async def test_provider_result_links_only_committed_terminal_call(sessions):
    from career_agent.domain.rules import CallStatus
    from career_agent.evaluation.contracts import OperationSnapshot
    from career_agent.evaluation.entities import InvocationRow

    owner, gateway = make(sessions)
    await owner.start()
    try:
        ctx = await gateway.prepare(context(), SPEC.task({}))
        result = await gateway.generate(ctx, SPEC.task({}))
        async with sessions.begin() as session:
            run = e.AgentRun(workflow="synthetic")
            session.add(run)
            await session.flush()
            step = e.AgentStep(run_id=run.id, sequence=1, node="synthetic")
            session.add(step)
            await session.flush()
            call = e.ModelCall(
                step_id=step.id,
                logical_operation_id=ctx.logical_operation_id,
                task_type="parse",
                provider="synthetic",
                model="cheap",
                status=CallStatus.RUNNING,
                versions=gateway.trace_metadata(ctx, SPEC.task({})).model_dump(mode="json"),
                usage=result.usage.model_dump(mode="json"),
            )
            session.add(call)
            await session.flush()
            call_id = call.id
        req = ReconcileRequest(request_id=uuid4(), expected_revision=0)
        response = await owner.reconcile(ctx.selection.attempt_id, req)
        assert response["attempt_status"] == "settled"  # RUNNING is not evidence of completion
        async with sessions.begin() as session:
            call = await session.get(e.ModelCall, call_id)
            call.status = CallStatus.SUCCEEDED
            artifact = uuid4()
            session.add(
                InvocationRow(
                    model_call_id=call_id,
                    data=OperationSnapshot(
                        kind="model_task",
                        name="parse",
                        version="v1",
                        input_snapshot={},
                        input_hash="synthetic",
                        output={"category": "synthetic"},
                        output_ref=artifact,
                        accepted_model_call_id=call_id,
                        logical_operation_id=ctx.logical_operation_id,
                    ).model_dump(mode="json"),
                )
            )
        async with sessions() as session:
            incident = await session.scalar(select(RecoveryIncident))
            revision = incident.revision
        response = await owner.reconcile(
            ctx.selection.attempt_id,
            ReconcileRequest(request_id=uuid4(), expected_revision=revision),
        )
        assert response["attempt_status"] == "business_committed"
        async with sessions() as session:
            journal = await session.scalar(select(AttemptJournal))
            assert journal.data["model_call_id"] == str(call_id)
            assert journal.data["artifact_ref"] == str(artifact)
            assert (await session.scalar(select(RecoveryIncident))).status == "resolved"
        assert gateway.adapters["synthetic"].calls == 1
    finally:
        await owner.close()


async def test_ops_api_private_boundary_and_denominators(client, sessions, caplog):
    from pydantic import SecretStr

    owner, gateway = make(sessions)
    await owner.start()
    app = client._transport.app
    app.state.control_owner = owner
    app.state.settings.ops_token = SecretStr("synthetic-operator-token")
    headers = {"X-Ops-Token": "synthetic-operator-token"}
    try:
        assert (await client.get("/api/v1/ops/controller")).status_code == 403
        info = await client.get("/api/v1/ops/controller", headers=headers)
        assert info.status_code == 200
        assert info.json()["effective"]["ready"]
        req = {
            "request_id": str(uuid4()),
            "expected_revision": info.json()["effective"]["revision"],
            "action": "override",
            "route": "synthetic:cheap",
            "values": {"concurrency": 1},
            "ttl_seconds": 60,
        }
        assert (
            await client.post("/api/v1/ops/controls", headers=headers, json=req)
        ).status_code == 200
        assert (await client.post("/api/v1/ops/controls", headers=headers, json=req)).json()[
            "idempotent"
        ]
        async with sessions.begin() as session:
            session.add_all(
                [
                    e.AgentRun(workflow="parent", consumed_usage={"estimated_cost": "1"}),
                    e.AgentRun(workflow="child", consumed_usage={"estimated_cost": "1"}),
                ]
            )
        await gateway.generate(context(), SPEC.task({}))
        response = await client.get("/api/v1/ops/metrics", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["attempts"] == 1 and data["workflow_runs"] == 2
        assert data["estimated_cost_usd_known"] == "0"  # parent/child totals never added
        assert data["unknown_usage_attempts"] == 0 and data["actual_billed_cost_usd"] is None
        events = await client.get("/api/v1/ops/events", headers=headers)
        assert events.status_code == 200
        assert all("snapshot" not in event for event in events.json())
        combined = response.text + events.text + info.text + caplog.text
        for private in [
            "synthetic-operator-token",
            "Classify synthetic input",
            "category",
            "financial_reservation",
        ]:
            assert private not in combined
    finally:
        app.state.control_owner = None
        await owner.close()


async def test_sampling_adjustment_preserves_old_decision_and_no_recursive_judge(client, sessions):
    from decimal import Decimal
    from uuid import UUID

    from test_interview_loop import actual_session, append

    from career_agent.evaluation import entities as q
    from career_agent.evaluation.contracts import JudgeSamplingPolicy, Subject
    from career_agent.evaluation.monitoring import enqueue

    interview, _ = await actual_session(client)
    interview = await append(client, interview, 1)
    run = (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                "source_kind": "actual",
                "interview_id": interview["id"],
                "expected_source_revision": interview["content_revision"],
                "question_analysis": "all",
                "overall_analysis": False,
            },
        )
    ).json()
    assert (await client.post(f"/api/v1/interview-debriefs/{run['id']}/execute")).status_code == 200
    async with sessions.begin() as session:
        invocation = await session.scalar(
            select(q.InvocationRow).where(q.InvocationRow.data["output_ref"].astext.is_not(None))
        )
        call = await session.get(e.ModelCall, invocation.model_call_id)
        call.versions = {
            **call.versions,
            "control_metadata": {
                **call.versions["control_metadata"],
                "effective_sampling_rate": "1",
                "effective_state_revision": 42,
            },
        }
        subject = Subject(
            subject_id=UUID(invocation.data["output_ref"]),
            task_type=invocation.data["name"],
            accepted_model_call_id=call.id,
            operation_id=invocation.id,
        )
        policy = JudgeSamplingPolicy(version="synthetic-adjusted-v1", default_rate=Decimal(0))
        first = await enqueue(session, subject, policy)
        assert first.data["effective_rate"] == "1" and first.data["sampled"]
        assert first.data["effective_control_revision"] == 42
        call.versions = {
            **call.versions,
            "control_metadata": {
                **call.versions["control_metadata"],
                "effective_sampling_rate": "0",
                "effective_state_revision": 43,
            },
        }
        second = await enqueue(session, subject, policy)
        assert second.id == first.id and second.data["effective_rate"] == "1"
        assert (
            await enqueue(session, subject.model_copy(update={"origin": "evaluation"}), policy)
            is None
        )
        judges = list(
            await session.scalars(select(q.JudgeRow).where(q.JudgeRow.sampling_id == first.id))
        )
        assert len(judges) == 1 and judges[0].status == "pending"


async def test_automatic_tick_pressure_bounds_and_durable_decisions(sessions):
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.models.control.recovery_contracts import Adjustment

    class Limited:
        async def generate(self, candidate, context, task):
            raise ModelGatewayError("provider_429")

    owner, gateway = make(sessions)
    gateway.adapters["synthetic"] = Limited()
    await owner.start()
    try:
        for _ in range(5):
            with pytest.raises(ModelGatewayError, match="provider_429"):
                await gateway.generate(context(budget_owner_refs=[uuid4()]), SPEC.task({}))
        await owner.operate(
            OperatorRequest(
                request_id=uuid4(),
                expected_revision=owner.controller.effective.revision,
                action="tick",
            )
        )
        automatic = owner.controller.effective.automatic["synthetic:cheap"]
        assert automatic.pressure == 0.8
        original = automatic.model_copy(deep=True)
        await owner.operate(
            OperatorRequest(
                request_id=uuid4(),
                expected_revision=owner.controller.effective.revision,
                action="tick",
            )
        )
        assert owner.controller.effective.automatic["synthetic:cheap"] == original
        async with sessions() as session:
            records = list(
                await session.scalars(select(ControlEvent).where(ControlEvent.scope == owner.scope))
            )
            assert any(
                d["reason"] == "pressure_reduce" for r in records for d in r.data["decisions"]
            )
            report = await metrics(session, owner.scope, 3600)
            assert report["attempts"] == 5 and report["unknown_usage_attempts"] == 5
            assert report["provider_health"]["failure"] == 0
            assert report["provider_health"]["neutral"] == 5
        await owner.operate(
            OperatorRequest(
                request_id=uuid4(),
                expected_revision=owner.controller.effective.revision,
                action="override",
                route="synthetic:cheap",
                values=Adjustment(concurrency=1),
                ttl_seconds=20,
            )
        )
        assert owner.controller.effective.values("synthetic:cheap", owner.now()).concurrency == 1
    finally:
        await owner.close()


async def test_stale_generation_cannot_publish_control_event(sessions):
    from career_agent.models.contracts import ModelGatewayError

    owner, _ = make(sessions)
    await owner.start()
    try:
        revision = owner.controller.effective.revision
        owner.controller.effective.generation = uuid4()
        with pytest.raises(ModelGatewayError, match="controller_generation_stale"):
            await owner.operate(
                OperatorRequest(
                    request_id=uuid4(), expected_revision=revision, action="kill", enabled=True
                )
            )
        async with sessions() as session:
            row = await session.scalar(
                select(ControllerState).where(ControllerState.scope == owner.scope)
            )
            assert row.revision == revision
            assert not row.data["effective"]["kill"]
    finally:
        await owner.close()


async def test_restart_retains_actual_debt_before_journal_settlement(sessions):
    from career_agent.models.contracts import Usage

    owner, gateway = make(sessions)
    await owner.start()
    ctx = await gateway.prepare(context(), SPEC.task({}))
    await owner.intent(ctx)
    selection = ctx.selection
    assert selection is not None
    lease_id = selection.lease_id
    assert owner.controller.dispatch(lease_id) is None
    owner.controller.settle(lease_id, Usage(input_tokens=10000, output_tokens=10000), None)
    # A control event can snapshot known capacity usage before journal finish commits.
    await owner.operate(
        OperatorRequest(
            request_id=uuid4(), expected_revision=owner.controller.effective.revision, action="tick"
        )
    )
    await owner.close()
    restarted, _ = make(sessions, owner.scope)
    try:
        await restarted.start()
        assert restarted.controller.leases[lease_id].tokens >= 20000
        async with sessions() as session:
            item = await session.scalar(
                select(AttemptJournal).where(AttemptJournal.scope == owner.scope)
            )
            assert item.status == "unknown"
    finally:
        await restarted.close()


@pytest.mark.parametrize("rollback", [False, True])
async def test_global_kill_serializes_stale_local_candidate(sessions, monkeypatch, rollback):
    first, _ = make(sessions)
    second, gateway = make(sessions)
    await first.start()
    await second.start()
    entered, release = asyncio.Event(), asyncio.Event()
    original = second._event

    async def held(*args, **kwargs):
        entered.set()
        await release.wait()
        if rollback:
            raise DomainError("synthetic_rollback")
        return await original(*args, **kwargs)

    monkeypatch.setattr(second, "_event", held)
    try:
        tick = asyncio.create_task(
            second.operate(
                OperatorRequest(
                    request_id=uuid4(),
                    expected_revision=second.controller.effective.revision,
                    action="tick",
                )
            )
        )
        await entered.wait()
        kill = asyncio.create_task(
            first.operate(
                OperatorRequest(
                    request_id=uuid4(),
                    expected_revision=first.controller.effective.revision,
                    expected_global_revision=0,
                    action="global_kill",
                    enabled=True,
                )
            )
        )
        await asyncio.sleep(0)
        assert not kill.done()
        release.set()
        if rollback:
            with pytest.raises(DomainError, match="synthetic_rollback"):
                await tick
            monkeypatch.setattr(second, "_event", original)
        else:
            await tick
        await kill
        assert second.controller.effective.global_kill
        from career_agent.models.contracts import ModelGatewayError

        with pytest.raises(ModelGatewayError):
            await gateway.prepare(context(), SPEC.task({}))
        with pytest.raises(DomainError, match="global_revision_conflict"):
            await second.operate(
                OperatorRequest(
                    request_id=uuid4(),
                    expected_revision=second.controller.effective.revision,
                    expected_global_revision=0,
                    action="global_kill",
                    enabled=False,
                )
            )
        assert second.controller.effective.global_kill
    finally:
        release.set()
        await first.close()
        await second.close()


async def test_business_rollback_immediately_protects_same_owner(sessions):
    from career_agent.models.contracts import ModelGatewayError

    owner, gateway = make(sessions)
    await owner.start()
    parent = uuid4()
    try:
        async with sessions() as session:
            await session.begin()
            ctx = await gateway.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
            owner.watch(session, ctx.selection.attempt_id)
            await gateway.generate(ctx, SPEC.task({}))
            await session.rollback()
            assert ctx.selection.attempt_id in owner.rollback_pending
        with pytest.raises(ModelGatewayError, match="recovery_decision_required"):
            await gateway.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
        async with sessions() as session:
            journal = await session.scalar(select(AttemptJournal))
            incident = await session.scalar(select(RecoveryIncident))
            assert journal.data["usage"] is not None and journal.data["recovered"]
            assert incident.reason == "business_transaction_rolled_back"
        assert gateway.adapters["synthetic"].calls == 1
        await owner.business_ack(ctx.selection.attempt_id, False)
        async with sessions() as session:
            assert len(list(await session.scalars(select(RecoveryIncident)))) == 1
    finally:
        await owner.close()


async def test_ops_deduplicates_admission_and_preserves_old_unknown(sessions):
    from datetime import timedelta
    from decimal import Decimal

    from career_agent.models.control.recovery_contracts import JournalData

    owner, gateway = make(sessions)
    await owner.start()
    try:
        ctx = await gateway.prepare(context(), SPEC.task({}))
        await owner.intent(ctx)
        decisions = [
            {
                "sequence": 1,
                "route": "synthetic:cheap",
                "reason": "rpm_capacity",
                "disposition": "denied",
            }
        ]
        await owner.admission_denied(ctx, decisions)
        await owner.admission_denied(
            ctx,
            decisions
            + [
                {
                    "sequence": 2,
                    "route": "synthetic:cheap",
                    "reason": "tpm_capacity",
                    "disposition": "denied",
                }
            ],
        )
        async with sessions.begin() as session:
            item = await session.scalar(select(AttemptJournal))
            item.created_at = owner.now() - timedelta(hours=2)
            # Original immutable reservation is zero-cost synthetic; unknown must still be counted.
            data = JournalData.model_validate(item.data)
            assert data.financial_reservation.budget_reserved_usd == Decimal(0)
        async with sessions() as session:
            report = await metrics(session, owner.scope, 3600)
            assert report["admission_decisions"] == {"rpm_capacity": 1, "tpm_capacity": 1}
            assert report["unknown_usage_attempts"] == 0
            assert report["outstanding_unknown_attempts"] == 1
    finally:
        await owner.close()
