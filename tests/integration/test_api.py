from uuid import uuid4

import pytest
from sqlalchemy import select

from career_agent.infrastructure import entities as e

pytestmark = pytest.mark.integration


async def test_health_profile_and_fact_lifecycle(client, sessions, synthetic):
    assert (await client.get("/api/v1/health")).json()["milestone"] == "v0.1a"
    assert (await client.get("/api/v1/profile")).status_code == 404
    payload = {"expected_revision": 0, "data": synthetic["profile"]}
    response = await client.put("/api/v1/profile", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    assert (await client.put("/api/v1/profile", json=payload)).status_code == 409
    payload["expected_revision"] = 1
    assert (await client.put("/api/v1/profile", json=payload)).json()["revision"] == 2
    assert (await client.get("/api/v1/profile")).json()["revision"] == 2
    fact = (await client.post("/api/v1/facts", json=synthetic["fact"])).json()
    assert fact["status"] == "proposed"
    verified = await client.post(f"/api/v1/facts/{fact['id']}/verify")
    assert verified.status_code == 200 and verified.json()["verified_at"] is not None
    assert (await client.post(f"/api/v1/facts/{fact['id']}/verify")).status_code == 409
    replacement = {
        **synthetic["fact"],
        "statement": "Updated synthetic fact",
        "expected_revision": 1,
    }
    response = await client.post(f"/api/v1/facts/{fact['id']}/supersede", json=replacement)
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["status"] == "proposed" and new["verified_at"] is None
    assert new["revision"] == 2 and new["replaces_id"] == fact["id"]
    assert new["lineage_id"] == fact["lineage_id"]
    old = next(f for f in (await client.get("/api/v1/facts")).json() if f["id"] == fact["id"])
    assert old["statement"] == synthetic["fact"]["statement"] and old["status"] == "superseded"
    assert (
        await client.post(f"/api/v1/facts/{fact['id']}/supersede", json=replacement)
    ).status_code == 409
    async with sessions() as session:
        profiles = list(await session.scalars(select(e.PersonalProfile)))
        assert len(profiles) == 2


async def test_job_revision_application_history(client, sessions, synthetic):
    response = await client.post("/api/v1/jobs", json=synthetic["job"])
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["revision"] == 1 and len(job["requirements"]) == 1
    assert (await client.get(f"/api/v1/jobs/{job['id']}")).json() == job
    assert len((await client.get("/api/v1/jobs")).json()) == 1
    revision = {
        "expected_revision": 1,
        "title": "Synthetic revised title",
        "jd_text": "New synthetic JD",
    }
    response = await client.post(f"/api/v1/jobs/{job['id']}/revisions", json=revision)
    assert response.status_code == 201 and response.json()["revision"] == 2
    assert (
        await client.post(f"/api/v1/jobs/{job['id']}/revisions", json=revision)
    ).status_code == 409
    async with sessions() as session:
        revisions = list(
            await session.scalars(select(e.JobRevision).order_by(e.JobRevision.revision))
        )
        assert len(revisions) == 2 and revisions[0].jd_text == synthetic["job"]["jd_text"]
    url = f"/api/v1/applications/{job['application_id']}"
    application = (await client.get(url)).json()
    assert application["status"] == "tracking" and application["events"][0]["kind"] == "created"
    # Merely editing a job has not recorded any application.
    bad = await client.patch(url, json={"expected_revision": 1, "status": "offer"})
    assert bad.status_code == 409
    response = await client.patch(url, json={"expected_revision": 1, "status": "applied"})
    assert response.status_code == 200, response.text
    assert response.json()["events"][-1]["from_status"] == "tracking"
    assert (
        await client.patch(url, json={"expected_revision": 1, "status": "interviewing"})
    ).status_code == 409
    correction = {
        "expected_revision": 2,
        "status": "tracking",
        "correction": True,
        "reason": "Synthetic correction",
    }
    assert (await client.patch(url, json=correction)).json()["events"][-1]["kind"] == "correction"
    assert (await client.post(url + "/notes", json={"text": "Synthetic note"})).status_code == 201
    application = (await client.get(url)).json()
    assert application["revision"] == 4
    assert [event["sequence"] for event in application["events"]] == [1, 2, 3, 4]
    assert application["status"] == "tracking"


async def test_interview_knowledge(client, synthetic):
    job = (await client.post("/api/v1/jobs", json=synthetic["job"])).json()
    response = await client.post(
        "/api/v1/interviews",
        json={"application_id": job["application_id"], "round_name": "Synthetic technical round"},
    )
    assert response.status_code == 201, response.text
    interview = response.json()
    url = f"/api/v1/interviews/{interview['id']}/notes"
    assert (await client.post(url, json={"text": "Synthetic question"})).status_code == 201
    response = await client.post(url, json={"text": "Synthetic follow-up"})
    assert len(response.json()["notes"]) == 2
    response = await client.post(
        "/api/v1/knowledge-notes",
        json={
            "title": "Synthetic lesson",
            "content": "Practice SQL",
            "interview_id": interview["id"],
        },
    )
    assert response.status_code == 201
    assert len((await client.get("/api/v1/knowledge-notes")).json()) == 1


async def test_runtime_reads(client, sessions):
    async with sessions.begin() as session:
        run = e.AgentRun(
            workflow="foundation_test",
            budget={"token_limit": 500},
            consumed_usage={"input_tokens": 0, "estimated_cost": "0"},
        )
        session.add(run)
        await session.flush()
        step = e.AgentStep(run_id=run.id, sequence=1, node="contract_test")
        session.add(step)
        await session.flush()
        model = e.ModelCall(step_id=step.id, task_type="parse", provider="fake", model="fixture")
        tool = e.ToolCall(step_id=step.id, tool_name="synthetic_fixture")
        session.add_all([model, tool])
        await session.flush()
        session.add(e.Observation(tool_call_id=tool.id, status=e.ObservationStatus.OK))
        session.add(e.Observation(model_call_id=model.id, status=e.ObservationStatus.OK))
        run_id = run.id
    response = await client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200, response.text
    assert response.json()["workflow_version"] is None
    steps = (await client.get(f"/api/v1/runs/{run_id}/steps")).json()
    assert len(steps) == 1 and steps[0]["versions"]["prompt_version"] is None
    assert (await client.post("/api/v1/runs", json={})).status_code == 404


@pytest.mark.parametrize(
    "path,payload,status",
    [
        ("/facts", {"statement": "Synthetic", "category": "project", "status": "verified"}, 422),
        ("/jobs", {"company_name": "Synthetic"}, 422),
        ("/interviews", {"application_id": str(uuid4()), "round_name": "Synthetic"}, 404),
        (
            "/knowledge-notes",
            {"title": "Synthetic", "content": "Synthetic", "interview_id": str(uuid4())},
            404,
        ),
    ],
)
async def test_invalid_payloads(client, path, payload, status):
    response = await client.post("/api/v1" + path, json=payload)
    assert response.status_code == status
    assert set(response.json()) == {"error"}


async def test_missing_and_invalid_ids(client):
    assert (await client.get("/api/v1/jobs/not-a-uuid")).status_code == 422
    assert (await client.get(f"/api/v1/jobs/{uuid4()}")).status_code == 404
    assert (await client.get(f"/api/v1/runs/{uuid4()}/steps")).status_code == 404
    assert (await client.get("/api/v1/jobs?limit=1000")).status_code == 422


async def test_explicit_reject_fact(client, synthetic):
    fact = (await client.post("/api/v1/facts", json=synthetic["fact"])).json()
    url = f"/api/v1/facts/{fact['id']}"
    assert (await client.post(url + "/reject")).json()["status"] == "rejected"
    assert (await client.post(url + "/verify")).status_code == 409
    assert (await client.post(url + "/reject")).status_code == 409


async def test_concurrent_updates_use_revision_lock(client, synthetic):
    import asyncio

    job = (await client.post("/api/v1/jobs", json=synthetic["job"])).json()
    url = f"/api/v1/applications/{job['application_id']}"
    responses = await asyncio.gather(
        *[client.patch(url, json={"expected_revision": 1, "status": "applied"}) for _ in range(2)]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len((await client.get(url)).json()["events"]) == 2


async def test_failed_fact_replacement_rolls_back(client, synthetic):
    fact = (await client.post("/api/v1/facts", json=synthetic["fact"])).json()
    await client.post(f"/api/v1/facts/{fact['id']}/verify")
    response = await client.post(
        f"/api/v1/facts/{fact['id']}/supersede",
        json={**synthetic["fact"], "expected_revision": 1, "source_document_id": str(uuid4())},
    )
    assert response.status_code == 404
    facts = (await client.get("/api/v1/facts")).json()
    assert len(facts) == 1 and facts[0]["status"] == "verified"
