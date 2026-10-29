from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from career_agent.infrastructure import entities as e
from career_agent.product.entities import ProductDraft


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "facts"),
        ("POST", "facts"),
        ("POST", "facts/{id}/verify"),
        ("POST", "facts/{id}/reject"),
        ("POST", "facts/{id}/supersede"),
        ("GET", "fact-library"),
        ("POST", "fact-library/actions"),
        ("PATCH", "fact-library/{id}"),
        ("POST", "resume-workspaces/{id}/review"),
        ("POST", "resume-workspaces/{id}/publish"),
    ],
)
async def test_retired_fact_routes_absent(client, method, path):
    response = await client.request(method, "/api/v1/" + path.format(id=uuid4()), json={})
    assert response.status_code in {404, 405}


@pytest.mark.parametrize("status", ["pending", "running", "recovery_required", "completed"])
async def test_retired_draft_readable_but_never_executed_or_adopted(client, sessions, status):
    from test_profile_records import named_source

    profile = await named_source(client)
    response = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "base_resume_drafting",
            "profile_id": profile["profile_id"],
            "mode": "fixture",
        },
    )
    assert response.status_code == 201, response.text
    id = response.json()["id"]
    async with sessions.begin() as session:
        row = await session.get(ProductDraft, UUID(id))
        row.task = "profile_fact_extraction"
        row.request = {**row.request, "task": row.task}
        row.status = status
        row.output = {
            "facts": [
                {
                    "section": "projects",
                    "entry_index": 0,
                    "statement": "合成经历",
                    "source_quote": "合成经历",
                }
            ]
        }
        if status == "completed":
            step = e.AgentStep(run_id=row.run_id, sequence=1, node="product_draft")
            session.add(step)
            await session.flush()
            call = e.ModelCall(
                step_id=step.id,
                task_type=row.task,
                provider="fixture",
                model="historical",
                status=e.CallStatus.SUCCEEDED,
            )
            session.add(call)
            await session.flush()
            row.accepted_model_call_id = call.id
            row.adopted = {"fact_ids": [], "profile_id": profile["profile_id"]}
        frozen_view = {
            "output": row.output,
            "adopted": row.adopted,
            "accepted_model_call_id": str(row.accepted_model_call_id)
            if row.accepted_model_call_id
            else None,
        }
        before_usage = dict(row.usage)
        before_calls = await session.scalar(select(func.count()).select_from(e.ModelCall))
    read = await client.get(f"/api/v1/product-drafts/{id}")
    assert read.status_code == 200
    for key, value in frozen_view.items():
        assert read.json()[key] == value
    for action in ["execute", "adopt"]:
        result = await client.post(f"/api/v1/product-drafts/{id}/{action}", json={})
        assert result.status_code == 410, result.text
        assert "task_retired" in result.text
    async with sessions() as session:
        row = await session.get(ProductDraft, UUID(id))
        assert row.usage == before_usage
        assert row.status in {status, "recovery_required"}
        assert await session.scalar(select(func.count()).select_from(e.ModelCall)) == before_calls
    denied = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "profile_fact_extraction",
            "profile_id": profile["profile_id"],
        },
    )
    assert denied.status_code == 422


async def test_retired_task_direct_service_is_fenced_before_calls(client, sessions):
    from test_profile_records import named_source

    from career_agent.domain.rules import DomainError
    from career_agent.models.prompts import application_prompts
    from career_agent.preparation.providers import dependencies
    from career_agent.product.draft_contracts import DraftAdopt, DraftCreate
    from career_agent.product.drafts import DraftService

    profile = await named_source(client)
    response = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "base_resume_drafting",
            "profile_id": profile["profile_id"],
        },
    )
    id = UUID(response.json()["id"])
    async with sessions.begin() as session:
        row = await session.get(ProductDraft, id)
        row.task = "profile_fact_extraction"
        row.request = {**row.request, "task": row.task}
        row.status = "recovery_required"
        run = await session.get(e.AgentRun, row.run_id)
        run_usage = dict(run.consumed_usage)
        legacy = dict(row.request)
    settings = client._transport.app.state.settings
    async with dependencies(settings, "fixture", require_research=False) as (gateway, _):
        service = DraftService(sessions, settings, gateway)
        for operation in [
            service.execute(id),
            service.adopt(id, DraftAdopt()),
            service.create(DraftCreate.model_construct(**legacy)),
        ]:
            with pytest.raises(DomainError, match="task_retired"):
                await operation
    async with sessions() as session:
        row = await session.get(ProductDraft, id)
        assert row.status == "recovery_required"
        run = await session.get(e.AgentRun, row.run_id)
        assert run.consumed_usage == run_usage
        assert await session.scalar(select(func.count()).select_from(e.ModelCall)) == 0
    assert "profile_fact_extraction" not in application_prompts().specs


async def test_historical_evidence_lineage_remains_readable(sessions):
    from career_agent.domain.rules import FactStatus

    async with sessions.begin() as session:
        original = e.PersonalFact(
            statement="原始合成经历", category="project", status=FactStatus.SUPERSEDED
        )
        session.add(original)
        await session.flush()
        replacement = e.PersonalFact(
            statement="修订合成经历",
            category="project",
            lineage_id=original.lineage_id,
            revision=2,
            replaces_id=original.id,
        )
        session.add(replacement)
        await session.flush()
        original_id, replacement_id = original.id, replacement.id
    async with sessions() as session:
        original = await session.get(e.PersonalFact, original_id)
        replacement = await session.get(e.PersonalFact, replacement_id)
        assert replacement.replaces_id == original.id
        assert replacement.lineage_id == original.lineage_id
        assert original.statement == "原始合成经历"
        assert original.status == FactStatus.SUPERSEDED
