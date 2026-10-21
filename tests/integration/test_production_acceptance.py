"""Cross-layer Phase 3 acceptance: real PostgreSQL, synthetic providers, no external API."""

import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_preparation import prep_input as preparation_fixture

from career_agent.domain.rules import CallStatus
from career_agent.evaluation.entities import InvocationRow
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.control.contracts import (
    BreakerPolicy,
    CapacityFeedback,
    CapacityLimits,
    ControlPolicy,
    FeedbackBucket,
    RouteApproval,
    TaskControlPolicy,
)
from career_agent.models.control.controller import Controller
from career_agent.models.control.durable import DurableControl
from career_agent.models.control.recovery_contracts import AutomaticPolicy
from career_agent.models.gateway import ModelGateway, ModelPolicy
from career_agent.ops.entities import AttemptJournal
from career_agent.ops.query import metrics
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.preparation.research import FixtureResearchAdapter
from career_agent.runtime.contracts import Usage

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["overflow", "retry_fallback", "429", "output_limit"])
async def test_control_to_business_artifact_and_ops(client, sessions, prep_input, scenario):
    app = client._transport.app
    cheap, strong = "fixture:fixture-cheap", "fixture:fixture-strong"
    control = Controller(
        ControlPolicy(
            quota_scope="phase3-" + uuid4().hex,
            routes={cheap: CapacityLimits(concurrency=1)},
            breaker=BreakerPolicy(consecutive_failures=1),
        )
    )
    owner = DurableControl(sessions.kw["bind"], control, AutomaticPolicy())
    await owner.start()
    held = None
    if scenario == "overflow":
        held, _, _ = control.acquire("fixture", cheap, 1, 1, "normal_user")
        assert held is not None
    selected = []

    class Provider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            selected.append(context.selection)
            if context.task_type == "job_requirement_extraction" and len(selected) == 1:
                if scenario == "retry_fallback":
                    raise ModelGatewayError(
                        "provider_5xx",
                        retryable=True,
                        usage=Usage(
                            input_tokens=5,
                            output_tokens=0,
                            estimated_cost=0,
                            measurement="reported",
                        ),
                    )
                if scenario == "429":
                    raise ModelGatewayError(
                        "provider_429",
                        retryable=True,
                        usage=Usage(
                            input_tokens=0,
                            output_tokens=0,
                            estimated_cost=0,
                            measurement="reported",
                        ),
                        capacity_feedback=CapacityFeedback(
                            quota_scope=control.policy.quota_scope,
                            bucket=FeedbackBucket(scope="route", bucket_id=cheap),
                            remaining_requests=0,
                            reset_requests_seconds=0.01,
                            retry_after_seconds=0.01,
                        ),
                    )
            response = await super().generate(candidate, context, task)
            if scenario == "output_limit":
                response.finish_reason = "max_output_tokens"
            return response

    task_policy = TaskControlPolicy(
        candidates=[
            RouteApproval(
                provider="fixture",
                model="fixture-cheap",
                priority=0,
                qualification_ref="synthetic-primary-v1",
            ),
            RouteApproval(
                provider="fixture",
                model="fixture-strong",
                priority=1,
                qualification_ref="synthetic-fallback-v1",
                roles={"capacity_overflow", "runtime_fallback"},
            ),
        ],
        max_wait_seconds=0,
    )
    policy = ModelPolicy(
        POLICY.version, POLICY.task_tiers, {"job_requirement_extraction": task_policy}
    )

    @asynccontextmanager
    async def dependencies(settings, mode):
        yield (
            ModelGateway(
                registry(settings, False),
                policy,
                {"fixture": Provider()},
                controller=control,
                durable=owner,
            ),
            FixtureResearchAdapter(),
        )

    app.state.preparation_dependencies = dependencies
    try:
        response = await client.post(
            "/api/v1/workflows/prepare_application",
            json={**prep_input, "targets": ["fit_analysis"]},
        )
        assert response.status_code == 201, response.text
        state = response.json()["state"]
        assert state["status"] == ("failed" if scenario == "output_limit" else "completed")
        if owner.ack_tasks:
            await asyncio.gather(*list(owner.ack_tasks))
        if held:
            control.release(held.id)
        assert all(lease.settled or lease.released for lease in control.leases.values())
        expected = (
            3 if scenario in {"retry_fallback", "429"} else 1 if scenario == "output_limit" else 2
        )
        assert len(selected) == expected
        assert state["usage"]["model_calls"] == expected
        assert state["usage"]["reserved_input_tokens"] == 0
        assert state["usage"]["reserved_output_tokens"] == 0
        async with sessions() as session:
            calls = list(
                await session.scalars(select(e.ModelCall).order_by(e.ModelCall.created_at))
            )
            journals = list(await session.scalars(select(AttemptJournal)))
            assert len(calls) == len(journals) == expected
            for selection in selected:
                journal = next(j for j in journals if j.attempt_id == selection.attempt_id)
                call = next(
                    c
                    for c in calls
                    if c.versions["control_metadata"]["attempt_id"] == str(selection.attempt_id)
                )
                assert call.model == selection.model and call.provider == selection.provider
                assert journal.data["selection"]["route"] == selection.route
                assert journal.data["selection"]["lease_id"] == str(selection.lease_id)
                assert control.leases[selection.lease_id].route == selection.route
                assert (
                    journal.data["financial_reservation"]["reserved_output_tokens"]
                    == selection.hard_output_tokens
                )
                assert selection.reserved_output_tokens < selection.hard_output_tokens
                assert journal.data["usage"]["input_tokens"] == call.usage["input_tokens"]
                assert journal.data["model_call_id"] == str(call.id)
                assert journal.status == "business_committed"
            if scenario == "output_limit":
                assert calls[0].error_code == "provider_incomplete"
                assert calls[0].versions["control_metadata"]["output_hard_limit_hit"]
                assert not state["fit_analysis_id"]
                assert not list(
                    await session.scalars(
                        select(InvocationRow).where(
                            InvocationRow.data["output_ref"].astext.is_not(None)
                        )
                    )
                )
            else:
                accepted = await session.scalar(
                    select(InvocationRow).where(
                        InvocationRow.data["output_ref"].astext == state["fit_analysis_id"]
                    )
                )
                assert accepted and accepted.model_call_id in {
                    c.id for c in calls if c.status == CallStatus.SUCCEEDED
                }
            report = await metrics(session, owner.scope, 3600)
            assert report["attempts"] == expected
            assert report["logical_operations"] == (1 if scenario == "output_limit" else 2)
            assert report["outstanding_unknown_attempts"] == 0
            assert report["provider_health"]["failure"] == (
                1 if scenario == "retry_fallback" else 0
            )
            assert report["retry_attempts"] == (1 if scenario in {"retry_fallback", "429"} else 0)
            assert "隐私姓名" not in json.dumps(report, default=str, ensure_ascii=False)
            assert "synthetic-pii@example.invalid" not in json.dumps(report, default=str)
        if scenario == "overflow":
            assert all(s.route == strong for s in selected)
            assert selected[0].routing_role == "capacity_overflow"
            assert not control.circuits[cheap].observations
        elif scenario == "retry_fallback":
            assert selected[0].route == cheap and selected[1].route == strong
            assert selected[1].routing_role == "runtime_fallback"
            assert selected[0].logical_operation_id == selected[1].logical_operation_id
            assert selected[0].deadline == selected[1].deadline
            assert control.circuits[cheap].phase == "open"
        elif scenario == "429":
            assert selected[0].route == selected[1].route == cheap
            assert all(ok for _, ok in control.circuits[cheap].observations)
    finally:
        if held:
            control.release(held.id)
        await owner.close()


@pytest.mark.parametrize("boundary", ["known_rollback", "unknown"])
async def test_recovery_restart_ops_and_reconcile_never_replay(sessions, boundary):
    from test_recovery_ops import SPEC, context, make

    from career_agent.models.control.recovery_contracts import ReconcileRequest
    from career_agent.ops.entities import RecoveryIncident

    owner, gateway = make(sessions)
    await owner.start()
    parent = uuid4()
    request = await gateway.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
    if boundary == "known_rollback":
        async with sessions() as session:
            await session.begin()
            owner.watch(session, request.selection.attempt_id)
            await gateway.generate(request, SPEC.task({}))
            await session.rollback()
        with pytest.raises(ModelGatewayError, match="recovery_decision_required"):
            await gateway.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
        assert gateway.adapters["synthetic"].calls == 1
    else:
        await owner.intent(request)
        assert gateway.adapters["synthetic"].calls == 0
    await owner.close()
    recovered, after = make(sessions, owner.scope)
    await recovered.start()
    try:
        with pytest.raises(ModelGatewayError, match="recovery_decision_required"):
            await after.prepare(context(budget_owner_refs=[parent]), SPEC.task({}))
        async with sessions() as session:
            incidents = list(await session.scalars(select(RecoveryIncident)))
            assert len(incidents) == 1
            incident_id, revision = incidents[0].id, incidents[0].revision
            report = await metrics(session, recovered.scope, 3600)
            assert report["recovery_incidents"] == {"open": 1}
            assert report["outstanding_unknown_attempts"] == (1 if boundary == "unknown" else 0)
            assert report["actual_billed_cost_usd"] is None
        inspect = ReconcileRequest(request_id=uuid4(), expected_revision=revision)
        first = await recovered.reconcile(request.selection.attempt_id, inspect)
        repeated = await recovered.reconcile(request.selection.attempt_id, inspect)
        assert first["replayed"] is False and repeated["idempotent"]
        async with sessions() as session:
            incidents = list(await session.scalars(select(RecoveryIncident)))
            assert len(incidents) == 1 and incidents[0].id == incident_id
        assert after.adapters["synthetic"].calls == 0
    finally:
        await recovered.close()
