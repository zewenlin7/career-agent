from uuid import UUID

import pytest
from sqlalchemy import select
from test_preparation import prep_input as prep_fixture

from career_agent.infrastructure import entities as e
from career_agent.product.entities import ApplicationBinding

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def make_job(client):
    return (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "合成企业",
                "title": "工程师",
                "jd_text": "Python 开发",
                "requirements": [{"text": "Python", "source_quote": "Python"}],
            },
        )
    ).json()


async def test_jd_update_atomic_binding_noop_conflict_and_history(client, sessions):
    job = await make_job(client)
    other = await make_job(client)
    path = f"/api/v1/applications/{job['application_id']}"
    old_binding = (await client.get(path + "/context")).json()
    body = {
        "expected_revision": 1,
        "expected_binding_revision": old_binding["revision"],
        "jd_text": "Python 服务与 SQL",
    }
    updated = await client.put(path + "/jd", json=body)
    assert updated.status_code == 200, updated.text
    new = updated.json()
    assert new["revision"] == 2 and new["requirements"] == []
    binding = (await client.get(path + "/context")).json()
    assert binding["job_revision_id"] == new["job_revision_id"]
    assert (await client.get(f"/api/v1/applications/{other['application_id']}/context")).json()[
        "job_revision_id"
    ] == other["job_revision_id"]
    assert (await client.get(f"/api/v1/job-revisions/{job['job_revision_id']}")).json()[
        "jd_text"
    ] == "Python 开发"
    assert (await client.put(path + "/jd", json=body)).status_code == 409
    body.update(expected_revision=2, expected_binding_revision=binding["revision"])
    assert (await client.put(path + "/jd", json=body)).json()["job_revision_id"] == new[
        "job_revision_id"
    ]
    assert (await client.get(path + "/context")).json() == binding
    async with sessions() as session:
        assert (
            len(
                list(
                    await session.scalars(
                        select(e.JobRevision).where(e.JobRevision.job_id == UUID(job["id"]))
                    )
                )
            )
            == 2
        )
        old = list(
            await session.scalars(
                select(e.JobRequirement).where(
                    e.JobRequirement.job_revision_id == UUID(job["job_revision_id"])
                )
            )
        )
        assert len(old) == 1


async def test_closed_delete_hides_workspace_and_rejects_writes_preserves_sources(client, sessions):
    job = await make_job(client)
    other = await make_job(client)
    path = f"/api/v1/applications/{job['application_id']}"
    assert (await client.delete(path)).status_code == 409
    closed = await client.patch(
        path,
        json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束申请"},
    )
    assert closed.status_code == 200
    assert (await client.delete(path)).status_code == 200
    assert (await client.get(path)).status_code == 404
    assert (await client.get(path + "/context")).status_code == 404
    assert (await client.post(path + "/notes", json={"text": "不允许新增"})).status_code == 404
    assert (
        await client.patch(
            path,
            json={
                "expected_revision": 2,
                "status": "tracking",
                "correction": True,
                "reason": "恢复",
            },
        )
    ).status_code == 404
    listing = (await client.get("/api/v1/applications")).json()["items"]
    assert [r["id"] for r in listing] == [other["application_id"]]
    assert (await client.get(f"/api/v1/job-revisions/{job['job_revision_id']}")).status_code == 200
    async with sessions() as session:
        app = await session.get(e.Application, UUID(job["application_id"]))
        assert app is not None and app.deleted_at is not None
        assert await session.get(e.Company, UUID(job["company_id"]))
        assert await session.get(ApplicationBinding, app.id)


async def test_jd_rollback_does_not_publish_partial_revision(client, sessions, monkeypatch):
    from career_agent.application import services
    from career_agent.domain.schemas import ApplicationJDWrite

    job = await make_job(client)
    original = services.add_job_revision

    async def fail_after_insert(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("synthetic rollback")

    monkeypatch.setattr(services, "add_job_revision", fail_after_insert)
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        async with sessions.begin() as session:
            await services.edit_application_jd(
                session,
                UUID(job["application_id"]),
                ApplicationJDWrite(
                    expected_revision=1, expected_binding_revision=1, jd_text="新的 JD"
                ),
            )
    current = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    binding = (await client.get(f"/api/v1/applications/{job['application_id']}/context")).json()
    assert current == job
    assert binding["job_revision_id"] == job["job_revision_id"] and binding["revision"] == 1


async def test_deleted_application_blocks_pending_operation_before_budget(
    client, sessions, prep_input
):
    from uuid import uuid4

    from career_agent.product.entities import ProductOperation

    job = (await client.get("/api/v1/jobs")).json()[0]
    payload = {
        "request_id": str(uuid4()),
        "kind": "prepare_application",
        "request": {**prep_input, "targets": ["fit_analysis"]},
    }
    created = await client.post("/api/v1/operations", json=payload)
    assert created.status_code == 201
    op = created.json()
    path = f"/api/v1/applications/{job['application_id']}"
    await client.patch(
        path,
        json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束申请"},
    )
    await client.delete(path)
    assert (await client.post(f"/api/v1/operations/{op['id']}/execute")).status_code == 409
    payload["request_id"] = str(uuid4())
    assert (await client.post("/api/v1/operations", json=payload)).status_code == 409
    async with sessions() as session:
        assert not list(await session.scalars(select(e.ModelCall)))
        assert (await session.get(ProductOperation, UUID(op["id"]))).status == "pending"


async def test_application_deletion_migration_history(migrated_url, sessions, client):
    import asyncio

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    job = await make_job(client)
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "b905c1202601")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with sessions() as session:
        app = await session.get(e.Application, UUID(job["application_id"]))
        assert app is not None and app.deleted_at is None
        assert await session.scalar(text("select count(*) from application_events")) == 1
    await asyncio.to_thread(command.check, cfg)


async def test_delete_rechecks_status_after_concurrent_writer(client, sessions):
    import asyncio

    job = await make_job(client)
    path = f"/api/v1/applications/{job['application_id']}"
    await client.patch(
        path,
        json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束"},
    )
    async with sessions() as session:
        row = await session.scalar(
            select(e.Application)
            .where(e.Application.id == UUID(job["application_id"]))
            .with_for_update()
        )
        row.status = e.ApplicationStatus.TRACKING
        row.revision += 1
        await session.flush()
        waiting = asyncio.create_task(client.delete(path))
        await asyncio.sleep(0.05)
        assert not waiting.done()
        await session.commit()
        assert (await waiting).status_code == 409
    assert (await client.get(path)).json()["status"] == "tracking"


async def test_new_jd_extracts_new_requirements_old_fit_survives_deletion(
    client, sessions, prep_input
):
    from uuid import uuid4

    job = (await client.get("/api/v1/jobs")).json()[0]

    async def execute(jd_id):
        created = (
            await client.post(
                "/api/v1/operations",
                json={
                    "request_id": str(uuid4()),
                    "kind": "prepare_application",
                    "request": {
                        **prep_input,
                        "job_revision_id": jd_id,
                        "targets": ["fit_analysis"],
                    },
                },
            )
        ).json()
        done = await client.post(f"/api/v1/operations/{created['id']}/execute")
        assert done.status_code == 200 and done.json()["status"] == "success", done.text
        return created["id"]

    original = await execute(job["job_revision_id"])
    old_result = (await client.get(f"/api/v1/operations/{original}/result")).json()
    path = f"/api/v1/applications/{job['application_id']}"
    binding = (await client.get(path + "/context")).json()
    changed = (
        await client.put(
            path + "/jd",
            json={
                "expected_revision": job["revision"],
                "expected_binding_revision": binding["revision"],
                "jd_text": "使用 Python 开发服务。",
            },
        )
    ).json()
    assert changed["requirements"] == []
    await execute(changed["job_revision_id"])
    async with sessions() as session:
        requirements = list(
            await session.scalars(
                select(e.JobRequirement).where(
                    e.JobRequirement.job_revision_id == UUID(changed["job_revision_id"])
                )
            )
        )
        assert requirements and all(r.extraction_metadata for r in requirements)
    assert (await client.get(f"/api/v1/operations/{original}/result")).json() == old_result
    await client.patch(
        path,
        json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束"},
    )
    await client.delete(path)
    assert (await client.get(f"/api/v1/operations/{original}/result")).json() == old_result
    # Execution facts remain successful while the current workspace is unavailable.
    status = (await client.get(f"/api/v1/task-status/operations/{original}")).json()
    assert status["state"] == "success" and status["selection"].get("result")
    assert status["workspace"] == {
        "application_id": job["application_id"],
        "available": False,
        "reason": "application_deleted",
    }
    assert (await client.get(path + "/summary")).status_code == 404
