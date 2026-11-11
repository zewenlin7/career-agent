"""Summary lifecycle uses real application transactions and historical references."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import prep_input as prep_fixture
from test_preparation import run

from career_agent.infrastructure import entities as e

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def job(client):
    r = await client.post(
        "/api/v1/jobs",
        json={"company_name": "摘要公司", "title": "工程师", "jd_text": "完整职位描述"},
    )
    assert r.status_code == 201
    return r.json()


async def test_summary_status_aliases_and_noop(client, sessions):
    j = await job(client)
    path = f"/api/v1/applications/{j['application_id']}"
    revision = 1
    for status in ["offer", "rejected", "interviewing", "closed", "tracking", "applied"]:
        r = await client.patch(path, json={"expected_revision": revision, "status": status})
        assert r.status_code == 200, r.text
        revision += 1
        assert r.json()["revision"] == revision
        again = await client.patch(path, json={"expected_revision": revision, "status": status})
        assert again.json()["revision"] == revision
    async with sessions.begin() as s:
        app = await s.get(e.Application, UUID(j["application_id"]))
        app.status = e.ApplicationStatus.WITHDRAWN
    assert (await client.get(path)).json()["status"] == "closed"
    assert (await client.get("/api/v1/applications?status=closed")).json()["items"][0]["id"] == j[
        "application_id"
    ]
    assert (await client.delete(path)).status_code == 200


async def test_user_note_edit_delete_preserves_event_and_cas(client, sessions):
    j = await job(client)
    path = f"/api/v1/applications/{j['application_id']}"
    request = {"text": "第一条", "request_id": str(uuid4()), "expected_revision": 1}
    r = await client.post(path + "/notes", json=request)
    assert r.status_code == 201, r.text
    assert (await client.post(path + "/notes", json=request)).json()["id"] == r.json()["id"]
    summary = (await client.get(path + "/summary")).json()
    assert len(summary["notes"]) == 1 and len(summary["records"]) == 1
    note = summary["notes"][0]
    update = {
        "request_id": str(uuid4()),
        "expected_revision": summary["revision"],
        "expected_entry_revision": note["revision"],
        "text": "修改笔记",
    }
    assert (await client.patch(path + "/entries/" + note["id"], json=update)).status_code == 200
    assert (
        await client.patch(
            path + "/entries/" + note["id"], json={**update, "request_id": str(uuid4())}
        )
    ).status_code == 409
    changed = (await client.get(path + "/summary")).json()
    assert changed["notes"][0]["text"] == "修改笔记"
    assert changed["notes"][0]["created_at"] == note["created_at"]
    noop = await client.patch(
        path + "/entries/" + note["id"],
        json={
            **update,
            "request_id": str(uuid4()),
            "expected_revision": changed["revision"],
            "expected_entry_revision": 2,
        },
    )
    assert noop.json()["revision"] == changed["revision"]
    assert (await client.get(path + "/summary")).json()["notes"] == changed["notes"]

    delete = {
        **update,
        "request_id": str(uuid4()),
        "expected_revision": changed["revision"],
        "expected_entry_revision": 2,
    }
    assert (
        await client.request("DELETE", path + "/entries/" + note["id"], json=delete)
    ).status_code == 200
    assert (await client.get(path + "/summary")).json()["notes"] == []
    async with sessions() as s:
        original = await s.get(e.ApplicationEvent, UUID(note["id"]))
        assert original.note == "第一条"


async def test_unknown_legacy_note_not_editable_and_state_record_removal_does_not_undo(
    client, sessions
):
    j = await job(client)
    path = f"/api/v1/applications/{j['application_id']}"
    async with sessions.begin() as s:
        row = e.ApplicationEvent(
            application_id=UUID(j["application_id"]), sequence=2, kind="note", note="来源未知"
        )
        s.add(row)
        app = await s.get(e.Application, UUID(j["application_id"]))
        app.revision = 2
        await s.flush()
        unknown_id = str(row.id)
    mutation = {
        "request_id": str(uuid4()),
        "expected_revision": 2,
        "expected_entry_revision": 1,
        "text": "更改",
    }
    assert (await client.patch(path + "/entries/" + unknown_id, json=mutation)).status_code == 409
    r = await client.patch(
        path, json={"expected_revision": 2, "status": "offer", "reason": "收到录用"}
    )
    assert r.status_code == 200
    summary = (await client.get(path + "/summary")).json()
    assert summary["notes"] == []
    record = next(x for x in summary["records"] if x["kind"] == "status")
    cleared = await client.patch(
        path + "/entries/" + record["id"], json={**mutation, "expected_revision": 3, "text": ""}
    )
    assert cleared.status_code == 200
    assert (await client.get(path + "/summary")).json()["records"][0]["text"] is None
    assert (await client.get(path)).json()["events"][-1]["note"] == "收到录用"

    assert (
        await client.request(
            "DELETE",
            path + "/entries/" + record["id"],
            json={
                **mutation,
                "request_id": str(uuid4()),
                "expected_revision": 4,
                "expected_entry_revision": 2,
            },
        )
    ).status_code == 200
    assert (await client.get(path)).json()["status"] == "offer"


async def test_summary_notes_all_entries_system_protection_and_migration(
    client, sessions, migrated_url
):
    import asyncio

    from alembic import command
    from alembic.config import Config

    j = await job(client)
    path = f"/api/v1/applications/{j['application_id']}"
    for n in range(8):
        assert (await client.post(path + "/notes", json={"text": f"笔记 {n}"})).status_code == 201
    summary = (await client.get(path + "/summary")).json()
    assert len(summary["notes"]) == 8
    assert len(summary["records"]) == 1
    assert len(summary["preparation"]) == 5
    assert all(not item["available"] for item in summary["preparation"])
    created = summary["records"][0]
    assert (
        await client.request(
            "DELETE",
            path + "/entries/" + created["id"],
            json={
                "request_id": str(uuid4()),
                "expected_revision": summary["revision"],
                "expected_entry_revision": 1,
            },
        )
    ).status_code == 409
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.check, cfg)
    # No edits exist: downgrade and re-upgrade preserve old events, without inventing ownership.
    await asyncio.to_thread(command.downgrade, cfg, "ba05c1302601")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert len((await client.get(path)).json()["events"]) == 9
    assert (await client.get(path + "/summary")).json()["notes"] == []


async def test_submission_never_regresses_status_and_snapshot_survives(
    client, sessions, prep_input
):
    package = await run(client, prep_input)
    view = (
        await client.get(f"/api/v1/preparation-artifacts/{package['package_id']}/product-view")
    ).json()
    resume = next(r for r in view["results"] if r["kind"] == "resume_tailoring")
    j = (await client.get("/api/v1/jobs")).json()[0]
    path = f"/api/v1/applications/{j['application_id']}"
    for status in ["tracking", "applied", "interviewing", "offer", "rejected", "closed"]:
        app = (await client.get(path)).json()
        response = await client.patch(
            path, json={"expected_revision": app["revision"], "status": status}
        )
        app = response.json()
        payload = {
            "request_id": str(uuid4()),
            "expected_revision": app["revision"],
            "resume_revision_id": resume["resume_revision_id"],
            "render_artifact_id": package["state"]["render_report_id"],
        }
        saved = await client.post(path + "/submissions", json=payload)
        assert saved.status_code == 201, saved.text
        assert (await client.post(path + "/submissions", json=payload)).json() == saved.json()
        current = (await client.get(path)).json()
        assert current["status"] == ("applied" if status == "tracking" else status)
        summary = (await client.get(path + "/summary")).json()
        assert summary["notes"] == []
        # Submission-owned events are not editable as user notes or state comments.
        denied = await client.patch(
            path + "/entries/" + saved.json()["event_id"],
            json={
                "request_id": str(uuid4()),
                "expected_revision": current["revision"],
                "expected_entry_revision": 1,
                "text": "不允许",
            },
        )
        assert denied.status_code == 409
        link = summary["submission"]["resume"]["href"]
        assert resume["resume_revision_id"] in link and package["state"]["render_report_id"] in link
    exact = await client.get(
        f"/api/v1/resume-revisions/{resume['resume_revision_id']}/snapshot?pdf={package['state']['render_report_id']}"
    )
    assert exact.status_code == 200 and exact.json()["document"] == resume["content"]
    download = await client.get(
        f"/api/v1/artifacts/{package['state']['render_report_id']}/download"
    )
    assert download.status_code == 200 and download.content.startswith(b"%PDF")


async def test_summary_latest_success_exact_result_and_expired_research(
    client, sessions, prep_input
):
    from datetime import timedelta

    await run(client, prep_input)
    j = (await client.get("/api/v1/jobs")).json()[0]
    path = f"/api/v1/applications/{j['application_id']}"
    operation = await client.post(
        f"/api/v1/companies/{j['company_id']}/research",
        json={
            "request_id": str(uuid4()),
            "kind": "company_research",
            "request": {**prep_input, "mode": "fixture"},
        },
    )
    assert operation.status_code == 201, operation.text
    done = await client.post(f"/api/v1/operations/{operation.json()['id']}/execute")
    assert done.json()["status"] == "success", done.text
    first = (await client.get(path + "/summary")).json()
    fit = next(x for x in first["preparation"] if x["kind"] == "fit_analysis")
    assert fit["available"] and not fit["stale"]
    async with sessions.begin() as s:
        research = await s.scalar(select(e.CompanyResearch))
        assert research is not None
        research.expires_at = e.utcnow() - timedelta(days=2)
    binding = (await client.get(path + "/context")).json()
    assert (
        await client.put(
            path + "/jd",
            json={
                "expected_revision": j["revision"],
                "expected_binding_revision": binding["revision"],
                "jd_text": "修改后的完整职位描述",
            },
        )
    ).status_code == 200
    second = (await client.get(path + "/summary")).json()
    assert next(x for x in second["preparation"] if x["kind"] == "company_research")["available"]
    updated_fit = next(x for x in second["preparation"] if x["kind"] == "fit_analysis")
    assert updated_fit["href"] == fit["href"] and updated_fit["stale"]
    target = fit["href"].split("result=")[1]
    exact = await client.get(
        f"/api/v1/preparation-artifacts/{target}/result?application_id={j['application_id']}"
    )
    assert (
        exact.status_code == 200
        and exact.json()["result"]["context"]["job_revision_id"] == prep_input["job_revision_id"]
    )


async def test_summary_actual_totals_and_debrief_generation_selection(client):
    from test_interview_loop import actual_session, append

    row, j = await actual_session(client)
    row = await append(client, row, 1)
    path = f"/api/v1/applications/{j['application_id']}/summary"
    for n in range(3):
        await client.post(
            "/api/v1/interviews",
            json={
                "application_id": j["application_id"],
                "round_name": f"草稿 {n}",
                "status": "draft",
            },
        )
    first = (await client.get(path)).json()
    assert first["actual"]["count"] == 1
    assert row["id"] in first["actual"]["latest"]["href"]
    payload = {
        "source_kind": "actual",
        "interview_id": row["id"],
        "expected_source_revision": row["content_revision"],
        "question_analysis": "all",
        "overall_analysis": True,
    }
    root = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    assert (
        "run_completed"
        in (await client.post(f"/api/v1/interview-debriefs/{root['id']}/execute")).text
    )
    summary = (await client.get(path)).json()
    assert summary["debrief"]["count"] == 1
    assert root["id"] in summary["debrief"]["latest"]["href"]
    assert summary["debrief"]["latest"]["created_at"]
    regenerated = (
        await client.post(
            f"/api/v1/interview-debriefs/{root['id']}/regenerate",
            json={"question_analysis": "all", "overall_analysis": True},
        )
    ).json()
    # A pending generation does not replace the previously readable result.
    assert (await client.get(path)).json()["debrief"] == summary["debrief"]
    assert (
        "run_completed"
        in (await client.post(f"/api/v1/interview-debriefs/{regenerated['id']}/execute")).text
    )
    latest = (await client.get(path)).json()["debrief"]
    assert latest["count"] == 1 and regenerated["id"] in latest["latest"]["href"]
    historical = await client.get(f"/api/v1/interview-debriefs/{root['id']}?historical=true")
    assert historical.json()["id"] == root["id"]


async def test_summary_mock_ordinal_and_read_has_no_execution(client, sessions, prep_input):
    from sqlalchemy import func

    j = (await client.get("/api/v1/jobs")).json()[0]
    binding = await client.put(
        f"/api/v1/applications/{j['application_id']}/context",
        json={"expected_revision": 1, **prep_input},
    )
    assert binding.status_code == 200, binding.text
    creation = {
        "context": prep_input,
        "application_binding": {
            "application_id": j["application_id"],
            "revision": binding.json()["revision"],
        },
    }
    mocks = []
    for _ in range(2):
        response = await client.post("/api/v1/mock-interviews", json=creation)
        assert response.status_code == 201, response.text
        mocks.append(response.json())
    async with sessions() as session:
        before = await session.scalar(select(func.count()).select_from(e.ModelCall))
    path = f"/api/v1/applications/{j['application_id']}/summary"
    summary = (await client.get(path)).json()
    assert summary["mock"]["label"] == "第 2 次模拟面试"
    assert mocks[1]["id"] in summary["mock"]["href"]
    assert summary["mock"]["status"] == "ready_to_generate"
    assert (await client.get(f"/api/v1/mock-interviews/{mocks[1]['id']}")).json()["turns"] == []
    assert (await client.get(path)).json()["mock"] == summary["mock"]
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(e.ModelCall)) == before

    ended = await client.post(
        f"/api/v1/mock-interviews/{mocks[1]['id']}/end",
        json={"request_id": str(uuid4()), "expected_revision": mocks[1]["revision"]},
    )
    assert ended.status_code == 200
    record = (await client.get(path)).json()["mock"]
    assert record["completion_type"] == "user_ended_early"
    assert "/interview/history?session=" in record["href"]
    binding = (await client.get(path.removesuffix("summary") + "context")).json()
    updated = await client.put(
        path.removesuffix("summary") + "jd",
        json={
            "expected_revision": j["revision"],
            "expected_binding_revision": binding["revision"],
            "jd_text": "新职位描述",
        },
    )
    assert updated.status_code == 200
    assert (await client.get(path)).json()["mock"]["stale"]
