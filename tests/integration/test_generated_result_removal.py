"""Visibility removal protects real frozen consumers, not a result's own generation chain."""

from uuid import uuid4

import pytest
from test_preparation import prep_input as prep_fixture
from test_preparation import run

prep_input = prep_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("target_kind", ["fit_analysis", "interview_preparation"])
async def test_fit_removal_excludes_reuse_and_keeps_original_artifact(
    client, prep_input, target_kind
):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    binding = (
        await client.put(
            f"/api/v1/applications/{app['id']}/context", json={"expected_revision": 1, **prep_input}
        )
    ).json()
    operation = (
        await client.post(
            "/api/v1/operations",
            json={
                "request_id": str(uuid4()),
                "kind": "prepare_interview"
                if target_kind == "interview_preparation"
                else "prepare_application",
                **(
                    {"application_id": app["id"]}
                    if target_kind == "fit_analysis"
                    else {
                        "application_binding": {
                            "application_id": app["id"],
                            "revision": binding["revision"],
                        }
                    }
                ),
                "request": {
                    **prep_input,
                    **(
                        {} if target_kind == "interview_preparation" else {"targets": [target_kind]}
                    ),
                },
            },
        )
    ).json()
    executed = (await client.post(f"/api/v1/operations/{operation['id']}/execute")).json()
    assert executed["status"] == "success", executed
    history = (
        await client.get(f"/api/v1/applications/{app['id']}/results?target={target_kind}")
    ).json()
    item = history["items"][0]["result"]
    target = item["target_artifact_id"]
    other_job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "另一申请公司",
                "title": "另一职位",
                "jd_text": "Python 开发",
            },
        )
    ).json()
    other_id = other_job["application_id"]
    cross = await client.request(
        "DELETE",
        f"/api/v1/applications/{other_id}/results/{target}",
        json={"request_id": str(uuid4())},
    )
    assert cross.status_code == 409
    path = f"/api/v1/applications/{app['id']}/results/{target}"
    body = {"request_id": str(uuid4())}
    deleted = await client.request("DELETE", path, json=body)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"]
    assert (await client.request("DELETE", path, json=body)).json()["deleted"]
    assert not (
        await client.get(f"/api/v1/applications/{app['id']}/results?target={target_kind}")
    ).json()["items"]
    assert (
        await client.get(f"/api/v1/preparation-artifacts/{item['result_id']}")
    ).status_code == 200
    regenerated = await run(
        client,
        {
            **prep_input,
            **({} if target_kind == "interview_preparation" else {"targets": [target_kind]}),
        },
        "prepare_interview" if target_kind == "interview_preparation" else "prepare_application",
    )
    assert (
        regenerated["state"][
            "interview_prep_id" if target_kind == "interview_preparation" else "fit_analysis_id"
        ]
        != item["result_id"]
    )


async def test_research_company_visibility_and_frozen_prep_reference(client, prep_input):
    job = (await client.get("/api/v1/jobs")).json()[0]
    reports = []
    for _ in range(2):
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
        done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
        assert done["status"] == "success", done
        reports.append(done["research_report_id"])
    prepared = await run(
        client, {**prep_input, "research_report_id": reports[0]}, "prepare_interview"
    )
    assert prepared["state"]["status"] == "completed", prepared
    base = f"/api/v1/companies/{job['company_id']}/research"
    before = (await client.get(base)).json()
    exact_before = (await client.get(base + "/" + reports[0])).json()
    assert [r["id"] for r in before["items"]] == list(reversed(reports))
    denied = await client.request("DELETE", base + "/" + reports[0])
    assert denied.status_code == 200, denied.text
    assert not denied.json()["deleted"] and denied.json()["used_by"]
    # Rejected removal cannot hide an older report or change its exact readable body.
    assert (await client.get(base)).json() == before
    assert (await client.get(base + "/" + reports[0])).json() == exact_before
    repeated = await client.request("DELETE", base + "/" + reports[0])
    assert repeated.json() == denied.json()
    assert (await client.get(base)).json() == before
    removed = await client.request("DELETE", base + "/" + reports[1])
    assert removed.status_code == 200, removed.text
    assert removed.json()["deleted"], removed.text
    assert (await client.request("DELETE", base + "/" + reports[1])).json()["deleted"]
    assert [r["id"] for r in (await client.get(base)).json()["items"]] == reports[:1]
    assert (await client.get(base + "/" + reports[0])).json() == exact_before
    # History remains readable; removal affects normal candidates and reuse, not frozen bodies.
    assert (await client.get(base + "/" + reports[1])).status_code == 200


async def test_research_reference_transaction_serializes_with_delete(client, prep_input, sessions):
    import asyncio
    from uuid import UUID

    from career_agent.application.services import require
    from career_agent.infrastructure import entities as e
    from career_agent.product.entities import ProductOperation

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
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    report = done["research_report_id"]
    async with sessions.begin() as session:
        await require(session, e.CompanyResearch, UUID(report))
        session.add(
            ProductOperation(
                request_id=uuid4(),
                run_id=uuid4(),
                kind="prepare_interview",
                payload={
                    "kind": "prepare_interview",
                    "request_id": str(uuid4()),
                    "request": {**prep_input, "research_report_id": report},
                },
            )
        )
        await session.flush()
        deletion = asyncio.create_task(
            client.request("DELETE", f"/api/v1/companies/{job['company_id']}/research/{report}")
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(deletion), 0.1)
    response = await asyncio.wait_for(deletion, 5)
    assert response.status_code == 200, response.text
    assert not response.json()["deleted"]
    assert any(value.startswith("生成任务（") for value in response.json()["used_by"])


@pytest.mark.parametrize("referenced", [False, True])
async def test_sole_expired_research_stays_readable_then_removal_respects_consumer(
    client, prep_input, sessions, referenced
):
    from datetime import timedelta
    from uuid import UUID

    from sqlalchemy import func, select

    from career_agent.infrastructure import entities as e

    job = (await client.get("/api/v1/jobs")).json()[0]
    path = f"/api/v1/companies/{job['company_id']}/research"
    assert (await client.get(path)).json()["items"] == []
    op = (
        await client.post(
            path,
            json={
                "kind": "company_research",
                "request_id": str(uuid4()),
                "request": {"job_revision_id": job["job_revision_id"], "mode": "fixture"},
            },
        )
    ).json()
    done = (await client.post(f"/api/v1/operations/{op['id']}/execute")).json()
    assert done["status"] == "success"
    report_id = done["research_report_id"]
    if referenced:
        prepared = await run(
            client, {**prep_input, "research_report_id": report_id}, "prepare_interview"
        )
        assert prepared["state"]["status"] == "completed"
    async with sessions.begin() as session:
        report = await session.get(e.CompanyResearch, UUID(report_id))
        report.expires_at = e.utcnow() - timedelta(days=1)
        calls = await session.scalar(select(func.count()).select_from(e.ModelCall))
    assert (await client.get(path + "/current?mode=fixture")).status_code == 404
    before = (await client.get(path)).json()
    assert [r["id"] for r in before["items"]] == [report_id]
    exact = (await client.get(path + "/" + report_id)).json()
    removed = (await client.delete(path + "/" + report_id)).json()
    assert removed["deleted"] is not referenced
    if referenced:
        assert removed["used_by"]
        assert (await client.get(path)).json() == before
    else:
        assert (await client.get(path)).json()["items"] == []
        assert (await client.get(path + "/current?mode=fixture")).status_code == 404
    assert (await client.get(path + "/" + report_id)).json() == exact
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(e.ModelCall)) == calls
