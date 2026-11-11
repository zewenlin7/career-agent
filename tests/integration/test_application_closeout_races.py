"""Real execution and adoption boundaries ordered against logical Application deletion."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import inject
from test_preparation import prep_input as prep_fixture

from career_agent.infrastructure import entities as e
from career_agent.preparation.providers import FixtureTaskProvider
from career_agent.product.drafts import DraftService

prep_input = prep_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("case", ["operation", "delete_before_adopt", "adopt_before_delete"])
async def test_dispatched_output_and_adoption_delete_order(
    client, sessions, prep_input, monkeypatch, case
):
    job = (await client.get("/api/v1/jobs")).json()[0]
    application = f"/api/v1/applications/{job['application_id']}"
    source = None
    if case != "operation":
        generated = (
            await client.post(
                "/api/v1/workflows/prepare_application",
                json={**prep_input, "targets": ["greeting_generation"]},
            )
        ).json()
        source = generated["outcome"]["targets"]["greeting_generation"]["artifact_id"]
    assert (
        await client.patch(
            application,
            json={"expected_revision": 1, "status": "closed", "correction": True, "reason": "结束"},
        )
    ).status_code == 200
    entered, release = asyncio.Event(), asyncio.Event()
    output_ready = False

    class Delayed(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            nonlocal output_ready
            result = await super().generate(candidate, context, task)
            if case == "adopt_before_delete":
                output_ready = True
            else:
                entered.set()
                await release.wait()
            return result

    inject(client, provider=Delayed())
    if case == "adopt_before_delete":
        original = DraftService.context

        async def delayed_context(self, session, request):
            result = await original(self, session, request)
            if output_ready:
                entered.set()
                await release.wait()
            return result

        monkeypatch.setattr(DraftService, "context", delayed_context)
    if case == "operation":
        family = "operations"
        payload = {
            "request_id": str(uuid4()),
            "kind": "prepare_application",
            "request": {**prep_input, "targets": ["fit_analysis"]},
        }
    else:
        family = "product-drafts"
        payload = {
            "request_id": str(uuid4()),
            "task": "greeting_refinement",
            "source_artifact_id": source,
            "application_id": job["application_id"],
            "intent": "regenerate",
            "feedback": "保留事实调整表达",
        }
    made = await client.post(f"/api/v1/{family}", json=payload)
    assert made.status_code == 201, made.text
    id = made.json()["id"]
    execution = asyncio.create_task(client.post(f"/api/v1/{family}/{id}/execute"))
    await asyncio.wait_for(entered.wait(), 5)
    deletion = asyncio.create_task(client.delete(application))
    try:
        if case == "delete_before_adopt":
            assert (await asyncio.wait_for(deletion, 3)).status_code == 200
        else:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(deletion), 0.1)
    finally:
        release.set()
    result = await asyncio.wait_for(execution, 10)
    assert result.status_code == 200, result.text
    assert (await asyncio.wait_for(deletion, 3)).status_code == 200
    assert result.json()["status"] in {"success", "completed"}
    status = (await client.get(f"/api/v1/task-status/{family}/{id}")).json()
    assert status["workspace"]["available"] is False
    if case != "operation":
        assert result.json()["accepted_model_call_id"]
        assert bool(result.json()["adopted"]) is (case == "adopt_before_delete")
        if case == "delete_before_adopt":
            assert (await client.post(f"/api/v1/{family}/{id}/adopt", json={})).status_code == 409
    async with sessions() as session:
        assert (await session.get(e.Application, UUID(job["application_id"]))).deleted_at
        assert list(await session.scalars(select(e.ModelCall)))
