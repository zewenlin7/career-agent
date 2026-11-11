"""Current generation contracts through the real gateway, validator and persistence."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from test_preparation import inject, run
from test_preparation import prep_input as prep_fixture

from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.providers import FixtureTaskProvider
from career_agent.preparation.research import FixtureResearchAdapter

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_explicit_research_refresh_is_company_only_and_failure_retains_history(
    client, sessions, prep_input
):
    class Search(FixtureResearchAdapter):
        calls = 0

        async def search(self, query):
            self.calls += 1
            return await super().search(query)

    class Provider(FixtureTaskProvider):
        inputs = []
        fail = False

        async def generate(self, candidate, context, task):
            if context.task_type == "company_research_synthesis":
                self.inputs.append(task.inputs["context"])
                if self.fail:
                    raise ModelGatewayError("synthetic_failure")
            return await super().generate(candidate, context, task)

    search, provider = Search(), Provider()
    inject(client, provider, research=search)
    job = (await client.get("/api/v1/jobs")).json()[0]
    other = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_id": job["company_id"],
                "company_name": job["company_name"],
                "title": "其他职位",
                "jd_text": "不同要求",
            },
        )
    ).json()
    reports = []
    for jd in [job["job_revision_id"], other["job_revision_id"]]:
        op = (
            await client.post(
                f"/api/v1/companies/{job['company_id']}/research",
                json={
                    "kind": "company_research",
                    "request_id": str(uuid4()),
                    "request": {
                        "job_revision_id": jd,
                        "mode": "fixture",
                        "force_research_refresh": True,
                    },
                },
            )
        ).json()
        done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
        assert done["status"] == "success", done
        reports.append(done["research_report_id"])
        before = search.calls
        assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json() == done
        assert search.calls == before
    assert reports[0] != reports[1] and search.calls == 2
    assert all(set(value) == {"company", "evidence"} for value in provider.inputs)
    assert provider.inputs[0]["company"] == provider.inputs[1]["company"]
    provider.fail = True
    op = (
        await client.post(
            f"/api/v1/companies/{job['company_id']}/research",
            json={
                "kind": "company_research",
                "request_id": str(uuid4()),
                "request": {
                    "job_revision_id": job["job_revision_id"],
                    "mode": "fixture",
                    "force_research_refresh": True,
                },
            },
        )
    ).json()
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()[
        "status"
    ] == "failure"
    calls = search.calls
    for report in reports:
        assert (
            await client.get(f"/api/v1/companies/{job['company_id']}/research/{report}")
        ).status_code == 200
    assert search.calls == calls
    async with sessions() as session:
        assert len(list(await session.scalars(select(e.CompanyResearch)))) == 2


async def test_fit_current_schema_persists_and_reaches_downstream_without_legacy_slot(
    client, prep_input
):
    class Provider(FixtureTaskProvider):
        inputs = {}

        async def generate(self, candidate, context, task):
            self.inputs[context.task_type] = task.inputs["context"]
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    result = await run(client, prep_input)
    assert result["outcome"]["status"] == "completed", result
    fit = (
        await client.get(f"/api/v1/preparation-artifacts/{result['state']['fit_analysis_id']}")
    ).json()
    assert all("missing_evidence" not in item for item in fit["data"]["output"]["items"])
    assert "job_requirement_extraction" in provider.inputs
    # Independent targets intentionally omit optional Fit; do not introduce a new dependency.
    for task in ["resume_tailoring", "greeting_generation"]:
        assert provider.inputs[task]["fit"] is None
    interview = await run(
        client, {**prep_input, "application_package_id": result["package_id"]}, "prepare_interview"
    )
    assert interview["state"]["status"] == "completed", interview
    # Interviewers see only the bound Resume, not Fit's broader personal evidence.
    assert provider.inputs["interview_preparation"]["fit"] is None
    assert provider.inputs["interview_preparation"]["variant"]["sections"]


async def test_legacy_research_readable_but_not_execution_reused_observation_stays_reusable(
    client, sessions, prep_input
):
    from datetime import timedelta
    from uuid import UUID

    class Search(FixtureResearchAdapter):
        calls = 0

        async def search(self, query):
            self.calls += 1
            return await super().search(query)

    search = Search()
    inject(client, research=search)
    job = (await client.get("/api/v1/jobs")).json()[0]

    async def execute():
        op = (
            await client.post(
                f"/api/v1/companies/{job['company_id']}/research",
                json={
                    "kind": "company_research",
                    "request_id": str(uuid4()),
                    "request": {"job_revision_id": job["job_revision_id"], "mode": "fixture"},
                },
            )
        ).json()
        result = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
        assert result["status"] == "success", result
        return result["research_report_id"]

    first = await execute()
    # Isolated fixture simulates pre-contract rows; no business database is accessed.
    async with sessions.begin() as session:
        row = await session.get(e.CompanyResearch, UUID(first))
        row.data = {**row.data, "compatibility_versions": None}
    second = await execute()
    assert second != first and search.calls == 1
    async with sessions.begin() as session:
        row = await session.get(e.CompanyResearch, UUID(first))
        row.expires_at = e.utcnow() - timedelta(hours=1)
    old = (await client.get(f"/api/v1/companies/{job['company_id']}/research/{first}")).json()
    assert old["historical_readable"] and not old["reusable_for_current_execution"]
    assert old["data"]["report"]["conclusions"]
    assert (
        len((await client.get(f"/api/v1/companies/{job['company_id']}/research")).json()["items"])
        == 2
    )


@pytest.mark.parametrize("kind", ["company_research", "prepare_application"])
async def test_read_navigation_does_not_wait_for_provider(client, prep_input, kind):
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()

    class PausedProvider(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            entered.set()
            await release.wait()
            return await super().generate(candidate, context, task)

    inject(client, PausedProvider(), research=FixtureResearchAdapter())
    job = (await client.get("/api/v1/jobs")).json()[0]
    request = {"job_revision_id": job["job_revision_id"], "mode": "fixture"}
    if kind == "prepare_application":
        request.update(profile_id=prep_input["profile_id"], targets=["fit_analysis"])
    op = (
        await client.post(
            "/api/v1/operations",
            json={
                "kind": kind,
                "request_id": str(uuid4()),
                "request": request,
            },
        )
    ).json()
    execution = asyncio.create_task(client.post(f"/api/v1/operations/{op['id']}/execute"))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        for path in [
            f"applications/{job['application_id']}",
            f"applications/{job['application_id']}/context",
            f"applications/{job['application_id']}/summary",
            f"operations/{op['id']}",
        ]:
            try:
                response = await asyncio.wait_for(client.get(f"/api/v1/{path}"), 2)
            except TimeoutError:
                pytest.fail(f"navigation blocked on {path}")
            assert response.status_code == 200
        assert not execution.done()
    finally:
        release.set()
        await execution


async def test_fit_new_intent_reuses_exact_artifact_but_changed_inputs_and_failures_do_not(
    client, prep_input
):
    class Provider(FixtureTaskProvider):
        calls = []
        invalid = False

        async def generate(self, candidate, context, task):
            self.calls.append(context.task_type)
            response = await super().generate(candidate, context, task)
            if self.invalid and context.task_type == "fit_analysis":
                response.output["items"][0]["requirement_ref"] = str(uuid4())
            return response

    provider = Provider()
    inject(client, provider)
    job = (await client.get("/api/v1/jobs")).json()[0]

    async def execute(request, request_id=None):
        payload = {
            "kind": "prepare_application",
            "request_id": str(request_id or uuid4()),
            "request": request,
        }
        op = (await client.post("/api/v1/operations", json=payload)).json()
        done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
        view = (
            await client.get(f"/api/v1/preparation-artifacts/{done['package_id']}/product-view")
        ).json()
        return op, done, view

    body = {
        "job_revision_id": job["job_revision_id"],
        "profile_id": prep_input["profile_id"],
        "targets": ["fit_analysis"],
        "fit_input": "profile",
        "mode": "fixture",
    }
    token = uuid4()
    op, done, first = await execute(body, token)
    assert done["status"] == "success" and not first["results"][0]["reused"]
    calls = list(provider.calls)
    replay, replay_done, _ = await execute(body, token)
    assert replay["id"] == op["id"] and replay_done == done
    newer, _, reused = await execute(body)
    assert newer["id"] != op["id"]
    assert newer["request_id"] != op["request_id"]
    assert reused["results"][0]["reused"]
    first_id = first["results"][0]["target_artifact_id"]
    assert reused["results"][0]["target_artifact_id"] == first_id
    assert provider.calls == calls
    for source in ["resume", "both"]:
        _, changed, view = await execute(
            {**body, "fit_input": source, "resume_revision_id": prep_input["resume_revision_id"]}
        )
        assert changed["status"] == "success"
        assert not view["results"][0]["reused"]
        assert view["results"][0]["target_artifact_id"] != first_id
    profile = (await client.get("/api/v1/profile")).json()
    updated = (
        await client.put(
            "/api/v1/profile",
            json={
                "expected_revision": profile["revision"],
                "data": {**profile["data"], "display_name": "Changed source"},
            },
        )
    ).json()
    _, changed, view = await execute({**body, "profile_id": updated["id"]})
    assert changed["status"] == "success" and not view["results"][0]["reused"]
    assert view["results"][0]["target_artifact_id"] != first_id
    assert provider.calls.count("job_requirement_extraction") == 1
    assert provider.calls.count("fit_analysis") == 4
    history_url = f"/api/v1/applications/{job['application_id']}/results?target=fit_analysis"
    before = (await client.get(history_url)).json()
    assert len(before["items"]) == 4
    summary_url = f"/api/v1/applications/{job['application_id']}/summary"
    summary = (await client.get(summary_url)).json()
    jd = (
        await client.post(
            f"/api/v1/jobs/{job['id']}/revisions",
            json={
                "expected_revision": 1,
                "title": job["title"],
                "jd_text": "必须具备不同领域开发经验。",
            },
        )
    ).json()
    provider.invalid = True
    _, failed, failed_view = await execute({**body, "job_revision_id": jd["job_revision_id"]})
    assert failed["status"] == "failure"
    assert failed_view["results"][0]["status"] == "failed"
    assert (await client.get(history_url)).json() == before
    after = (await client.get(summary_url)).json()
    old_fit = next(item for item in summary["preparation"] if item["kind"] == "fit_analysis")
    new_fit = next(item for item in after["preparation"] if item["kind"] == "fit_analysis")
    assert new_fit["href"] == old_fit["href"]
    assert new_fit["created_at"] == old_fit["created_at"]
    assert new_fit["stale"]  # New JD, old successful artifact remains readable.
