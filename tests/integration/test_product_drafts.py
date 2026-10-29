from uuid import uuid4

import pytest
from test_preparation import prep_input as prep_fixture

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def draft(client, task, **kw):
    request = {"request_id": str(uuid4()), "task": task, **kw}
    created = await client.post("/api/v1/product-drafts", json=request)
    assert created.status_code == 201, created.text
    id = created.json()["id"]
    assert (await client.post("/api/v1/product-drafts", json=request)).json()["id"] == id
    result = await client.post(f"/api/v1/product-drafts/{id}/execute")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed", result.text
    return result.json()


async def test_base_draft_without_manual_facts(client):
    profile = (
        await client.put(
            "/api/v1/profile",
            json={
                "expected_revision": 0,
                "data": {
                    "display_name": "合成用户",
                    "projects": [
                        {
                            "organization": "模拟项目",
                            "role": "开发",
                            "description": "使用 Python 实现事务回滚测试。",
                        }
                    ],
                },
            },
        )
    ).json()
    resume = await draft(client, "base_resume_drafting", profile_id=profile["id"])
    saved = await client.post(f"/api/v1/product-drafts/{resume['id']}/adopt", json={})
    assert saved.status_code == 200, saved.text
    again = await client.post(f"/api/v1/product-drafts/{resume['id']}/adopt", json={})
    assert again.json()["adopted"] == saved.json()["adopted"]
    assert saved.json()["accepted_model_call_id"]


@pytest.mark.parametrize(
    "target,task,workflow",
    [
        ("greeting_generation", "greeting_refinement", "prepare_application"),
        ("resume_tailoring", "resume_refinement", "prepare_application"),
        ("interview_preparation", "interview_preparation_refinement", "prepare_interview"),
    ],
)
async def test_refinement_new_artifact_and_provenance(
    client, sessions, prep_input, target, task, workflow
):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    result = await client.post(
        f"/api/v1/workflows/{workflow}",
        json={**prep_input, **({"targets": [target]} if workflow == "prepare_application" else {})},
    )
    assert result.json()["outcome"]["status"] == "completed"
    source = result.json()["outcome"]["targets"][target]["artifact_id"]
    from sqlalchemy import func, select
    from test_frontend_discovery import HEADERS, authorize

    from career_agent.infrastructure.entities import ModelCall

    authorize(client)
    initial = (
        await client.get(f"/api/v1/applications/{app['id']}/results?target={target}")
    ).json()["items"][0]["result"]
    async with sessions() as session:
        before = await session.scalar(select(func.count()).select_from(ModelCall))
    votes = []
    for vote in ["thumbs_up", "thumbs_down"]:
        response = await client.post(
            "/api/v1/evaluation/feedback",
            json={
                "subject": initial["feedback_target"],
                "vote": vote,
                "comment": "突出事务测试",
                "application_id": app["id"],
            },
        )
        assert response.status_code == 201, response.text
        votes.append(response.json()["id"])
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ModelCall)) == before
    feedback = await client.get(
        f"/api/v1/evaluation/feedback?application_id={app['id']}", headers=HEADERS
    )
    assert len(feedback.json()["items"]) == 2
    assert feedback.json()["items"][0]["comment"] == "突出事务测试"
    assert feedback.json()["items"][0]["generation_provenance"]["model_call_id"]
    proposal = await draft(
        client,
        task,
        source_artifact_id=source,
        feedback_id=votes[-1],
        application_id=app["id"],
        intent="refine",
        feedback="简洁一些，突出事务测试。",
    )
    saved = await client.post(f"/api/v1/product-drafts/{proposal['id']}/adopt", json={})
    assert saved.status_code == 200, saved.text
    assert saved.json()["adopted"]["target_artifact_id"] != source
    lineage = await client.get(
        f"/api/v1/evaluation/refinements?feedback_id={votes[-1]}", headers=HEADERS
    )
    assert lineage.json()["items"][0]["source_artifact_id"] == source
    assert lineage.json()["items"][0]["adopted"] == saved.json()["adopted"]
    history = (
        await client.get(f"/api/v1/applications/{app['id']}/results?target={target}")
    ).json()["items"]
    assert len(history) == 2
    assert (
        history[0]["result"]["feedback_target"]["accepted_model_call_id"]
        == proposal["accepted_model_call_id"]
    )
