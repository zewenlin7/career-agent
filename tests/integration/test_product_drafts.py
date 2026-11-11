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
@pytest.mark.parametrize("intent", ["refine", "regenerate"])
async def test_refinement_new_artifact_and_provenance(
    client, sessions, prep_input, target, task, workflow, intent
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
        intent=intent,
        feedback="简洁一些，突出事务测试。",
    )
    if task in {"resume_refinement", "greeting_refinement", "interview_preparation_refinement"}:
        assert proposal["adopted"]
    if task == "resume_refinement":
        assert proposal["adopted"], "Application optimization must save before execute returns"
        versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
        assert any(item["id"] == proposal["adopted"]["resume_revision_id"] for item in versions)
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

    if task == "resume_refinement":
        version_id = proposal["adopted"]["resume_revision_id"]
        before_versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
        version = next(item for item in before_versions if item["id"] == version_id)
        renamed = await client.patch(
            f"/api/v1/resume-library/versions/{version_id}",
            json={"expected_revision": version["metadata_revision"], "name": "针对当前岗位的简历"},
        )
        assert renamed.status_code == 200, renamed.text
        replay = await client.post(f"/api/v1/product-drafts/{proposal['id']}/adopt", json={})
        assert replay.json()["adopted"] == saved.json()["adopted"]
        after_versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
        assert len(after_versions) == len(before_versions)
        history = (
            await client.get(f"/api/v1/applications/{app['id']}/results?target={target}")
        ).json()["items"]
        own = next(
            item["result"] for item in history if item["result"]["resume_revision_id"] == version_id
        )
        assert own["resume_name"] == "针对当前岗位的简历"
        archived = await client.request(
            "DELETE",
            f"/api/v1/resume-library/versions/{version_id}",
            json={"expected_revision": renamed.json()["metadata_revision"]},
        )
        assert archived.status_code == 200, archived.text
        visible = (
            await client.get(f"/api/v1/applications/{app['id']}/results?target={target}&limit=1")
        ).json()
        assert len(visible["items"]) == 1 and not visible["has_more"]
        assert visible["items"][0]["result"]["resume_revision_id"] != version_id
        exact = await client.get(
            f"/api/v1/preparation-artifacts/{own['target_artifact_id']}/result?application_id={app['id']}"
        )
        assert exact.status_code == 200 and exact.json()["result"]["available"] is False


async def test_cancelled_draft_notification_is_persisted_without_model_call(
    client, sessions, prep_input
):
    from sqlalchemy import select

    from career_agent.infrastructure import entities as e

    created = (
        await client.post(
            "/api/v1/product-drafts",
            json={
                "request_id": str(uuid4()),
                "task": "base_resume_drafting",
                "profile_id": prep_input["profile_id"],
            },
        )
    ).json()
    response = await client.post(f"/api/v1/product-drafts/{created['id']}/cancel", json={})
    assert response.status_code == 200, response.text
    path = f"/api/v1/task-status/product-drafts/{created['id']}"
    first = (await client.get(path)).json()
    assert first["state"] == "cancelled"
    assert (await client.get(path)).json() == first
    async with sessions() as session:
        assert not list(await session.scalars(select(e.ModelCall)))


@pytest.mark.parametrize(
    "code",
    ["provider_429", "provider_timeout", "output_validation_failed", "grounding_failed"],
)
async def test_refinement_failure_reason_survives_persistence_and_status(
    client, sessions, prep_input, code
):
    from test_preparation import inject

    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.providers import FixtureTaskProvider

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    initial = (
        await client.post(
            "/api/v1/workflows/prepare_application",
            json={**prep_input, "targets": ["resume_tailoring"]},
        )
    ).json()
    source = initial["outcome"]["targets"]["resume_tailoring"]["artifact_id"]
    before = (await client.get("/api/v1/resume-library/versions")).json()["items"]

    class Fault(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if context.task_type != "resume_refinement":
                return response
            if code == "output_validation_failed":
                response.output = {"invalid_schema": True}
            elif code == "grounding_failed":
                response.output["sections"][0]["items"][0]["text"] = (
                    "管理 99999 名员工，收入增长 99999%。"
                )
            else:
                raise ModelGatewayError(code)
            return response

    inject(client, provider=Fault())
    created = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "resume_refinement",
            "source_artifact_id": source,
            "application_id": app["id"],
            "intent": "regenerate",
            "feedback": "保留事实重新组织表达",
        },
    )
    assert created.status_code == 201, created.text
    id = created.json()["id"]
    executed = await client.post(f"/api/v1/product-drafts/{id}/execute")
    assert executed.json()["status"] == "failed", executed.text
    assert executed.json()["reason"] == code
    reread = (await client.get(f"/api/v1/product-drafts/{id}")).json()
    assert reread["reason"] == code and reread["adopted"] is None
    status = (await client.get(f"/api/v1/task-status/product-drafts/{id}")).json()
    assert status["state"] == "failure" and status["reason"] == code
    assert (await client.get("/api/v1/resume-library/versions")).json()["items"] == before


async def test_refinement_database_save_failure_recovers_without_new_model_call(
    client, sessions, prep_input
):
    from sqlalchemy import func, select, text

    from career_agent.infrastructure import entities as e

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    initial = (
        await client.post(
            "/api/v1/workflows/prepare_application",
            json={**prep_input, "targets": ["resume_tailoring"]},
        )
    ).json()
    source = initial["outcome"]["targets"]["resume_tailoring"]["artifact_id"]
    created = (
        await client.post(
            "/api/v1/product-drafts",
            json={
                "request_id": str(uuid4()),
                "task": "resume_refinement",
                "source_artifact_id": source,
                "application_id": app["id"],
                "feedback": "保留事实重新组织表达",
            },
        )
    ).json()
    async with sessions.begin() as session:
        await session.execute(
            text(
                "CREATE FUNCTION reject_test_resume() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'isolated save fault'; END $$"
            )
        )
        await session.execute(
            text(
                "CREATE TRIGGER reject_test_resume BEFORE INSERT ON resume_variant_revisions "
                "FOR EACH ROW EXECUTE FUNCTION reject_test_resume()"
            )
        )
    try:
        failed = (await client.post(f"/api/v1/product-drafts/{created['id']}/execute")).json()
        assert failed["status"] == "completed" and failed["output"]
        assert failed["reason"] == "resume_library_save_failed" and failed["adopted"] is None
    finally:
        async with sessions.begin() as session:
            await session.execute(
                text("DROP TRIGGER reject_test_resume ON resume_variant_revisions")
            )
            await session.execute(text("DROP FUNCTION reject_test_resume()"))
    async with sessions() as session:
        calls = await session.scalar(select(func.count()).select_from(e.ModelCall))
    saved = (await client.post(f"/api/v1/product-drafts/{created['id']}/adopt", json={})).json()
    assert saved["adopted"]["resume_revision_id"] and saved["reason"] is None
    repeated = (await client.post(f"/api/v1/product-drafts/{created['id']}/adopt", json={})).json()
    assert repeated["adopted"] == saved["adopted"]
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(e.ModelCall)) == calls


async def test_product_preflight_rejection_records_step_without_call_or_reservation(
    client, sessions, prep_input
):
    from sqlalchemy import func, select

    from career_agent.infrastructure import entities as e
    from career_agent.product.entities import ProductDraft

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    initial = (
        await client.post(
            "/api/v1/workflows/prepare_application",
            json={**prep_input, "targets": ["resume_tailoring"]},
        )
    ).json()
    source = initial["outcome"]["targets"]["resume_tailoring"]["artifact_id"]
    created_response = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "resume_refinement",
            "source_artifact_id": source,
            "application_id": app["id"],
            "feedback": "合成意见" * 4500,
        },
    )
    assert created_response.status_code == 201, created_response.text
    id = created_response.json()["id"]
    from uuid import UUID

    response = (await client.post(f"/api/v1/product-drafts/{id}/execute")).json()
    assert response["status"] == "failed" and response["reason"] == "product_input_too_large"
    async with sessions() as session:
        row = await session.get(ProductDraft, UUID(id))
        assert row is not None
        steps = list(
            await session.scalars(select(e.AgentStep).where(e.AgentStep.run_id == row.run_id))
        )
        assert [step.reason_code for step in steps] == ["product_input_too_large"]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(e.ModelCall)
                .where(e.ModelCall.logical_operation_id == row.logical_operation_id)
            )
            == 0
        )
        assert row.usage == {}


async def test_application_optimization_actions_share_one_name_sequence(
    client, sessions, prep_input
):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    result = await client.post(
        "/api/v1/workflows/prepare_application",
        json={**prep_input, "targets": ["resume_tailoring"]},
    )
    assert result.json()["outcome"]["status"] == "completed"
    source = result.json()["outcome"]["targets"]["resume_tailoring"]["artifact_id"]
    names = []
    for intent in ("refine", "regenerate"):
        proposal = await draft(
            client,
            "resume_refinement",
            source_artifact_id=source,
            application_id=app["id"],
            intent=intent,
            feedback="保持事实，突出事务测试。",
        )
        adopted = proposal["adopted"]
        versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
        version = next(v for v in versions if v["id"] == adopted["resume_revision_id"])
        names.append(version["name"])
        replay = await client.post(f"/api/v1/product-drafts/{proposal['id']}/adopt", json={})
        assert replay.json()["adopted"] == adopted
        assert (await client.get("/api/v1/resume-library/versions")).json()["items"] == versions
        source = adopted["target_artifact_id"]
    assert names[0].endswith(" · 优化版 3"), names
    assert names[1].endswith(" · 优化版 4"), names
    assert all("AI优化版" not in name for name in names)

    # Ordinary expression editing must carry sequence metadata through its workspace.
    exact = (
        await client.get(
            f"/api/v1/resume-variants/{version['variant_id']}?revision={version['revision']}"
        )
    ).json()
    document = exact["document"]
    document["sections"][0]["items"][0]["text"] += "\n项目经验。"
    edited = await client.post(
        f"/api/v1/resume-library/versions/{version['id']}/expression",
        json={
            "request_id": str(uuid4()),
            "expected_revision": version["revision"],
            "name": version["name"],
            "document": document,
        },
    )
    assert edited.status_code == 200, edited.text
    workspace = edited.json()["workspace"]
    resolved = await client.post(
        f"/api/v1/resume-workspaces/{workspace['id']}/resolve",
        json={"expected_revision": workspace["revision"]},
    )
    assert resolved.status_code == 200, resolved.text
    from uuid import UUID

    from career_agent.infrastructure import entities as e

    async with sessions() as session:
        saved = await session.get(
            e.ResumeVariantRevision, UUID(resolved.json()["resume_revision_id"])
        )
        assert saved.library_state["optimization_number"] == 4


async def test_optimization_number_allocation_serializes_different_variants(sessions, prep_input):
    import asyncio

    from sqlalchemy import select

    from career_agent.application import resumes
    from career_agent.infrastructure import entities as e
    from career_agent.resume.schemas import ResumeDocument

    async with sessions() as session:
        original = await session.scalar(
            select(e.ResumeVariantRevision).where(
                e.ResumeVariantRevision.job_revision_id.is_not(None)
            )
        )
        assert original is not None
        document = ResumeDocument.model_validate(original.document)

    async def save():
        async with sessions() as session, session.begin():
            row = await resumes.create_variant(session, document, library_visible=False)
            return row.id, row.library_state["optimization_number"], row.display_name

    first, second = await asyncio.gather(save(), save())
    assert first[0] != second[0]
    assert sorted([first[1], second[1]]) == [2, 3]
    assert first[2] != second[2]
