"""Acceptance regressions exercise legacy reads and removal through real persistence."""

from uuid import UUID, uuid4

import pytest
from test_preparation import prep_input as prep_fixture

from career_agent.infrastructure import entities as e

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_legacy_mock_with_verified_exact_binding_is_visible_only_to_owner(
    client, prep_input, sessions
):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    created = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    # Legacy API creates no Product owner; exact source links remain authoritative.
    listed = (await client.get(f"/api/v1/mock-interviews?application_id={app['id']}")).json()
    assert created["id"] in [r["id"] for r in listed["items"]]
    detail = (await client.get(f"/api/v1/mock-interviews/{created['id']}")).json()
    assert detail["application_id"] == app["id"]
    other = (
        await client.post(
            "/api/v1/jobs",
            json={"company_name": "别家公司", "title": "另一个岗位", "jd_text": "Python"},
        )
    ).json()
    rows = (
        await client.get(f"/api/v1/mock-interviews?application_id={other['application_id']}")
    ).json()
    assert not rows["items"]
    async with sessions() as session:
        assert (
            await session.get(e.MockInterviewSession, UUID(created["id"]))
        ).application_id is None
    async with sessions.begin() as session:
        row = await session.get(e.MockInterviewSession, UUID(created["id"]))
        row.context = {
            **row.context,
            "binding": {**row.context["binding"], "resume_revision_id": str(uuid4())},
        }
    listed = (await client.get(f"/api/v1/mock-interviews?application_id={app['id']}")).json()
    assert not listed["items"]


async def test_legacy_fit_owner_from_exact_operation_source_can_remove(
    client, prep_input, sessions
):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    op = (
        await client.post(
            "/api/v1/operations",
            json={
                "request_id": str(uuid4()),
                "kind": "prepare_application",
                "request": {**prep_input, "targets": ["fit_analysis"]},
            },
        )
    ).json()
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "success"
    history = (
        await client.get(f"/api/v1/applications/{app['id']}/results?target=fit_analysis")
    ).json()
    target = history["items"][0]["result"]["target_artifact_id"]
    removed = await client.request(
        "DELETE",
        f"/api/v1/applications/{app['id']}/results/{target}",
        json={"request_id": str(uuid4())},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["deleted"], removed.text


async def test_research_loaded_but_not_consumed_by_fit_does_not_block_removal(client, prep_input):
    job = (await client.get("/api/v1/jobs")).json()[0]
    op = (
        await client.post(
            f"/api/v1/companies/{job['company_id']}/research",
            json={
                "kind": "company_research",
                "request_id": str(uuid4()),
                "request": {
                    "job_revision_id": prep_input["job_revision_id"],
                    "mode": "fixture",
                    "force_research_refresh": True,
                },
            },
        )
    ).json()
    report = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()[
        "research_report_id"
    ]
    from test_preparation import run

    await run(client, {**prep_input, "targets": ["fit_analysis"]})
    await run(client, {**prep_input, "targets": ["fit_analysis"]})
    removed = await client.delete(f"/api/v1/companies/{job['company_id']}/research/{report}")
    assert removed.json()["deleted"], removed.text


@pytest.mark.parametrize(
    "kind,workflow,task",
    [
        ("fit_analysis", "prepare_application", None),
        ("interview_preparation", "prepare_interview", "interview_preparation_refinement"),
    ],
)
async def test_republication_is_not_downstream_but_frozen_refinement_is(
    client, prep_input, kind, workflow, task
):
    payload = {**prep_input, **({"targets": [kind]} if kind == "fit_analysis" else {})}
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    outputs = []
    for _ in range(2):
        op = (
            await client.post(
                "/api/v1/operations",
                json={
                    "kind": workflow,
                    "request_id": str(uuid4()),
                    "application_id": app["id"],
                    "request": payload,
                },
            )
        ).json()
        done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
        assert done["status"] == "success", done
        outputs.append(done)
    result = (await client.get(f"/api/v1/applications/{app['id']}/results?target={kind}")).json()[
        "items"
    ][0]["result"]
    if task:
        draft = await client.post(
            "/api/v1/product-drafts",
            json={
                "task": task,
                "request_id": str(uuid4()),
                "application_id": app["id"],
                "source_artifact_id": result["target_artifact_id"],
                "feedback": "补充练习建议",
                "mode": "fixture",
            },
        )
        assert draft.status_code == 201, draft.text
    response = await client.request(
        "DELETE",
        f"/api/v1/applications/{app['id']}/results/{result['target_artifact_id']}",
        json={"request_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is (task is None), response.text


async def test_missing_input_capture_is_unknown_not_proof_of_no_research(
    client, prep_input, sessions
):
    from sqlalchemy import delete, select
    from test_preparation import run

    from career_agent.evaluation.entities import InvocationRow

    job = (await client.get("/api/v1/jobs")).json()[0]
    op = (
        await client.post(
            f"/api/v1/companies/{job['company_id']}/research",
            json={
                "kind": "company_research",
                "request_id": str(uuid4()),
                "request": {
                    "job_revision_id": prep_input["job_revision_id"],
                    "mode": "fixture",
                    "force_research_refresh": True,
                },
            },
        )
    ).json()
    report = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()[
        "research_report_id"
    ]
    await run(client, {**prep_input, "targets": ["fit_analysis"]})
    async with sessions.begin() as session:
        calls = select(e.ModelCall.id).where(e.ModelCall.task_type == "fit_analysis")
        await session.execute(delete(InvocationRow).where(InvocationRow.model_call_id.in_(calls)))
    result = await client.delete(f"/api/v1/companies/{job['company_id']}/research/{report}")
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "result_references_unavailable"
    assert any(
        r["id"] == report
        for r in (await client.get(f"/api/v1/companies/{job['company_id']}/research")).json()[
            "items"
        ]
    )


async def test_unconsumed_fit_in_multi_target_operation_is_not_a_dependency(client, prep_input):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    op = (
        await client.post(
            "/api/v1/operations",
            json={
                "kind": "prepare_application",
                "request_id": str(uuid4()),
                "application_id": app["id"],
                "request": {**prep_input, "targets": ["fit_analysis", "greeting_generation"]},
            },
        )
    ).json()
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "success", done
    target = (
        await client.get(f"/api/v1/applications/{app['id']}/results?target=fit_analysis")
    ).json()["items"][0]["result"]["target_artifact_id"]
    result = await client.request(
        "DELETE",
        f"/api/v1/applications/{app['id']}/results/{target}",
        json={"request_id": str(uuid4())},
    )
    assert result.status_code == 200, result.text
    assert result.json()["deleted"], result.text


async def test_greeting_nested_actual_research_input_blocks_removal(client, prep_input):
    from test_preparation import run

    job = (await client.get("/api/v1/jobs")).json()[0]
    op = (
        await client.post(
            f"/api/v1/companies/{job['company_id']}/research",
            json={
                "kind": "company_research",
                "request_id": str(uuid4()),
                "request": {
                    "job_revision_id": prep_input["job_revision_id"],
                    "mode": "fixture",
                    "force_research_refresh": True,
                },
            },
        )
    ).json()
    report = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()[
        "research_report_id"
    ]
    generated = await run(client, {**prep_input, "targets": ["greeting_generation"]})
    assert generated["state"]["greeting_id"]
    removed = await client.delete(f"/api/v1/companies/{job['company_id']}/research/{report}")
    assert removed.status_code == 200, removed.text
    assert not removed.json()["deleted"]
    assert any(value.startswith("招呼语（") for value in removed.json()["used_by"])
