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

    mock = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    job = (await client.get("/api/v1/jobs")).json()[0]
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
