"""Current-state saves must not manufacture changes to frozen interview sources."""

import pytest
from test_preparation import prep_input as prep_fixture

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_mock_active_generation_cannot_be_recovered_or_redispatched(client, prep_input):
    import asyncio
    from uuid import uuid4

    from test_preparation import inject

    from career_agent.preparation.providers import FixtureTaskProvider

    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(FixtureTaskProvider):
        count = 0

        async def generate(self, candidate, context, task):
            self.count += 1
            entered.set()
            await release.wait()
            return await super().generate(candidate, context, task)

    provider = Delayed()
    inject(client, provider)
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}"
    request = {"request_id": str(uuid4()), "expected_revision": row["revision"]}
    generation = asyncio.create_task(client.post(path + "/generate", json=request))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        running = (await client.get(path)).json()
        assert running["generation_active"] and running["turns"] == []
        rejected = await client.post(
            path + "/recover",
            json={"request_id": str(uuid4()), "expected_revision": running["revision"]},
        )
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "generation_in_progress"
        status = await client.get(
            f"/api/v1/task-status/mock-interviews/{row['id']}?request_id={request['request_id']}"
        )
        assert status.json()["state"] == "running"
    finally:
        release.set()
    done = (await generation).json()
    assert len(done["turns"]) == 1 and done["stop_reason"] is None
    assert provider.count == 1
    repeated = (await client.post(path + "/generate", json=request)).json()
    assert repeated["turns"] == done["turns"] and provider.count == 1


async def test_noop_preserves_revision_and_legacy_note_structure(client, prep_input):
    application = (await client.get("/api/v1/applications")).json()["items"][0]
    response = await client.post(
        "/api/v1/interviews",
        json={"application_id": application["id"], "round_name": "原始名称", "status": "draft"},
    )
    assert response.status_code == 201, response.text
    row = response.json()
    path = f"/api/v1/interviews/{row['id']}"
    for text in ("第一条笔记", "第二条笔记"):
        response = await client.post(
            path + "/notes", json={"expected_revision": row["content_revision"], "text": text}
        )
        assert response.status_code == 201, response.text
        row = response.json()
    saved = await client.patch(
        path,
        json={
            "expected_revision": row["content_revision"],
            "round_name": row["round_name"],
            "entries": row["entries"],
            "notes_text": "\n".join(note["text"] for note in row["notes"]),
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["content_revision"] == row["content_revision"]
    assert saved.json()["notes"] == row["notes"]
    assert saved.json()["round_number"] is None
    assert saved.json()["interview_type"] is None
    assert (await client.get(path)).json() == saved.json()


async def test_atomic_create_retry_round_conflict_and_empty_rejection(client, prep_input):
    from uuid import uuid4

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    body = {
        "request_id": str(uuid4()),
        "application_id": app["id"],
        "round_number": 1,
        "interview_type": "technical",
        "entries": [
            {"entry_id": str(uuid4()), "order": 1, "kind": "primary", "question": "如何测试？"}
        ],
        "notes_text": "后续复习",
    }
    created = await client.post("/api/v1/interviews", json=body)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["status"] == "completed" and row["content_revision"] == 1
    assert row["entries"][0]["entry_id"] == body["entries"][0]["entry_id"]
    repeated = await client.post("/api/v1/interviews", json=body)
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == row["id"]
    conflict = await client.post("/api/v1/interviews", json={**body, "request_id": str(uuid4())})
    assert conflict.status_code == 409
    empty = await client.post(
        "/api/v1/interviews",
        json={**body, "request_id": str(uuid4()), "round_number": 2, "entries": []},
    )
    assert empty.status_code == 422
    listing = (await client.get("/api/v1/interviews", params={"application_id": app["id"]})).json()
    assert len(listing) == 1


async def test_mock_creation_identity_and_application_scope(client, prep_input):
    from uuid import uuid4

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    binding = await client.put(
        f"/api/v1/applications/{app['id']}/context", json={"expected_revision": 1, **prep_input}
    )
    assert binding.status_code == 200, binding.text
    body = {
        "request_id": str(uuid4()),
        "application_binding": {
            "application_id": app["id"],
            "revision": binding.json()["revision"],
        },
        "context": prep_input,
    }
    first = await client.post("/api/v1/mock-interviews", json=body)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/mock-interviews", json=body)
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["application_id"] == app["id"]
    listing = (
        await client.get("/api/v1/mock-interviews", params={"application_id": app["id"]})
    ).json()
    assert [row["id"] for row in listing["items"]] == [first.json()["id"]]
    item = listing["items"][0]
    assert item["creation_request_id"] == body["request_id"]
    assert item["primary_question_count"] == 0
    assert item["generation_active"] is False
    assert item["focus"] == "mixed"
    # Exact legacy source verification resolves the unique relational owner without a backfill.
    legacy = await client.post("/api/v1/mock-interviews", json={"context": prep_input})
    assert legacy.status_code == 201, legacy.text
    listing = (
        await client.get("/api/v1/mock-interviews", params={"application_id": app["id"]})
    ).json()
    assert {row["id"] for row in listing["items"]} == {first.json()["id"], legacy.json()["id"]}
    pages = [
        (
            await client.get(
                "/api/v1/mock-interviews",
                params={"application_id": app["id"], "limit": 1, "offset": offset},
            )
        ).json()
        for offset in (0, 1)
    ]
    assert pages[0]["has_more"] and not pages[1]["has_more"]
    assert {page["items"][0]["id"] for page in pages} == {first.json()["id"], legacy.json()["id"]}
    other = (
        await client.post(
            "/api/v1/jobs", json={"company_name": "隔离公司", "title": "研发", "jd_text": "Python"}
        )
    ).json()
    isolated = (
        await client.get(
            "/api/v1/mock-interviews", params={"application_id": other["application_id"]}
        )
    ).json()
    assert isolated["items"] == []


@pytest.mark.parametrize("recovery_action", ["generate", "recover", "orphan"])
async def test_mock_saved_output_recovery_never_calls_provider_twice(
    client, prep_input, monkeypatch, recovery_action, sessions
):
    from uuid import UUID, uuid4

    from sqlalchemy.exc import OperationalError
    from test_preparation import inject

    from career_agent.evaluation import recording
    from career_agent.infrastructure import entities as e
    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        count = 0

        async def generate(self, candidate, context, task):
            self.count += 1
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    original = recording.bind_artifact
    broken = True

    async def fail_once(*args, **kwargs):
        nonlocal broken
        if broken:
            broken = False
            raise OperationalError("synthetic persistence fault", {}, None)
        return await original(*args, **kwargs)

    monkeypatch.setattr(recording, "bind_artifact", fail_once)
    created = await client.post("/api/v1/mock-interviews", json={"context": prep_input})
    row = created.json()
    path = f"/api/v1/mock-interviews/{row['id']}"
    request = {"expected_revision": row["revision"], "request_id": str(uuid4())}
    failed = await client.post(path + "/generate", json=request)
    assert failed.status_code == 200, failed.text
    row = failed.json()
    assert row["stop_reason"] == "artifact_save_failed"
    assert row["turns"] == [] and row["primary_question_count"] == 0
    assert provider.count == 1
    audit_state = "failure"
    if recovery_action == "orphan":
        from sqlalchemy import select

        audit_state = "running"
        async with sessions.begin() as session:
            stored = await session.get(e.MockInterviewSession, UUID(row["id"]))
            stored.generation_active = True
            receipt = await session.scalar(
                select(e.MockRequestReceipt).where(
                    e.MockRequestReceipt.request_id == UUID(request["request_id"])
                )
            )
            receipt.outcome = {
                "state": "running",
                "logical_operation_id": str(stored.generation_operation_id),
                "revision": row["revision"] - 1,
            }
        projected = (await client.get(path)).json()
        assert projected["generation_active"] is False
        assert projected["stop_reason"] == "execution_outcome_unknown"
        recovery_action = "recover"
    restored = await client.post(
        path + "/" + recovery_action,
        json={"expected_revision": row["revision"], "request_id": str(uuid4())},
    )
    assert restored.status_code == 200, restored.text
    row = restored.json()
    assert row["status"] == "waiting_answer" and len(row["turns"]) == 1
    assert provider.count == 1
    assert (await client.get(path)).json() == row
    # The read projection follows the exact accepted output, without rewriting the audit receipt.
    receipt = await client.get(
        f"/api/v1/task-status/mock-interviews/{row['id']}?request_id={request['request_id']}"
    )
    assert receipt.json()["state"] == "success"
    assert receipt.json()["selection"]["question"] == row["turns"][0]["id"]
    async with sessions() as session:
        from sqlalchemy import select

        audit = await session.scalar(
            select(e.MockRequestReceipt).where(
                e.MockRequestReceipt.request_id == UUID(request["request_id"])
            )
        )
        assert audit.outcome["state"] == audit_state


async def test_current_numbering_reorders_without_rewriting_existing_debrief(client):
    from test_interview_loop import actual_session, append

    row, _ = await actual_session(client)
    row = await append(client, row, 1)
    row = await append(client, row, 2)
    created = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "actual",
            "interview_id": row["id"],
            "expected_source_revision": row["content_revision"],
            "question_analysis": "all",
        },
    )
    assert created.status_code == 201, created.text
    before = created.json()
    entries = row["entries"]
    entries[0]["order"], entries[1]["order"] = 2, 1
    response = await client.patch(
        f"/api/v1/interviews/{row['id']}",
        json={
            "expected_revision": row["content_revision"],
            "entries": entries,
        },
    )
    assert response.status_code == 200, response.text
    current = response.json()["entries"]
    assert current[0]["entry_id"] == entries[1]["entry_id"]
    assert [entry["main_question_number"] for entry in current] == [1, 2]
    after = await client.get(f"/api/v1/interview-debriefs/{before['id']}")
    assert after.json()["snapshot"] == before["snapshot"]


async def test_mock_unknown_recovery_never_dispatches(client, prep_input, sessions):
    from uuid import UUID, uuid4

    from sqlalchemy import func, select

    from career_agent.infrastructure import entities as e

    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    async with sessions.begin() as session:
        stored = await session.get(e.MockInterviewSession, UUID(row["id"]))
        stored.generation_active = True
        stored.generation_operation_id = uuid4()
    orphaned = (await client.get(f"/api/v1/mock-interviews/{row['id']}")).json()
    assert orphaned["generation_active"] is False
    assert orphaned["stop_reason"] == "execution_outcome_unknown"
    response = await client.post(
        f"/api/v1/mock-interviews/{row['id']}/recover",
        json={
            "expected_revision": row["revision"],
            "request_id": str(uuid4()),
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "execution_outcome_unknown"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(e.ModelCall)) == 0
        stored = await session.get(e.MockInterviewSession, UUID(row["id"]))
        assert stored.generation_active and stored.interviewer_turn_count == 0


async def test_prep_and_mock_receive_resume_expressions_not_other_profile_evidence(
    client, prep_input
):
    import json
    from uuid import uuid4

    from test_preparation import inject, run

    from career_agent.preparation.providers import FixtureTaskProvider

    class Provider(FixtureTaskProvider):
        contexts = {}

        async def generate(self, candidate, context, task):
            self.contexts[context.task_type] = task.inputs.get("context", task.inputs)
            return await super().generate(candidate, context, task)

    provider = Provider()
    inject(client, provider)
    prepared = await run(client, {**prep_input, "use_company_research": False}, "prepare_interview")
    assert prepared["state"]["status"] == "completed", prepared
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    generated = await client.post(
        f"/api/v1/mock-interviews/{row['id']}/generate",
        json={
            "expected_revision": row["revision"],
            "request_id": str(uuid4()),
        },
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["status"] == "waiting_answer", generated.text
    for name in ["interview_preparation", "mock_interview_turn_generation"]:
        context = provider.contexts[name]
        evidence = context.get("stable_context", context)["facts"]
        assert len(evidence) == 1
        assert evidence[0]["statement"] == "使用 Python 和 FastAPI 构建模拟服务。"
        assert "RAG / Agent 合成数据实验" not in json.dumps(context, ensure_ascii=False)
        assert "使用 PostgreSQL 验证事务回滚" not in json.dumps(context, ensure_ascii=False)


async def test_mock_unknown_gateway_outcome_is_not_retryable_failure(
    client, prep_input, monkeypatch
):
    from uuid import uuid4

    from career_agent.interview.calls import InterviewCalls
    from career_agent.models.contracts import ModelGatewayError

    calls = 0

    async def unknown(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise ModelGatewayError("recovery_decision_required")

    monkeypatch.setattr(InterviewCalls, "generate", unknown)
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}"
    request_id = str(uuid4())
    response = await client.post(
        path + "/generate",
        json={
            "expected_revision": row["revision"],
            "request_id": request_id,
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()
    state = await client.get(
        f"/api/v1/task-status/mock-interviews/{row['id']}?request_id={request_id}"
    )
    assert state.json()["state"] == "unknown"
    retry = await client.post(
        path + "/generate",
        json={
            "expected_revision": row["revision"],
            "request_id": str(uuid4()),
        },
    )
    assert retry.status_code == 409
    assert calls == 1 and row["turns"] == []


async def test_actual_concurrent_round_creation_has_one_winner(client, prep_input):
    import asyncio
    from uuid import uuid4

    app = (await client.get("/api/v1/applications")).json()["items"][0]
    body = {
        "application_id": app["id"],
        "round_number": 3,
        "interview_type": "technical",
        "entries": [
            {"entry_id": str(uuid4()), "order": 1, "kind": "primary", "question": "设计测试"}
        ],
    }
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/interviews", json={**body, "request_id": str(uuid4())})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    rows = (await client.get("/api/v1/interviews", params={"application_id": app["id"]})).json()
    assert len(rows) == 1 and rows[0]["round_number"] == 3


async def test_mock_answer_preflight_failure_rolls_back_without_advancing(
    client, prep_input, monkeypatch
):
    from uuid import uuid4

    from career_agent.interview.calls import InterviewCalls
    from career_agent.models.contracts import ModelGatewayError

    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}"
    row = (
        await client.post(
            path + "/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    ).json()
    original = InterviewCalls.preflight

    def reject(*args, **kwargs):
        raise ModelGatewayError("mock_input_too_large")

    monkeypatch.setattr(InterviewCalls, "preflight", reject)
    body = {
        "expected_revision": row["revision"],
        "request_id": str(uuid4()),
        "pending_question_id": row["pending_question_id"],
        "answer": "已输入但尚未保存",
    }
    response = await client.post(path + "/answers", json=body)
    assert response.status_code >= 400
    assert (await client.get(path)).json() == row
    monkeypatch.setattr(InterviewCalls, "preflight", original)
    saved = await client.post(path + "/answers", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["turns"][0]["answer"] == body["answer"]
    assert saved.json()["turns"][1]["question"]["primary_entry_id"] == row["pending_question_id"]


@pytest.mark.parametrize("intent", ["refine", "regenerate"])
async def test_prep_refinement_keeps_original_frozen_inputs(client, prep_input, sessions, intent):
    from uuid import UUID, uuid4

    from test_preparation import run
    from test_product_drafts import draft

    from career_agent.infrastructure import entities as e
    from career_agent.product.entities import ProductDraft

    original = await run(client, {**prep_input, "use_company_research": False}, "prepare_interview")
    target = original["outcome"]["targets"]["interview_preparation"]["artifact_id"]
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    # A later company report is available, but refining the old record must not adopt it.
    job = (await client.get("/api/v1/jobs")).json()[0]
    operation = (
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
    assert (await client.post(f"/api/v1/operations/{operation['id']}/execute")).json()[
        "status"
    ] == "success"
    proposal = await draft(
        client,
        "interview_preparation_refinement",
        source_artifact_id=target,
        application_id=app["id"],
        intent=intent,
        feedback="保持来源，精简回答要点。",
    )
    assert proposal["adopted"]
    async with sessions() as session:
        old = await session.get(e.PreparationArtifact, UUID(target))
        stored = await session.get(ProductDraft, UUID(proposal["id"]))
        frozen = old.data["output"]["interview_context"]
        assert frozen["research_report_id"] is None
        assert stored.context["context"] == {**frozen, "source_artifact_id": target}
        newer = await session.get(
            e.PreparationArtifact, UUID(proposal["adopted"]["target_artifact_id"])
        )
        assert (
            newer.data["output"]["interview_context"]["source_resume_revision_id"]
            == prep_input["resume_revision_id"]
        )
        assert newer.data["output"]["interview_context"]["research_report_id"] is None


async def test_mock_answer_commit_failure_preserves_pending_question(client, prep_input):
    from uuid import uuid4

    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from career_agent.infrastructure import entities as e

    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}"
    row = (
        await client.post(
            path + "/generate",
            json={"expected_revision": row["revision"], "request_id": str(uuid4())},
        )
    ).json()
    body = {
        "expected_revision": row["revision"],
        "request_id": str(uuid4()),
        "pending_question_id": row["pending_question_id"],
        "answer": "保留此回答",
    }

    def fail_answer_flush(session, *args):
        if any(isinstance(value, e.MockInterviewTurn) and value.answer for value in session.dirty):
            raise OperationalError("isolated answer write fault", {}, None)

    event.listen(Session, "before_flush", fail_answer_flush)
    try:
        failed = await client.post(path + "/answers", json=body)
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "internal_error"
    finally:
        event.remove(Session, "before_flush", fail_answer_flush)
    assert (await client.get(path)).json() == row
    restored = await client.post(path + "/answers", json=body)
    assert restored.status_code == 200, restored.text
    assert restored.json()["turns"][0]["answer"] == body["answer"]
    assert len(restored.json()["turns"]) == 2
