"""Application defaults remain independent from historical execution inputs."""

from uuid import uuid4

import pytest
from test_preparation import prep_input as prep_fixture

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_binding_default_cas_and_frozen_operation(client, prep_input):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    path = f"/api/v1/applications/{app['id']}/context"
    initial = (await client.get(path)).json()
    assert initial["profile_id"] is None
    assert initial["resume_revision_id"] is None
    change = {
        "expected_revision": initial["revision"],
        **prep_input,
    }
    bound = await client.put(path, json=change)
    assert bound.status_code == 200, bound.text
    assert bound.json()["revision"] == 2
    assert (await client.put(path, json=change)).status_code == 409
    payload = {
        "request_id": str(uuid4()),
        "kind": "prepare_application",
        "application_binding": {"application_id": app["id"], "revision": 2},
        "request": {**prep_input, "targets": ["fit_analysis"]},
    }
    operation = await client.post("/api/v1/operations", json=payload)
    assert operation.status_code == 201, operation.text
    # Changing defaults cannot mutate the already accepted operation or its retries.
    changed = await client.put(
        path, json={**change, "expected_revision": 2, "resume_revision_id": None}
    )
    assert changed.status_code == 200
    repeated = await client.post("/api/v1/operations", json=payload)
    assert repeated.json()["id"] == operation.json()["id"]
    stale = await client.post("/api/v1/operations", json={**payload, "request_id": str(uuid4())})
    assert stale.status_code == 409
    result = await client.post(f"/api/v1/operations/{operation.json()['id']}/execute")
    assert result.json()["status"] == "success", result.text
    foreign = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "另一家公司",
                "title": "研发",
                "jd_text": "Python 开发",
            },
        )
    ).json()
    rejected = await client.put(
        path,
        json={
            **change,
            "expected_revision": 3,
            "job_revision_id": foreign["job_revision_id"],
        },
    )
    assert rejected.status_code == 422
    assert (await client.get(path)).json()["revision"] == 3


async def test_profile_noop_preserves_identity_but_does_not_bypass_cas(client, prep_input):
    profile = (await client.get("/api/v1/profile")).json()
    payload = {"expected_revision": profile["revision"], "data": profile["data"]}
    same = await client.put("/api/v1/profile", json=payload)
    assert same.status_code == 200, same.text
    assert same.json()["id"] == profile["id"]
    assert same.json()["revision"] == profile["revision"]
    stale = await client.put("/api/v1/profile", json={**payload, "expected_revision": 0})
    assert stale.status_code == 409


async def test_interview_prep_uses_selected_base_without_tailoring_or_pdf(
    client, sessions, prep_input
):
    from sqlalchemy import select

    from career_agent.infrastructure import entities as e

    response = await client.post("/api/v1/workflows/prepare_interview", json=prep_input)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["outcome"]["status"] == "completed", result
    async with sessions() as session:
        calls = list(await session.scalars(select(e.ModelCall)))
        assert {call.task_type for call in calls} == {
            "job_requirement_extraction",
            "interview_preparation",
        }
        assert not list(await session.scalars(select(e.RenderArtifact)))
    reused = await client.post("/api/v1/workflows/prepare_interview", json=prep_input)
    assert reused.json()["outcome"]["status"] == "completed"
    async with sessions() as session:
        assert len(list(await session.scalars(select(e.ModelCall)))) == len(calls)


async def test_task_history_only_returns_successful_requested_kind(client, prep_input):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    for target in ["fit_analysis", "greeting_generation"]:
        result = await client.post(
            "/api/v1/workflows/prepare_application",
            json={
                **prep_input,
                "targets": [target],
            },
        )
        assert result.json()["outcome"]["status"] == "completed", result.text
    for target in ["fit_analysis", "greeting_generation"]:
        history = await client.get(
            f"/api/v1/applications/{app['id']}/results", params={"target": target}
        )
        assert history.status_code == 200, history.text
        assert len(history.json()["items"]) == 1
        item = history.json()["items"][0]["result"]
        assert item["kind"] == target and item["status"] == "success"
        assert item["content"] and item["feedback_target"]


async def test_resume_noop_and_historical_content_append_current_head(client, sessions, prep_input):
    from uuid import UUID

    from career_agent.infrastructure import entities as e

    async with sessions() as session:
        revision = await session.get(
            e.ResumeVariantRevision, UUID(prep_input["resume_revision_id"])
        )
        variant_id = str(revision.resume_variant_id)
        original = dict(revision.document)
    path = f"/api/v1/resume-variants/{variant_id}/revisions"
    same = await client.post(path, json={"expected_revision": 1, "document": original})
    assert same.status_code == 201, same.text
    assert same.json()["revision"] == 1
    changed = {**original, "metadata": {**original["metadata"], "label": "第二版合成简历"}}
    second = await client.post(path, json={"expected_revision": 1, "document": changed})
    assert second.json()["revision"] == 2
    stale = await client.post(path, json={"expected_revision": 1, "document": original})
    assert stale.status_code == 409
    third = await client.post(path, json={"expected_revision": 2, "document": original})
    assert third.status_code == 201, third.text
    assert third.json()["revision"] == 3
    assert third.json()["document"] == original


async def test_resume_binding_derives_profile_without_persistent_profile_pointer(
    client, sessions, prep_input
):
    from sqlalchemy import select

    from career_agent.product.entities import ApplicationBinding

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    path = f"/api/v1/applications/{app['id']}/context"
    before = (await client.get(path)).json()
    saved = await client.put(
        path,
        json={
            "expected_revision": before["revision"],
            "profile_id": None,
            "resume_revision_id": prep_input["resume_revision_id"],
            "job_revision_id": prep_input["job_revision_id"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["profile_id"] == prep_input["profile_id"]
    async with sessions() as session:
        row = await session.scalar(select(ApplicationBinding))
        assert row.profile_id is None
        assert str(row.resume_revision_id) == prep_input["resume_revision_id"]


@pytest.mark.parametrize("source", ["profile", "resume", "both"])
async def test_fit_explicit_source_is_independent_of_application_binding(client, source, sessions):
    from sqlalchemy import select
    from test_profile_records import named_source

    from career_agent.evaluation.entities import InvocationRow
    from career_agent.infrastructure import entities as e

    profile = await named_source(client)
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "合成公司",
                "title": "测试开发",
                "jd_text": "需要 Python 和事务测试经验。",
            },
        )
    ).json()
    work = (
        await client.post("/api/v1/resume-workspaces", json={"profile_id": profile["profile_id"]})
    ).json()
    rendered = (
        await client.post(
            f"/api/v1/resume-workspaces/{work['id']}/render", json={"expected_revision": 1}
        )
    ).json()
    resume_id = rendered["resume_revision_id"]
    library = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    resume_profile = next(row["profile_id"] for row in library if row["id"] == resume_id)
    payload = {
        "request_id": str(uuid4()),
        "kind": "prepare_application",
        "request": {
            "profile_id": resume_profile if source == "resume" else profile["profile_id"],
            "resume_revision_id": resume_id if source != "profile" else None,
            "job_revision_id": job["job_revision_id"],
            "targets": ["fit_analysis"],
            "fit_input": source,
        },
    }
    created = await client.post("/api/v1/operations", json=payload)
    assert created.status_code == 201, created.text
    result = await client.post(f"/api/v1/operations/{created.json()['id']}/execute")
    assert result.json()["status"] == "success", result.text
    async with sessions() as session:
        calls = list(
            await session.scalars(
                select(e.ModelCall).where(e.ModelCall.task_type == "fit_analysis")
            )
        )
        assert len(calls) == 1
        invocation = await session.scalar(
            select(InvocationRow).where(InvocationRow.model_call_id == calls[0].id)
        )
        assert invocation is not None
        model_input = invocation.data["input_snapshot"]["context"]
        assert model_input["fit_input"]["source"] == source
        assert len({fact["id"] for fact in model_input["facts"]}) == len(model_input["facts"])
        if source != "profile":
            assert model_input["fit_input"]["resume"]["profile_id"] == resume_profile
    binding = (await client.get(f"/api/v1/applications/{job['application_id']}/context")).json()
    assert binding["resume_revision_id"] is None


async def test_mock_derives_profile_from_persistent_resume_binding(client, prep_input):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    bound = await client.put(
        f"/api/v1/applications/{app['id']}/context",
        json={"expected_revision": 1, **prep_input, "profile_id": None},
    )
    assert bound.status_code == 200, bound.text
    created = await client.post(
        "/api/v1/mock-interviews",
        json={
            "context": prep_input,
            "application_binding": {
                "application_id": app["id"],
                "revision": bound.json()["revision"],
            },
        },
    )
    assert created.status_code == 201, created.text
