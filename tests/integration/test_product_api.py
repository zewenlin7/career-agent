"""Browser contracts use real PostgreSQL and fixture providers; no paid calls."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import inject, run
from test_preparation import prep_input as prep_fixture

from career_agent.infrastructure import entities as e
from career_agent.product.entities import ProductOperation

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def make_operation(client, prep_input, **kw):
    payload = {
        "request_id": str(uuid4()),
        "kind": "prepare_application",
        "request": {**prep_input, "targets": ["fit_analysis"]},
    }
    payload.update(kw)
    response = await client.post("/api/v1/operations", json=payload)
    assert response.status_code == 201, response.text
    return payload, response.json()


async def test_operation_identity_execute_result_and_feedback(client, sessions, prep_input):
    payload, op = await make_operation(client, prep_input)
    assert op["status"] == "pending" and op["allowed_actions"] == ["execute"]
    assert (await client.post("/api/v1/operations", json=payload)).json()["id"] == op["id"]
    conflict = {**payload, "kind": "prepare_interview"}
    assert (await client.post("/api/v1/operations", json=conflict)).status_code == 409
    async with sessions() as session:
        assert not list(await session.scalars(select(e.ModelCall)))
    result = await client.post(f"/api/v1/operations/{op['id']}/execute")
    assert result.status_code == 200, result.text
    final = result.json()
    assert final["status"] == "success" and final["run_id"] == op["run_id"]
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json() == final
    product = await client.get(f"/api/v1/operations/{op['id']}/result")
    assert product.status_code == 200, product.text
    item = product.json()["results"][0]
    assert item["kind"] == "fit_analysis" and item["content"]["items"]
    assert item["feedback_target"]["subject_id"] == item["result_id"]
    feedback = await client.post(
        "/api/v1/evaluation/feedback",
        json={"subject": item["feedback_target"], "vote": "thumbs_up"},
    )
    assert feedback.status_code == 201, feedback.text
    assert item["target_artifact_id"] != item["result_id"]
    listing = (await client.get("/api/v1/operations?limit=1")).json()
    assert listing["items"][0]["id"] == op["id"] and not listing["has_more"]
    _, duplicate = await make_operation(client, prep_input)
    await client.post(f"/api/v1/operations/{duplicate['id']}/execute")
    reused = (await client.get(f"/api/v1/operations/{duplicate['id']}/result")).json()["results"][0]
    assert reused["reused"] and reused["result_id"] == item["result_id"]
    async with sessions() as session:
        assert len(list(await session.scalars(select(e.ModelCall)))) == 2


async def test_operation_concurrent_execution_and_live_poll(client, prep_input):
    from career_agent.preparation.providers import FixtureTaskProvider

    entered, release = asyncio.Event(), asyncio.Event()

    class Provider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            entered.set()
            await release.wait()
            return await super().generate(candidate, context, task)

    inject(client, Provider())
    _, op = await make_operation(client, prep_input)
    task = asyncio.create_task(client.post(f"/api/v1/operations/{op['id']}/execute"))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        poll = await client.get(f"/api/v1/operations/{op['id']}")
        assert poll.json()["status"] == "running"
        assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).status_code == 409
    finally:
        release.set()
    assert (await task).json()["status"] == "success"


async def test_interrupted_operation_never_auto_replays(client, sessions, prep_input):
    _, op = await make_operation(client, prep_input)
    async with sessions.begin() as session:
        row = await session.get(ProductOperation, UUID(op["id"]))
        row.status = "running"  # committed dispatch marker, no active request after restart
    result = (await client.get(f"/api/v1/operations/{op['id']}")).json()
    assert result["status"] == "recovery_required"
    assert result["allowed_actions"] == ["inspect_recovery"]
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json() == result
    async with sessions() as session:
        assert not list(await session.scalars(select(e.ModelCall)))


async def test_company_research_explicit_refresh_and_discovery(client, prep_input):
    from career_agent.preparation.research import FixtureResearchAdapter

    class Research(FixtureResearchAdapter):
        calls = 0

        async def search(self, query):
            self.calls += 1
            return await super().search(query)

    research = Research()
    inject(client, research=research)
    jobs = (await client.get("/api/v1/jobs")).json()
    company_id = jobs[0]["company_id"]
    assert (await client.get("/api/v1/companies")).json()["items"][0]["id"] == company_id
    assert (await client.get(f"/api/v1/companies/{company_id}")).status_code == 200
    for index, force in enumerate([False, False, True]):
        payload = {
            "request_id": str(uuid4()),
            "kind": "company_research",
            "request": {**prep_input, "force_research_refresh": force},
        }
        response = await client.post(f"/api/v1/companies/{company_id}/research", json=payload)
        assert response.status_code == 201, response.text
        op = response.json()
        done = await client.post(f"/api/v1/operations/{op['id']}/execute")
        assert done.json()["status"] == "success", done.text
        assert done.json()["research_report_id"]
        assert research.calls == [1, 1, 2][index]
    current = (
        await client.get(f"/api/v1/companies/{company_id}/research/current?mode=fixture")
    ).json()
    assert current["reusable_for_current_execution"]
    listing = (await client.get(f"/api/v1/companies/{company_id}/research?limit=1")).json()
    assert listing["has_more"] and len(listing["items"]) == 1
    assert (await client.get(f"/api/v1/operations/{op['id']}/result")).json()["id"] == current["id"]


async def test_profile_job_and_application_discovery(client, prep_input):
    job = (await client.get("/api/v1/jobs")).json()[0]
    profile = (await client.get("/api/v1/profile")).json()
    updated = await client.put(
        "/api/v1/profile",
        json={
            "expected_revision": profile["revision"],
            "data": {**profile["data"], "display_name": "更新资料"},
        },
    )
    assert updated.status_code == 200
    history = (await client.get("/api/v1/profile/revisions?limit=1")).json()
    assert history["has_more"] and history["items"][0]["id"] != profile["id"]
    assert (await client.get(f"/api/v1/profile/revisions/{profile['id']}")).json() == profile
    revision = await client.post(
        f"/api/v1/jobs/{job['id']}/revisions",
        json={"expected_revision": 1, "title": "新标题", "jd_text": "新 JD"},
    )
    assert revision.status_code == 201
    old = (await client.get(f"/api/v1/job-revisions/{job['job_revision_id']}")).json()
    assert old["revision"] == 1 and old["title"] == job["title"]
    assert (await client.get(f"/api/v1/jobs/{job['id']}/revisions?limit=1")).json()["has_more"]
    apps = (
        await client.get(f"/api/v1/applications?company_id={job['company_id']}&status=tracking")
    ).json()
    assert apps["items"][0]["id"] == job["application_id"]
    assert (await client.get("/api/v1/applications?status=applied")).json()["items"] == []
    assert (await client.get("/api/v1/operations?limit=0")).status_code == 422


async def test_submission_exact_material_and_idempotency(client, prep_input):
    package = await run(client, prep_input)
    st = package["state"]
    product = (
        await client.get(f"/api/v1/preparation-artifacts/{package['package_id']}/product-view")
    ).json()
    resume = next(x for x in product["results"] if x["kind"] == "resume_tailoring")
    assert resume["download_url"] and resume["feedback_target"]
    job = (await client.get("/api/v1/jobs")).json()[0]
    app = (await client.get(f"/api/v1/applications/{job['application_id']}")).json()
    assert app["status"] == "tracking"
    payload = {
        "request_id": str(uuid4()),
        "expected_revision": app["revision"],
        "resume_revision_id": resume["resume_revision_id"],
        "render_artifact_id": st["render_report_id"],
        "package_id": package["package_id"],
    }
    response = await client.post(f"/api/v1/applications/{app['id']}/submissions", json=payload)
    assert response.status_code == 201, response.text
    submitted = response.json()
    duplicate = await client.post(f"/api/v1/applications/{app['id']}/submissions", json=payload)
    assert duplicate.json() == submitted
    changed = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert changed["status"] == "applied" and changed["revision"] == app["revision"] + 1
    assert changed["events"][-1]["id"] == submitted["event_id"]
    listing = (await client.get(f"/api/v1/applications/{app['id']}/submissions")).json()
    assert listing["items"] == [submitted]
    stale = {**payload, "request_id": str(uuid4())}
    assert (
        await client.post(f"/api/v1/applications/{app['id']}/submissions", json=stale)
    ).status_code == 409


async def test_cancelled_execution_is_queryable_without_replay(client, prep_input):
    from career_agent.preparation.providers import FixtureTaskProvider

    entered = asyncio.Event()

    class Provider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            entered.set()
            await asyncio.Event().wait()

    inject(client, Provider())
    _, op = await make_operation(client, prep_input)
    task = asyncio.create_task(client.post(f"/api/v1/operations/{op['id']}/execute"))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = (await client.get(f"/api/v1/operations/{op['id']}")).json()
    assert result["status"] == "recovery_required"
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json() == result


async def test_interview_discovery_and_run_filters(client, prep_input):
    from test_interview_loop import actual_session, append

    job = (await client.get("/api/v1/jobs")).json()[0]
    binding = await client.put(
        f"/api/v1/applications/{job['application_id']}/context",
        json={"expected_revision": 1, **prep_input},
    )
    assert binding.status_code == 200, binding.text
    creation = {
        "context": prep_input,
        "application_binding": {
            "application_id": job["application_id"],
            "revision": binding.json()["revision"],
        },
    }
    mock = (await client.post("/api/v1/mock-interviews", json=creation)).json()
    found = (
        await client.get(
            "/api/v1/mock-interviews", params={"application_id": job["application_id"]}
        )
    ).json()
    assert found["items"][0]["id"] == mock["id"]
    actual, other = await actual_session(client)
    actual = await append(client, actual, 1)
    created = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "actual",
            "interview_id": actual["id"],
            "expected_source_revision": actual["content_revision"],
            "question_analysis": "all",
            "overall_analysis": False,
        },
    )
    assert created.status_code == 201, created.text
    listing = await client.get(
        "/api/v1/interview-debriefs",
        params={
            "source_kind": "actual",
            "source_id": actual["id"],
            "application_id": other["application_id"],
        },
    )
    assert listing.json()["items"][0]["id"] == created.json()["id"]
    assert (await client.get("/api/v1/mock-interviews", params={"job_id": other["id"]})).json()[
        "items"
    ] == []
    assert (await client.get("/api/v1/runs?kind=workflow&limit=1")).json()["has_more"]


async def test_product_migration_history_upgrade(migrated_url, sessions, prep_input):
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "ac04c0302601")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)
    async with sessions() as session:
        assert await session.get(e.PersonalProfile, UUID(prep_input["profile_id"]))
        assert not list(await session.scalars(select(ProductOperation)))


async def test_operation_needs_input_and_research_failure(client, prep_input):
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.research import FixtureResearchAdapter

    request = {**prep_input, "targets": ["resume_tailoring"], "bindings": {}}
    request.pop("resume_revision_id")
    _, op = await make_operation(client, prep_input, request=request)
    done = await client.post(f"/api/v1/operations/{op['id']}/execute")
    assert done.json()["status"] == "needs_input", done.text
    item = (await client.get(f"/api/v1/operations/{op['id']}/result")).json()["results"][0]
    assert item["status"] == "pending" and item["allowed_actions"] == ["provide_input"]

    class Research(FixtureResearchAdapter):
        async def search(self, query):
            raise ModelGatewayError("research_unavailable")

    inject(client, research=Research())
    _, op = await make_operation(client, prep_input, kind="company_research")
    done = await client.post(f"/api/v1/operations/{op['id']}/execute")
    assert done.json()["status"] == "failure", done.text
    assert done.json()["reason"] == "research_failed"
    assert done.json()["research_report_id"] is None
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json() == done.json()


@pytest.mark.parametrize("failure", ["rollback", "cancel", "after_commit"])
async def test_operation_pdf_transaction_outcome(
    client, sessions, prep_input, monkeypatch, failure
):
    from contextlib import asynccontextmanager

    from career_agent.preparation.workflows import PreparationWorkflow
    from career_agent.product.operations import execute as execute_operation

    app = client._transport.app
    inject(client)
    original = PreparationWorkflow.execute
    created = []

    async def execute(runner, workflow):
        result = await original(runner, workflow)
        created.extend(runner.session.info.get("artifact_cleanup", []))
        assert created
        for store, ref in created:
            assert store._path(ref).exists()
        if failure == "rollback":
            raise RuntimeError("synthetic rollback after PDF write")
        if failure == "cancel":
            raise asyncio.CancelledError()
        return result

    monkeypatch.setattr(PreparationWorkflow, "execute", execute)
    if failure == "after_commit":
        factory = app.state.preparation_dependencies

        @asynccontextmanager
        async def close_failure(settings, mode):
            async with factory(settings, mode) as deps:
                yield deps
            raise RuntimeError("synthetic provider context close after business commit")

        app.state.preparation_dependencies = close_failure
    _, op = await make_operation(
        client, prep_input, request={**prep_input, "targets": ["resume_tailoring"]}
    )
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await execute_operation(
                app.state.sessions,
                app.state.settings,
                UUID(op["id"]),
                app.state.preparation_dependencies,
            )
    else:
        await client.post(f"/api/v1/operations/{op['id']}/execute")
    done = (await client.get(f"/api/v1/operations/{op['id']}")).json()
    assert done["status"] == ("success" if failure == "after_commit" else "recovery_required")
    assert created, "The failure must occur after a real PDF was written"
    for store, ref in created:
        assert store._path(ref).exists() == (failure == "after_commit")
    async with sessions() as session:
        run = await session.get(e.AgentRun, UUID(op["run_id"]))
        assert (run is not None) == (failure == "after_commit")
    if failure == "after_commit":
        view = (await client.get(f"/api/v1/operations/{op['id']}/result")).json()
        assert (await client.get(view["results"][0]["download_url"])).content.startswith(b"%PDF")


async def test_research_workflow_provenance_and_replay_boundary(client, sessions, prep_input):
    from career_agent.evaluation.captured import replay_source
    from career_agent.evaluation.entities import InvocationRow
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.providers import FixtureTaskProvider

    seen = []

    class Provider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            seen.append((context.workflow, context.workflow_version))
            return await super().generate(candidate, context, task)

    inject(client, Provider())
    _, op = await make_operation(client, prep_input, kind="company_research")
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "success"
    identity = ("company_research", "company-research-product-v1")
    assert seen == [identity]
    async with sessions() as session:
        run = await session.get(e.AgentRun, UUID(op["run_id"]))
        assert (run.workflow, run.workflow_version) == identity
        for step in await session.scalars(select(e.AgentStep).where(e.AgentStep.run_id == run.id)):
            assert (step.versions["workflow"], step.versions["workflow_version"]) == identity
        calls = list(
            await session.scalars(
                select(e.ModelCall).join(e.AgentStep).where(e.AgentStep.run_id == run.id)
            )
        )
        assert len(calls) == 1
        call = calls[0]
        assert (call.versions["workflow"], call.versions["workflow_version"]) == identity
        invocation = await session.scalar(
            select(InvocationRow).where(InvocationRow.model_call_id == call.id)
        )
        provenance = invocation.data["provenance"]
        assert (provenance["workflow"], provenance["workflow_version"]) == identity
        source = provenance["source_snapshot"]
        assert (source["workflow"], source["workflow_version"]) == identity
        with pytest.raises(ModelGatewayError, match="case_incompatible"):
            replay_source(source)


async def test_research_recovery_mapping(client, prep_input, monkeypatch):
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.models.gateway import ModelGateway

    async def protected(self, context, task):
        raise ModelGatewayError("recovery_decision_required")

    monkeypatch.setattr(ModelGateway, "prepare", protected)
    _, op = await make_operation(client, prep_input, kind="company_research")
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "recovery_required"
    assert done["reason"] == "recovery_decision_required"
    assert done["allowed_actions"] == ["inspect_recovery"]
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json() == done


async def test_debrief_discovery_selected_and_historical(client):
    from test_interview_loop import actual_session, append

    actual, _ = await actual_session(client)
    actual = await append(client, actual, 1)
    first = (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                "source_kind": "actual",
                "interview_id": actual["id"],
                "expected_source_revision": actual["content_revision"],
                "question_analysis": "all",
                "overall_analysis": False,
            },
        )
    ).json()
    await client.post(f"/api/v1/interview-debriefs/{first['id']}/execute")
    second = (
        await client.post(
            f"/api/v1/interview-debriefs/{first['id']}/regenerate",
            json={
                "question_analysis": "all",
                "overall_analysis": False,
            },
        )
    ).json()
    listing = (
        await client.get("/api/v1/interview-debriefs", params={"source_id": actual["id"]})
    ).json()
    assert len(listing["items"]) == 2
    for item in listing["items"]:
        assert item["generation_id"] == item["id"]
        assert item["selected_run_id"] == second["id"]
        assert item["is_selected"] == (item["id"] == second["id"])
        current = (await client.get(item["detail_url"])).json()
        historical = (await client.get(item["historical_detail_url"])).json()
        assert current["id"] == second["id"]
        assert historical["id"] == item["id"] and historical["status"] == item["status"]
        assert historical["source_hash"] == first["source_hash"]


@pytest.mark.parametrize("new_resume", [False, True])
async def test_product_source_resume_binding(client, prep_input, new_resume):
    binding = (
        {"output_of": "resume_tailoring"}
        if new_resume
        else {"resume_revision_id": prep_input["resume_revision_id"]}
    )
    result = await run(
        client,
        {
            **prep_input,
            "targets": ["resume_tailoring", "greeting_generation"],
            "bindings": {"greeting_generation": binding},
        },
    )
    view = (
        await client.get(f"/api/v1/preparation-artifacts/{result['package_id']}/product-view")
    ).json()
    items = {item["kind"]: item for item in view["results"]}
    expected = (
        items["resume_tailoring"]["resume_revision_id"]
        if new_resume
        else prep_input["resume_revision_id"]
    )
    greeting = items["greeting_generation"]
    assert greeting["source_resume_revision_id"] == expected
    assert greeting["resume_revision_id"] is None
    interview = await run(
        client, {**prep_input, "application_package_id": result["package_id"]}, "prepare_interview"
    )
    view = (
        await client.get(f"/api/v1/preparation-artifacts/{interview['package_id']}/product-view")
    ).json()
    item = view["results"][0]
    assert item["kind"] == "interview_preparation"
    assert item["source_resume_revision_id"] == items["resume_tailoring"]["resume_revision_id"]
    assert item["resume_revision_id"] is None


async def test_operation_cleanup_preserves_uncertain_commit(sessions, tmp_path):
    from sqlalchemy import event

    from career_agent.product.operations import business_transaction
    from career_agent.resume.store import ArtifactStore

    store, ref = ArtifactStore(tmp_path), uuid4()
    store.write(ref, b"synthetic private artifact")

    def uncertain_commit(session):
        # Even a local rollback after COMMIT was attempted cannot establish its remote outcome.
        session.dispatch.after_rollback(session)
        raise RuntimeError("synthetic lost commit acknowledgement")

    with pytest.raises(RuntimeError, match="lost commit acknowledgement"):
        async with business_transaction(sessions) as session:
            session.info["artifact_cleanup"] = [(store, ref)]
            event.listen(session.sync_session, "before_commit", uncertain_commit)
    assert store._path(ref).exists()


async def test_research_guardrail_step_preserves_workflow(
    client, sessions, prep_input, monkeypatch
):
    from career_agent.domain.rules import DomainError
    from career_agent.preparation.workflows import PreparationWorkflow

    async def invalid_evidence(self):
        raise DomainError("invalid_reference")

    monkeypatch.setattr(PreparationWorkflow, "research_company", invalid_evidence)
    _, op = await make_operation(client, prep_input, kind="company_research")
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "failure" and done["reason"] == "invalid_reference"
    async with sessions() as session:
        steps = list(
            await session.scalars(
                select(e.AgentStep).where(e.AgentStep.run_id == UUID(op["run_id"]))
            )
        )
        assert steps
        assert all(step.versions["workflow"] == "company_research" for step in steps)
        assert all(
            step.versions["workflow_version"] == "company-research-product-v1" for step in steps
        )


async def test_research_without_personal_context(client, sessions, monkeypatch):
    from sqlalchemy import event

    from career_agent.preparation.workflows import PreparationWorkflow

    async def forbidden(*args, **kwargs):
        raise AssertionError("research must not validate personal inputs")

    monkeypatch.setattr(PreparationWorkflow, "validate_inputs", forbidden)
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "合成研究公司",
                "title": "开发工程师",
                "jd_text": "Python 服务开发",
            },
        )
    ).json()
    reads = []
    engine = client._transport.app.state.engine.sync_engine

    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement.lower())

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for _ in range(2):
            op = await client.post(
                f"/api/v1/companies/{job['company_id']}/research",
                json={
                    "request_id": str(uuid4()),
                    "kind": "company_research",
                    "request": {"job_revision_id": job["job_revision_id"], "mode": "fixture"},
                },
            )
            assert op.status_code == 201, op.text
            done = await client.post(f"/api/v1/operations/{op.json()['id']}/execute")
            assert done.json()["status"] == "success", done.text
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert not any("personal_facts" in q or "personal_profiles" in q for q in reads)
    async with sessions() as session:
        assert len(list(await session.scalars(select(e.CompanyResearch)))) == 1
        assert len(list(await session.scalars(select(e.ModelCall)))) == 1


async def test_raw_jd_fit_extracts_once_with_shared_run(client, sessions, prep_input):
    # prep_input provides a real verified context; this separate job has raw JD only.
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "合成岗位公司",
                "title": "开发工程师",
                "jd_text": "使用 Python 开发服务。",
            },
        )
    ).json()
    body = {**prep_input, "job_revision_id": job["job_revision_id"], "targets": ["fit_analysis"]}
    _, op = await make_operation(client, body)
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "success", done
    async with sessions() as session:
        calls = list(
            await session.scalars(
                select(e.ModelCall).join(e.AgentStep).where(e.AgentStep.run_id == op["run_id"])
            )
        )
        assert sorted(c.task_type for c in calls) == ["fit_analysis", "job_requirement_extraction"]
        requirements = list(
            await session.scalars(
                select(e.JobRequirement).where(
                    e.JobRequirement.job_revision_id == job["job_revision_id"]
                )
            )
        )
        assert requirements and all(r.source_quote in job["jd_text"] for r in requirements)
    _, other = await make_operation(client, body)
    assert (await client.post(f"/api/v1/operations/{other['id']}/execute")).json()[
        "status"
    ] == "success"
    async with sessions() as session:
        assert (
            len(
                list(
                    await session.scalars(
                        select(e.ModelCall).where(
                            e.ModelCall.task_type == "job_requirement_extraction"
                        )
                    )
                )
            )
            == 1
        )


async def test_fit_with_existing_requirements_skips_extraction(client, sessions, prep_input):
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "合成已有要求公司",
                "title": "开发工程师",
                "jd_text": "使用 Python 开发服务。",
                "requirements": [
                    {
                        "text": "使用 Python 开发服务。",
                        "category": "skill",
                        "importance": "must",
                        "source_quote": "使用 Python 开发服务。",
                    }
                ],
            },
        )
    ).json()
    _, op = await make_operation(client, {**prep_input, "job_revision_id": job["job_revision_id"]})
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "success", done
    async with sessions() as session:
        calls = list(await session.scalars(select(e.ModelCall)))
        assert [call.task_type for call in calls] == ["fit_analysis"]


async def test_applications_multi_company_filter_before_pagination(client):
    jobs = []
    for company, title in [("合成甲", "一"), ("合成乙", "二"), ("合成丙", "三"), ("合成甲", "四")]:
        existing = next((j for j in jobs if j["company_name"] == company), None)
        payload = {"company_name": company, "title": title, "jd_text": "合成职位描述"}
        if existing:
            payload["company_id"] = existing["company_id"]
        response = await client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 201, response.text
        jobs.append(response.json())
    app_id = jobs[1]["application_id"]
    response = await client.patch(
        f"/api/v1/applications/{app_id}",
        json={
            "expected_revision": 1,
            "status": "applied",
        },
    )
    assert response.status_code == 200, response.text
    companies = [("company_ids", jobs[0]["company_id"]), ("company_ids", jobs[1]["company_id"])]
    seen = []
    for offset in range(3):
        result = await client.get(
            "/api/v1/applications", params=companies + [("limit", "1"), ("offset", str(offset))]
        )
        assert result.status_code == 200, result.text
        data = result.json()
        seen.extend(a["id"] for a in data["items"])
        assert data["has_more"] == (offset < 2)
    assert set(seen) == {jobs[i]["application_id"] for i in [0, 1, 3]}
    filtered = (
        await client.get("/api/v1/applications", params=companies + [("status", "applied")])
    ).json()
    assert [a["id"] for a in filtered["items"]] == [app_id]
    duplicate = (await client.get("/api/v1/applications", params=companies + [companies[0]])).json()
    assert len(duplicate["items"]) == 3
    assert (
        await client.get("/api/v1/applications", params={"company_ids": "invalid"})
    ).status_code == 422
    assert len((await client.get("/api/v1/applications")).json()["items"]) == 4
    assert (await client.get("/api/v1/applications", params=[companies[0]] * 51)).status_code == 422


async def test_submission_note_overlay_delete_and_stable_identity(client, prep_input):
    package = await run(client, prep_input)
    product = (
        await client.get(f"/api/v1/preparation-artifacts/{package['package_id']}/product-view")
    ).json()
    resume = next(x for x in product["results"] if x["kind"] == "resume_tailoring")
    job = (await client.get("/api/v1/jobs")).json()[0]
    app = (await client.get(f"/api/v1/applications/{job['application_id']}")).json()
    base = f"/api/v1/applications/{app['id']}/submissions"
    created = (
        await client.post(
            base,
            json={
                "request_id": str(uuid4()),
                "expected_revision": app["revision"],
                "resume_revision_id": resume["resume_revision_id"],
                "render_artifact_id": resume["render_artifact_id"],
                "note": "原始备注",
            },
        )
    ).json()
    edit = {"request_id": str(uuid4()), "expected_revision": 1, "note": "更正备注"}
    response = await client.patch(base + "/" + created["id"], json=edit)
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised["note"] == "更正备注" and revised["revision"] == 2
    assert revised["created_at"] == created["created_at"]
    assert revised["resume_revision_id"] == created["resume_revision_id"]
    assert (await client.patch(base + "/" + created["id"], json=edit)).json() == revised
    noop = await client.patch(
        base + "/" + created["id"],
        json={"request_id": str(uuid4()), "expected_revision": 2, "note": "更正备注"},
    )
    assert noop.json()["revision"] == 2
    stale = await client.patch(
        base + "/" + created["id"], json={**edit, "request_id": str(uuid4())}
    )
    assert stale.status_code == 409
    deletion = {"request_id": str(uuid4()), "expected_revision": 2}
    deleted = await client.request("DELETE", base + "/" + created["id"], json=deletion)
    assert deleted.status_code == 200, deleted.text
    assert (await client.get(base)).json()["items"] == []
    assert (await client.get(f"/api/v1/applications/{app['id']}")).json()["status"] == "applied"
    assert (await client.get(f"/api/v1/applications/{app['id']}/summary")).json()[
        "submission"
    ] is None
    assert (
        await client.get(f"/api/v1/resume-revisions/{created['resume_revision_id']}/snapshot")
    ).status_code == 200
    assert (
        await client.request("DELETE", base + "/" + created["id"], json=deletion)
    ).status_code == 200


async def test_submission_allows_own_historical_greeting_but_rejects_other_application(
    client, prep_input
):
    first = await run(client, prep_input)
    job = (await client.get("/api/v1/jobs")).json()[0]
    app_id = job["application_id"]
    # Greeting is frozen against the tailored revision; use the original library Resume instead.
    source = next(
        row
        for row in (await client.get("/api/v1/resume-library/versions")).json()["items"]
        if row["id"] == prep_input["resume_revision_id"]
    )
    rendered = await client.post(
        f"/api/v1/resume-variants/{source['variant_id']}/render",
        json={"revision": source["revision"]},
    )
    assert rendered.status_code == 201, rendered.text
    report = rendered.json()
    app = (await client.get(f"/api/v1/applications/{app_id}")).json()
    payload = {
        "request_id": str(uuid4()),
        "expected_revision": app["revision"],
        "resume_revision_id": prep_input["resume_revision_id"],
        "render_artifact_id": report["id"],
        "greeting_id": first["state"]["greeting_id"],
    }
    accepted = await client.post(f"/api/v1/applications/{app_id}/submissions", json=payload)
    assert accepted.status_code == 201, accepted.text
    other = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "不同公司",
                "title": "不同职位",
                "jd_text": "开发 API",
            },
        )
    ).json()
    other_app = (await client.get(f"/api/v1/applications/{other['application_id']}")).json()
    rejected = await client.post(
        f"/api/v1/applications/{other['application_id']}/submissions",
        json={**payload, "request_id": str(uuid4()), "expected_revision": other_app["revision"]},
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "context_revision_mismatch"
    archived = await client.request(
        "DELETE",
        f"/api/v1/resume-library/versions/{source['id']}",
        json={"expected_revision": source["metadata_revision"]},
    )
    assert archived.status_code == 200, archived.text
    frozen = await client.get(
        f"/api/v1/resume-revisions/{source['id']}/snapshot?pdf={report['id']}"
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["pdf_id"] == report["id"]
    assert (await client.get(f"/api/v1/artifacts/{report['id']}/download")).status_code == 200
    history = (await client.get(f"/api/v1/applications/{app_id}/submissions")).json()
    assert history["items"][0]["resume_revision_id"] == source["id"]
    assert history["items"][0]["greeting_id"] == payload["greeting_id"]


async def test_greeting_removal_preserves_exact_history_and_guards_all_submissions(
    client, prep_input
):
    result = await run(client, prep_input)
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    rows = (
        await client.get(f"/api/v1/applications/{app['id']}/results?target=greeting_generation")
    ).json()["items"]
    target = rows[0]["result"]["target_artifact_id"]
    path = f"/api/v1/applications/{app['id']}/greetings/{target}"
    eligibility = await client.get(path)
    assert eligibility.status_code == 200, eligibility.text
    assert eligibility.json()["used_in"] == []
    request = {"request_id": str(uuid4())}
    removed = await client.request("DELETE", path, json=request)
    assert removed.status_code == 200 and removed.json()["deleted"]
    assert (await client.request("DELETE", path, json=request)).json()["deleted"]
    assert (
        await client.get(f"/api/v1/applications/{app['id']}/results?target=greeting_generation")
    ).json()["items"] == []
    assert (
        await client.get(
            f"/api/v1/preparation-artifacts/{target}/result?application_id={app['id']}"
        )
    ).status_code == 200
    other = (
        await client.post(
            "/api/v1/jobs", json={"company_name": "另一公司", "title": "岗位", "jd_text": "Python"}
        )
    ).json()
    assert (
        await client.request(
            "DELETE",
            f"/api/v1/applications/{other['application_id']}/greetings/{target}",
            json={"request_id": str(uuid4())},
        )
    ).status_code == 409
    assert result["state"]["greeting_id"]


async def test_used_greeting_cannot_be_removed_even_after_submission_deletion(client, prep_input):
    package = await run(client, prep_input)
    product = (
        await client.get(f"/api/v1/preparation-artifacts/{package['package_id']}/product-view")
    ).json()
    resume = next(x for x in product["results"] if x["kind"] == "resume_tailoring")
    greeting = next(x for x in product["results"] if x["kind"] == "greeting_generation")
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    base = f"/api/v1/applications/{app['id']}"
    recorded = await client.post(
        base + "/submissions",
        json={
            "request_id": str(uuid4()),
            "expected_revision": app["revision"],
            "resume_revision_id": resume["resume_revision_id"],
            "render_artifact_id": resume["render_artifact_id"],
            "greeting_id": greeting["result_id"],
        },
    )
    assert recorded.status_code == 201, recorded.text
    row = recorded.json()
    path = base + "/greetings/" + greeting["target_artifact_id"]
    assert (await client.request("DELETE", path, json={"request_id": str(uuid4())})).json() == {
        "deleted": False,
        "used_in": [1],
    }
    assert (
        await client.request(
            "DELETE",
            base + "/submissions/" + row["id"],
            json={"request_id": str(uuid4()), "expected_revision": 1},
        )
    ).status_code == 200
    assert (await client.request("DELETE", path, json={"request_id": str(uuid4())})).json() == {
        "deleted": False,
        "used_in": [1],
    }


async def test_tailoring_budget_rejection_is_pre_dispatch_and_does_not_replace_history(
    client, sessions, prep_input
):
    _, operation = await make_operation(
        client,
        prep_input,
        request={**prep_input, "targets": ["resume_tailoring"], "limits": {"max_model_calls": 0}},
    )
    result = await client.post(f"/api/v1/operations/{operation['id']}/execute")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "failure"
    assert result.json()["reason"] == "budget_exhausted"
    async with sessions() as session:
        assert not list(await session.scalars(select(e.ModelCall)))
    repeated = await client.post(f"/api/v1/operations/{operation['id']}/execute")
    assert repeated.json() == result.json()


async def test_deleted_optimization_is_not_reused_or_listed_but_exact_result_survives(
    client, prep_input
):
    first = await run(client, {**prep_input, "targets": ["resume_tailoring"]})
    target = first["outcome"]["targets"]["resume_tailoring"]["artifact_id"]
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    exact_path = f"/api/v1/preparation-artifacts/{target}/result?application_id={app['id']}"
    original = (await client.get(exact_path)).json()["result"]
    version = next(
        r
        for r in (await client.get("/api/v1/resume-library/versions")).json()["items"]
        if r["id"] == original["resume_revision_id"]
    )
    archived = await client.request(
        "DELETE",
        f"/api/v1/resume-library/versions/{version['id']}",
        json={"expected_revision": version["metadata_revision"]},
    )
    assert archived.status_code == 200, archived.text
    assert (
        await client.get(f"/api/v1/applications/{app['id']}/results?target=resume_tailoring")
    ).json()["items"] == []
    assert (await client.get(exact_path)).json()["result"]["content"] == original["content"]
    second = await run(client, {**prep_input, "targets": ["resume_tailoring"]})
    assert second["outcome"]["targets"]["resume_tailoring"]["artifact_id"] != target
    assert second["outcome"]["status"] == "completed"


async def test_tailoring_structured_entry_is_not_a_single_bullet(client, sessions, prep_input):
    """A grounded multi-line entry may exceed the legacy single-bullet allowance."""
    from career_agent.preparation.providers import FixtureTaskProvider

    class StructuredProvider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            result = await super().generate(candidate, context, task)
            if context.task_type == "resume_tailoring":
                item = result.output["sections"][0]["items"][0]
                item["kind"] = "entry"
                item["text"] = "\n".join([item["text"]] * 9)
                assert 180 < len(item["text"]) < 400
            return result

    inject(client, StructuredProvider())
    _, operation = await make_operation(
        client, prep_input, request={**prep_input, "targets": ["resume_tailoring"]}
    )
    response = await client.post(f"/api/v1/operations/{operation['id']}/execute")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success", response.json()
    result = (await client.get(f"/api/v1/operations/{operation['id']}/result")).json()["results"][0]
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    assert any(v["id"] == result["resume_revision_id"] for v in versions)
    async with sessions() as session:
        calls = list(
            await session.scalars(
                select(e.ModelCall).where(e.ModelCall.task_type == "resume_tailoring")
            )
        )
        assert len(calls) == 1 and calls[0].schema_validation_state == "valid"
    replay = await client.post(f"/api/v1/operations/{operation['id']}/execute")
    assert replay.json() == response.json()


async def test_task_status_is_read_only_exact_and_body_free(client, sessions, prep_input):
    _, op = await make_operation(client, prep_input)
    path = f"/api/v1/task-status/operations/{op['id']}"
    assert (await client.get(path)).json()["state"] == "pending"
    await client.post(f"/api/v1/operations/{op['id']}/execute")
    status = (await client.get(path)).json()
    assert status["state"] == "success"
    assert set(status) == {"id", "state", "reason", "selection", "workspace"}
    job = (await client.get("/api/v1/jobs")).json()[0]
    assert status["workspace"] == {
        "application_id": job["application_id"],
        "available": True,
        "reason": None,
    }
    target = (await client.get(f"/api/v1/operations/{op['id']}/result")).json()["results"][0]
    assert status["selection"] == {"result": target["target_artifact_id"]}
    async with sessions() as session:
        before = list(await session.scalars(select(e.ModelCall.id)))
    for _ in range(3):
        assert (await client.get(path)).json() == status
    async with sessions() as session:
        assert list(await session.scalars(select(e.ModelCall.id))) == before
        from career_agent.evaluation.entities import InvocationRow

        records = list(await session.scalars(select(InvocationRow)))
        assert records
        for record in records:
            assert record.data["provenance"]["execution_versions"]["task"] == record.data["name"]
    _, reused = await make_operation(client, prep_input)
    await client.post(f"/api/v1/operations/{reused['id']}/execute")
    assert (await client.get(f"/api/v1/task-status/operations/{reused['id']}")).json()[
        "state"
    ] == "reused"


async def test_task_status_orphan_is_unknown_without_mutating_operation(
    client, sessions, prep_input
):
    _, op = await make_operation(client, prep_input)
    async with sessions.begin() as session:
        row = await session.get(ProductOperation, UUID(op["id"]))
        row.status = "running"
    result = (await client.get(f"/api/v1/task-status/operations/{op['id']}")).json()
    assert result["state"] == "unknown"
    async with sessions() as session:
        assert (await session.get(ProductOperation, UUID(op["id"]))).status == "running"
        assert not list(await session.scalars(select(e.ModelCall)))
