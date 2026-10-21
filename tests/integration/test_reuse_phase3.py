import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_interview_loop import actual_session, append
from test_preparation import prep_input as prep_fixture
from test_preparation import run

from career_agent.infrastructure import entities as e
from career_agent.preparation.observation_store import (
    ReuseDecision,
    SearchObservation,
    search_reuse,
)
from career_agent.preparation.research import FixtureResearchAdapter, SearchInput

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_observation_concurrent_fresh_expiry_and_rollback(sessions):
    adapter = FixtureResearchAdapter()
    count = 0
    now = e.utcnow()

    async def fetch(query):
        nonlocal count
        count += 1
        await asyncio.sleep(0.01)
        return await adapter.search(query)

    async def lookup(at=now):
        return await search_reuse(
            sessions,
            adapter,
            SearchInput(query="  合成公司   技术 "),
            scope="synthetic",
            mode="fixture",
            clock=lambda: at,
            ttl_hours=1,
            run_id=uuid4(),
            fetch=fetch,
        )

    first, second = await asyncio.gather(lookup(), lookup())
    assert count == 1
    assert sorted([first[1], second[1]]) == [False, True]
    assert first[0] == second[0]
    # A later business/synthesis rollback cannot roll back the independently committed observation.
    with pytest.raises(RuntimeError):
        async with sessions.begin():
            assert (await lookup())[1]
            raise RuntimeError("synthetic_synthesis_failure")
    assert (await lookup())[1]
    assert not (await lookup(now + timedelta(hours=2)))[1]
    assert count == 2
    async with sessions.begin() as session:
        rows = list(await session.scalars(select(SearchObservation)))
        for row in rows:
            row.content_hash = "0" * 64
    assert not (await lookup())[1]
    assert count == 3
    async with sessions() as session:
        assert len(list(await session.scalars(select(ReuseDecision)))) == 6
        assert not list(await session.scalars(select(e.ToolCall)))


@pytest.mark.parametrize(
    "target,field",
    [
        ("fit_analysis", "fit_analysis_id"),
        ("resume_tailoring", "render_report_id"),
        ("greeting_generation", "greeting_id"),
    ],
)
async def test_concurrent_identical_target_only_one_generation(
    client, sessions, prep_input, target, field
):
    payload = {**prep_input, "targets": [target]}
    a, b = await asyncio.gather(run(client, payload), run(client, payload))
    assert a["outcome"]["status"] == b["outcome"]["status"] == "completed"
    assert a["state"][field] == b["state"][field]
    assert sum(x["state"]["usage"]["model_calls"] for x in [a, b]) == 2
    assert sum(x["state"]["usage"]["search_calls"] for x in [a, b]) == 0


async def test_debrief_duplicate_create_and_explicit_regenerate(client):
    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    payload = {
        "source_kind": "actual",
        "interview_id": row["id"],
        "expected_source_revision": row["content_revision"],
        "question_analysis": "all",
        "overall_analysis": True,
    }
    responses = await asyncio.gather(
        *[client.post("/api/v1/interview-debriefs", json=payload) for _ in range(2)]
    )
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    original = responses[0].json()
    await append(client, row, 2)
    regenerated = await client.post(
        f"/api/v1/interview-debriefs/{original['id']}/regenerate",
        json={"question_analysis": "all", "overall_analysis": True},
    )
    assert regenerated.status_code == 201, regenerated.text
    assert regenerated.json()["id"] != original["id"]
    assert regenerated.json()["source_hash"] == original["source_hash"]
    assert len(regenerated.json()["artifacts"]) == 2


async def test_claim_contention_timeout_has_no_call_and_does_not_poison_transaction(sessions):
    from sqlalchemy import text

    from career_agent.infrastructure.claims import claim
    from career_agent.models.contracts import ModelGatewayError

    async with sessions.begin() as holder:
        await claim(holder, "synthetic-claim")
        async with sessions.begin() as contender:
            with pytest.raises(ModelGatewayError, match="reuse_in_progress"):
                await claim(contender, "synthetic-claim", wait_seconds=0)
            assert await contender.scalar(text("SELECT 1")) == 1
    async with sessions.begin() as successor:
        await claim(successor, "synthetic-claim", wait_seconds=0)
        assert not list(await successor.scalars(select(e.ModelCall)))


async def test_authorized_search_survives_synthesis_failure_and_business_rollback(
    client, sessions, prep_input
):
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.models.gateway import ModelGateway
    from career_agent.preparation.contracts import WorkflowRequest, WorkflowState
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
    from career_agent.preparation.workflows import PreparationWorkflow

    class Research(FixtureResearchAdapter):
        calls = 0

        async def search(self, query):
            self.calls += 1
            return await super().search(query)

    class Provider(FixtureTaskProvider):
        fail = True
        captured = []

        async def generate(self, candidate, context, task):
            self.captured.append(task.inputs)
            if self.fail:
                raise ModelGatewayError("synthetic_synthesis_failure")
            return await super().generate(candidate, context, task)

    settings = client._transport.app.state.settings
    provider, research = Provider(), Research()
    gateway = ModelGateway(registry(settings, False), POLICY, {"fixture": provider})

    async def authorized(session, force=False):
        request = WorkflowRequest.model_validate(
            {**prep_input, "targets": ["fit_analysis"], "force_research_refresh": force}
        )
        runner = PreparationWorkflow(session, settings, gateway, research, request)
        runner.run = e.AgentRun(workflow="authorized_research_test")
        session.add(runner.run)
        await session.flush()
        runner.state = WorkflowState(
            run_id=runner.run.id,
            job_revision_id=request.job_revision_id,
            profile_id=request.profile_id,
            workflow="prepare_application",
            requested_outputs=["company_research_synthesis"],
        )
        await runner.validate_inputs()
        runner.step = e.AgentStep(run_id=runner.run.id, sequence=1, node="research_company")
        session.add(runner.step)
        await session.flush()
        await runner.research_company()
        return runner

    with pytest.raises(ModelGatewayError, match="synthetic_synthesis_failure"):
        async with sessions.begin() as session:
            await authorized(session)
    async with sessions() as session:
        assert not list(await session.scalars(select(e.CompanyResearch)))
        assert len(list(await session.scalars(select(SearchObservation)))) == 1
    provider.fail = False
    async with sessions.begin() as session:
        runner = await authorized(session)
        assert runner.state.usage.search_calls == 0
        assert runner.state.research_report_id is not None
    assert research.calls == 1
    async with sessions.begin() as session:
        refreshed = await authorized(session, force=True)
        assert refreshed.state.usage.search_calls == 1
    assert research.calls == 2
    for payload in provider.captured:
        evidence = payload["context"]["evidence"][0]
        assert evidence["id"] and evidence["source_url"] and evidence["content"]
        assert evidence["trust_level"] == "untrusted_external"
        assert not {"retrieved_at", "provider", "evidence_version"} & evidence.keys()


async def test_observation_identity_and_frozen_clock_isolate_contracts(sessions):
    from career_agent.evaluation.execution import FROZEN_CLOCK
    from career_agent.preparation.research import SearchReuseContract

    now = e.utcnow()
    adapter = FixtureResearchAdapter()
    calls = 0

    async def fetch(query):
        nonlocal calls
        calls += 1
        return await adapter.search(query)

    async def lookup(mode="fixture", scope="one"):
        return await search_reuse(
            sessions,
            adapter,
            SearchInput(query="合成公司 技术"),
            scope=scope,
            mode=mode,
            clock=e.utcnow,
            ttl_hours=1,
            run_id=uuid4(),
            fetch=fetch,
        )

    token = FROZEN_CLOCK.set(now)
    try:
        assert not (await lookup())[1]
        assert (await lookup())[1]
        assert not (await lookup(mode="live"))[1]
        assert not (await lookup(scope="two"))[1]
        adapter.reuse_contract = SearchReuseContract(
            provider="fixture", version="fixture-search-v2", parameters={"max_results": 3}
        )
        assert not (await lookup())[1]
        assert calls == 4
        async with sessions() as session:
            rows = list(await session.scalars(select(SearchObservation)))
            assert len({r.identity_hash for r in rows}) == 4
            assert all(
                r.retrieved_at == now and r.expires_at == now + timedelta(hours=1) for r in rows
            )
    finally:
        FROZEN_CLOCK.reset(token)


async def test_concurrent_failed_generation_waiter_does_not_repeat_paid_work(
    client, prep_input, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession
    from test_preparation import inject

    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.providers import FixtureTaskProvider

    entered, waited = asyncio.Event(), asyncio.Event()
    scalar = AsyncSession.scalar

    async def observed_scalar(self, statement, *args, **kwargs):
        result = await scalar(self, statement, *args, **kwargs)
        if "pg_try_advisory_xact_lock" in str(statement) and result is False:
            waited.set()
        return result

    monkeypatch.setattr(AsyncSession, "scalar", observed_scalar)

    class Provider(FixtureTaskProvider):
        fit_calls = 0

        async def generate(self, candidate, context, task):
            if context.task_type == "fit_analysis":
                self.fit_calls += 1
                entered.set()
                await asyncio.wait_for(waited.wait(), 5)
                raise ModelGatewayError("synthetic_fit_failure")
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    payload = {**prep_input, "targets": ["fit_analysis"]}
    first = asyncio.create_task(run(client, payload))
    await asyncio.wait_for(entered.wait(), 5)
    second = asyncio.create_task(run(client, payload))
    a, b = await asyncio.gather(first, second)
    assert provider.fit_calls == 1
    assert a["outcome"]["targets"]["fit_analysis"]["reason"] == "synthetic_fit_failure"
    assert b["outcome"]["targets"]["fit_analysis"]["reason"] == "reuse_result_unavailable"
    assert b["state"]["usage"]["model_calls"] == 0


async def test_interview_preparation_concurrent_reuse(client, prep_input):
    package = await run(client, prep_input)
    payload = {**prep_input, "application_package_id": package["package_id"]}
    a, b = await asyncio.gather(
        run(client, payload, "prepare_interview"), run(client, payload, "prepare_interview")
    )
    assert a["state"]["interview_prep_id"] == b["state"]["interview_prep_id"]
    assert a["outcome"]["status"] == b["outcome"]["status"] == "completed"
    assert sum(x["state"]["usage"]["model_calls"] for x in [a, b]) == 1


async def test_phase3_history_upgrade_preserves_old_debrief_without_invented_identity(
    client, sessions, migrated_url
):
    from uuid import UUID

    from alembic import command
    from alembic.config import Config

    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    payload = {
        "source_kind": "actual",
        "interview_id": row["id"],
        "expected_source_revision": row["content_revision"],
        "question_analysis": "all",
    }
    old = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "ab04c0202601")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with sessions() as session:
        restored = await session.get(e.DebriefRun, UUID(old["id"]))
        assert restored.source_hash == old["source_hash"]
        assert restored.request_fingerprint is None
        assert not list(await session.scalars(select(SearchObservation)))
    assert (await client.get(f"/api/v1/interview-debriefs/{old['id']}")).status_code == 200
    new = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    assert new["id"] != old["id"]
    assert new["source_hash"] == old["source_hash"]


async def test_reuse_ops_populations_are_separate_metadata_only(sessions):
    import json

    from career_agent.ops.query import metrics

    adapter = FixtureResearchAdapter()
    query = SearchInput(query="合成私有查询不应出现在Ops")
    for _ in range(2):
        await search_reuse(
            sessions,
            adapter,
            query,
            scope="synthetic",
            mode="fixture",
            clock=e.utcnow,
            ttl_hours=1,
            run_id=uuid4(),
            fetch=adapter.search,
        )
    async with sessions.begin() as session:
        session.add(
            ReuseDecision(
                run_id=uuid4(),
                category="business_artifact",
                operation="fit_analysis",
                disposition="reused",
            )
        )
    async with sessions() as session:
        report = await metrics(session, "synthetic", 3600)
    assert report["attempts"] == 0 and report["logical_operations"] == 0
    assert report["provider_token_cache"]["cached_tokens"]["known_sum"] is None
    external = report["reuse_global_population"]["external_observation"]
    business = report["reuse_global_population"]["business_artifact"]
    assert external["dispositions"] == {"executed": 1, "reused": 1}
    assert business["dispositions"] == {"reused": 1}
    assert (
        external["estimated_savings_usd"] is None and external["actual_billed_savings_usd"] is None
    )
    assert query.query not in json.dumps(report, default=str, ensure_ascii=False)
    assert "source_url" not in json.dumps(report, default=str)


async def test_rollback_owner_does_not_recharge_waiter(client, sessions, prep_input, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    from career_agent.models.gateway import ModelGateway
    from career_agent.preparation.contracts import WorkflowRequest
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
    from career_agent.preparation.workflows import PreparationWorkflow

    # Commit requirements beforehand, without creating a Fit artifact.
    await run(client, {**prep_input, "targets": ["greeting_generation"]})
    waited = asyncio.Event()
    original = AsyncSession.scalar

    async def scalar(self, statement, *args, **kwargs):
        result = await original(self, statement, *args, **kwargs)
        if "pg_try_advisory_xact_lock" in str(statement) and result is False:
            waited.set()
        return result

    monkeypatch.setattr(AsyncSession, "scalar", scalar)
    settings = client._transport.app.state.settings

    class Provider(FixtureTaskProvider):
        calls = 0

        async def generate(self, candidate, context, task):
            self.calls += 1
            return await super().generate(candidate, context, task)

    provider = Provider()
    gateway = ModelGateway(registry(settings, False), POLICY, {"fixture": provider})
    request = WorkflowRequest.model_validate({**prep_input, "targets": ["fit_analysis"]})

    async def execute(session):
        return await PreparationWorkflow(
            session, settings, gateway, FixtureResearchAdapter(), request
        ).execute("prepare_application")

    async def contender():
        async with sessions.begin() as session:
            return await execute(session)

    async with sessions() as owner:
        await owner.begin()
        first = await execute(owner)
        assert first["outcome"]["status"] == "completed"
        assert provider.calls == 1
        second_task = asyncio.create_task(contender())
        await asyncio.wait_for(waited.wait(), 5)
        await owner.rollback()
    second = await second_task
    assert provider.calls == 1
    assert second["state"]["usage"]["model_calls"] == 0
    assert second["outcome"]["targets"]["fit_analysis"]["reason"] == "reuse_result_unavailable"
    # A later explicit request is allowed; no permanent fingerprint poison.
    async with sessions.begin() as session:
        assert (await execute(session))["outcome"]["status"] == "completed"
    assert provider.calls == 2


async def test_concurrent_regenerate_returns_own_generation(client, monkeypatch):
    from career_agent.interview.debrief import DebriefService

    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    original = (
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
    view = DebriefService.view
    both_committed = asyncio.Event()
    created = []

    async def delayed_view(self, id, *, historical=False):
        created.append(id)
        if len(created) == 2:
            both_committed.set()
        await asyncio.wait_for(both_committed.wait(), 5)
        result = await view(self, id, historical=historical)
        assert str(result["id"]) == str(id)
        return result

    monkeypatch.setattr(DebriefService, "view", delayed_view)
    url = f"/api/v1/interview-debriefs/{original['id']}/regenerate"
    responses = await asyncio.gather(
        *[
            client.post(url, json={"question_analysis": "all", "overall_analysis": True})
            for _ in range(2)
        ]
    )
    assert all(r.status_code == 201 for r in responses)
    a, b = [r.json() for r in responses]
    assert a["id"] != b["id"] and a["run_id"] != b["run_id"]
    assert {x["id"] for x in a["artifacts"]}.isdisjoint(x["id"] for x in b["artifacts"])
    assert a["source_hash"] == b["source_hash"] == original["source_hash"]
    monkeypatch.setattr(DebriefService, "view", view)
    selected = (await client.get(f"/api/v1/interview-debriefs/{original['id']}")).json()
    assert selected["id"] == str(created[-1])
