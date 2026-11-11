"""Application closeout request identity and active-owner lifecycle regressions."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from test_preparation import prep_input as prep_fixture

from career_agent.application import services
from career_agent.domain.schemas import JobCreate
from career_agent.infrastructure import entities as e
from career_agent.product.entities import ApplicationBinding

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_job_request_concurrency_replay_conflict_and_independent_intent(client, sessions):
    payload = {
        "company_name": "请求诊断公司",
        "title": "工程师",
        "jd_text": "Python",
        "request_id": str(uuid4()),
    }
    first, second = await asyncio.gather(
        client.post("/api/v1/jobs", json=payload), client.post("/api/v1/jobs", json=payload)
    )
    assert first.status_code == second.status_code == 201
    a, b = first.json(), second.json()
    assert a["company_id"] == b["company_id"]
    # Replays share one durable receipt; independent intent keeps its own business objects.
    assert a["id"] == b["id"] and a["application_id"] == b["application_id"]
    replay = (await client.post("/api/v1/jobs", json=payload)).json()
    assert replay["id"] == a["id"]
    assert (
        await client.post("/api/v1/jobs", json={**payload, "title": "different"})
    ).status_code == 409
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(e.Company)) == 1
        for model in [
            e.JobPosting,
            e.JobRevision,
            e.Application,
            ApplicationBinding,
            e.ApplicationEvent,
            e.JobCreateRequest,
        ]:
            assert await session.scalar(select(func.count()).select_from(model)) == 1

    independent = (
        await client.post("/api/v1/jobs", json={**payload, "request_id": str(uuid4())})
    ).json()
    assert independent["id"] != a["id"]
    receipt = (await client.get(f"/api/v1/job-create-requests/{payload['request_id']}")).json()
    assert receipt["application_id"] == a["application_id"] and receipt["workspace_available"]
    path = f"/api/v1/applications/{a['application_id']}"
    assert (
        await client.patch(
            path,
            json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束"},
        )
    ).status_code == 200
    assert (await client.delete(path)).status_code == 200
    replay = (await client.post("/api/v1/jobs", json=payload)).json()
    assert replay["id"] == a["id"] and replay["application_id"] is None
    after = (await client.get(f"/api/v1/job-create-requests/{payload['request_id']}")).json()
    assert after["application_id"] == receipt["application_id"] and not after["workspace_available"]


async def test_audit_job_creation_transaction_rolls_back_all_initial_objects(sessions):
    with pytest.raises(RuntimeError, match="synthetic transaction abort"):
        async with sessions.begin() as session:
            await services.create_job(
                session,
                JobCreate(
                    request_id=uuid4(),
                    company_name="回滚诊断公司",
                    title="工程师",
                    jd_text="Python",
                ),
            )
            raise RuntimeError("synthetic transaction abort")
    async with sessions() as session:
        for model in [
            e.Company,
            e.JobPosting,
            e.JobRevision,
            e.Application,
            ApplicationBinding,
            e.ApplicationEvent,
            e.JobCreateRequest,
        ]:
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("binding_kind", ["profile", "resume"])
async def test_deleted_binding_allows_archive_and_job_has_no_workspace_link(
    client, sessions, prep_input, binding_kind
):
    job = (await client.get("/api/v1/jobs")).json()[0]
    app = f"/api/v1/applications/{job['application_id']}"
    bound = await client.put(
        app + "/context",
        json={
            "expected_revision": 1,
            **prep_input,
            "resume_revision_id": prep_input["resume_revision_id"]
            if binding_kind == "resume"
            else None,
        },
    )
    assert bound.status_code == 200, bound.text
    assert (
        await client.patch(
            app,
            json={
                "expected_revision": 1,
                "status": "closed",
                "correction": True,
                "reason": "结束合成申请",
            },
        )
    ).status_code == 200
    assert (await client.delete(app)).status_code == 200
    assert (await client.delete(app)).status_code == 404
    assert (await client.get(app + "/summary")).status_code == 404
    assert (await client.get("/api/v1/applications")).json()["items"] == []
    job_after = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert job_after["application_id"] is None
    if binding_kind == "profile":
        profile = await client.delete(f"/api/v1/profile/revisions/{prep_input['profile_id']}")
        assert profile.status_code == 200
        return
    async with sessions() as session:
        resume = await session.get(e.ResumeVariantRevision, UUID(prep_input["resume_revision_id"]))
        revision = resume.metadata_revision
    resume = await client.request(
        "DELETE",
        f"/api/v1/resume-library/versions/{prep_input['resume_revision_id']}",
        json={"expected_revision": revision},
    )
    assert resume.status_code == 200


async def test_named_profile_archive_excludes_deleted_owners(client):
    from test_profile_records import named_source

    profile = await named_source(client)
    job = (
        await client.post(
            "/api/v1/jobs",
            json={"company_name": "命名资料诊断", "title": "工程师", "jd_text": "Python"},
        )
    ).json()
    path = f"/api/v1/applications/{job['application_id']}"
    assert (
        await client.put(
            path + "/context",
            json={
                "expected_revision": 1,
                "profile_id": profile["profile_id"],
                "job_revision_id": job["job_revision_id"],
            },
        )
    ).status_code == 200
    assert (
        await client.patch(
            path,
            json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束"},
        )
    ).status_code == 200
    assert (await client.delete(path)).status_code == 200
    response = await client.request(
        "DELETE",
        f"/api/v1/profile-library/{profile['id']}",
        json={"expected_revision": profile["revision"]},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("resource", ["named", "profile", "resume"])
async def test_archive_active_mixed_and_concurrent_binding(resource, client, sessions, prep_input):
    from test_profile_records import named_source

    from career_agent.product import bindings
    from career_agent.product.contracts import ApplicationBindingWrite
    from career_agent.profile_area import api, contracts, records, service

    named = await named_source(client) if resource == "named" else None
    profile = named["profile_id"] if named else prep_input["profile_id"]
    resume = None
    if resource == "resume":
        async with sessions() as session:
            original = await session.get(
                e.ResumeVariantRevision, UUID(prep_input["resume_revision_id"])
            )
            document = {**original.document, "job_revision_id": None}
        created = (await client.post("/api/v1/resume-variants", json=document)).json()
        resume = created["resume_revision_id"]
    jobs = [
        (
            await client.post(
                "/api/v1/jobs",
                json={"company_name": "并发归档", "title": str(n), "jd_text": "Python"},
            )
        ).json()
        for n in range(2)
    ]

    def payload(job):
        return ApplicationBindingWrite(
            expected_revision=1,
            profile_id=UUID(profile),
            resume_revision_id=UUID(resume) if resume else None,
            job_revision_id=UUID(job["job_revision_id"]),
        )

    async def archive(session):
        if resource == "named":
            return await records.delete(
                UUID(named["id"]), contracts.Publish(expected_revision=named["revision"]), session
            )
        if resource == "profile":
            return await service.archive_profile(session, UUID(profile))
        return await api.archive_resume(
            UUID(resume), contracts.Publish(expected_revision=1), session
        )

    async def archive_transaction():
        async with sessions.begin() as session:
            await archive(session)

    from career_agent.domain.rules import DomainError

    # An uncommitted new binding holds the resource lock. Archive observes it after commit.
    async with sessions.begin() as session:
        await bindings.update(session, UUID(jobs[0]["application_id"]), payload(jobs[0]))
        pending = asyncio.create_task(archive_transaction())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(pending), 0.1)
    with pytest.raises(DomainError, match="in_use"):
        await asyncio.wait_for(pending, 3)
    async with sessions.begin() as session:
        await bindings.update(session, UUID(jobs[1]["application_id"]), payload(jobs[1]))
    for index, job in enumerate(jobs):
        path = f"/api/v1/applications/{job['application_id']}"
        await client.patch(
            path,
            json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束"},
        )
        if index == 1:
            # Archive must not mistake an uncommitted deletion for an inactive owner.
            async with sessions.begin() as session:
                await services.delete_application(session, UUID(job["application_id"]))
                with pytest.raises(DomainError, match="in_use"):
                    await asyncio.wait_for(archive_transaction(), 3)
        else:
            await client.delete(path)
        if index == 0:
            with pytest.raises(DomainError, match="in_use"):
                await archive_transaction()
    # Archive wins before a new binding: the waiter must reject the archived resource.
    new_job = (
        await client.post(
            "/api/v1/jobs", json={"company_name": "并发归档", "title": "new", "jd_text": "Python"}
        )
    ).json()

    async def bind_transaction():
        async with sessions.begin() as session:
            await bindings.update(session, UUID(new_job["application_id"]), payload(new_job))

    async with sessions.begin() as session:
        await archive(session)
        pending = asyncio.create_task(bind_transaction())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(pending), 0.1)
    with pytest.raises(DomainError, match="archived"):
        await asyncio.wait_for(pending, 3)
    async with sessions() as session:
        for job in jobs:
            assert await session.get(ApplicationBinding, UUID(job["application_id"]))


async def test_job_request_migration_retains_legacy_and_refuses_receipt_loss(
    client, sessions, migrated_url
):
    from alembic import command
    from alembic.config import Config

    legacy = (
        await client.post(
            "/api/v1/jobs",
            json={"company_name": "迁移历史", "title": "工程师", "jd_text": "Python"},
        )
    ).json()
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "c205c2102601")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert (await client.get(f"/api/v1/jobs/{legacy['id']}")).json() == legacy
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(e.JobCreateRequest)) == 0
    request_id = str(uuid4())
    payload = {
        "company_name": "迁移历史",
        "title": "工程师",
        "jd_text": "Python",
        "request_id": request_id,
    }
    created = (await client.post("/api/v1/jobs", json=payload)).json()
    with pytest.raises(RuntimeError, match="job_create_request_history_requires_retention"):
        await asyncio.to_thread(command.downgrade, cfg, "c205c2102601")
    assert (await client.post("/api/v1/jobs", json=payload)).json() == created
    await asyncio.to_thread(command.check, cfg)
