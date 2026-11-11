"""Review workspace contracts through real persistence and offline model execution."""

from uuid import UUID, uuid4

import pytest
from test_interview_loop import actual_session, append
from test_preparation import inject

from career_agent.infrastructure import entities as e
from career_agent.preparation.providers import FixtureTaskProvider

pytestmark = pytest.mark.integration


class RecordingProvider(FixtureTaskProvider):
    def __init__(self):
        self.inputs = []
        self.invalid = False

    async def generate(self, candidate, context, task):
        self.inputs.append((context.task_type, task.inputs))
        response = await super().generate(candidate, context, task)
        if self.invalid and context.task_type == "interview_group_debrief":
            response.output = {}
        return response


async def create(client, source, **overrides):
    response = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "actual",
            "interview_id": source["id"],
            "expected_source_revision": source["content_revision"],
            "question_analysis": "all",
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def execute(client, run):
    response = await client.post(f"/api/v1/interview-debriefs/{run['id']}/execute")
    assert response.status_code == 200, response.text
    return (await client.get(f"/api/v1/interview-debriefs/{run['id']}?historical=true")).json()


@pytest.mark.parametrize(
    "scope,overall,count",
    [
        ("all", False, 3),
        ("all", True, 4),
        ("selected", False, 2),
        ("selected", True, 3),
        ("none", True, 1),
        ("single", True, 2),
    ],
)
async def test_review_plan_calls_and_full_overall(client, scope, overall, count):
    provider = RecordingProvider()
    inject(client, provider)
    source, _ = await actual_session(client)
    for n in range(1, 4):
        source = await append(client, source, n)
    ids = [x["entry_id"] for x in source["entries"]]
    options = (
        {"primary_entry_ids": [ids[2], ids[0]]}
        if scope == "selected"
        else {"primary_entry_id": ids[1]}
        if scope == "single"
        else {}
    )
    request_id = str(uuid4())
    run = await create(
        client,
        source,
        request_id=request_id,
        question_analysis=scope,
        overall_analysis=overall,
        **options,
    )
    result = await execute(client, run)
    assert result["status"] == "completed" and len(provider.inputs) == count
    assert result["usage"]["model_calls"] == count
    for task, inputs in provider.inputs:
        assert len(
            inputs["source"]["entries"]
            if task == "interview_overall_debrief"
            else inputs["group"]["entries"]
        ) == (3 if task == "interview_overall_debrief" else 1)
    again = await create(
        client,
        source,
        request_id=request_id,
        question_analysis=scope,
        overall_analysis=overall,
        **options,
    )
    assert again["id"] == run["id"] and again["reused"]
    await execute(client, again)
    assert len(provider.inputs) == count


async def test_review_selection_validation_and_request_receipt(client):
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    primary = source["entries"][0]["entry_id"]
    source = await append(client, source, 2, primary)
    follow = source["entries"][1]["entry_id"]
    base = dict(
        source_kind="actual",
        interview_id=source["id"],
        expected_source_revision=source["content_revision"],
    )
    for options in [
        dict(question_analysis="none", overall_analysis=False),
        dict(question_analysis="selected", primary_entry_ids=[]),
        dict(question_analysis="selected", primary_entry_ids=[primary, primary]),
        dict(question_analysis="selected", primary_entry_ids=[follow]),
        dict(question_analysis="selected", primary_entry_ids=[str(uuid4())]),
    ]:
        bad = await client.post("/api/v1/interview-debriefs", json={**base, **options})
        assert bad.status_code in {400, 409, 422}, bad.text
    request_id = str(uuid4())
    run = await create(
        client, source, request_id=request_id, question_analysis="single", primary_entry_id=primary
    )
    same = await create(
        client, source, request_id=request_id, question_analysis="single", primary_entry_id=primary
    )
    assert same["id"] == run["id"]
    selected = await create(
        client, source, question_analysis="selected", primary_entry_ids=[primary]
    )
    assert selected["id"] != run["id"]
    assert [a["group_ref"] for a in selected["artifacts"]] == [primary]
    assert (
        await client.post(
            "/api/v1/interview-debriefs",
            json={
                **base,
                "request_id": request_id,
                "question_analysis": "none",
                "overall_analysis": True,
            },
        )
    ).status_code == 409


async def test_partial_explicit_retry_keeps_success_and_idempotent_attempt(client):
    provider = RecordingProvider()
    provider.invalid = True
    inject(client, provider)
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    run = await create(client, source, overall_analysis=True)
    first = await execute(client, run)
    assert first["status"] == "partial"
    successful = next(a for a in first["artifacts"] if a["status"] == "completed")
    assert "retryable" in first["recovery"].values(), first["recovery"]
    before = len(provider.inputs)
    provider.invalid = False
    payload = dict(request_id=str(uuid4()), expected_execution_revision=0)
    path = f"/api/v1/interview-debriefs/{run['id']}/retry"
    response = await client.post(path, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["execution_revision"] == 1
    assert (await client.post(path, json=payload)).status_code == 200
    result = await execute(client, run)
    assert result["status"] == "completed" and len(provider.inputs) == before + 1
    assert next(a for a in result["artifacts"] if a["id"] == successful["id"]) == successful
    assert (await client.post(path, json=payload)).json()["status"] == "completed"
    await execute(client, run)
    assert len(provider.inputs) == before + 1


@pytest.mark.parametrize("kind", ["group", "overall", "legacy_overall"])
async def test_accepted_output_save_failure_recovers_without_new_call(
    client, monkeypatch, sessions, kind
):
    from career_agent.evaluation import recording

    provider = RecordingProvider()
    inject(client, provider)
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    from dataclasses import replace

    from career_agent.interview import debrief
    from career_agent.interview.compact import CompactOverall
    from career_agent.interview.prompts import BASE, PROMPTS

    current_inputs = debrief.inputs_for

    async def fail_save(*args, **kwargs):
        raise RuntimeError("synthetic save fault")

    with monkeypatch.context() as previous:
        if kind == "legacy_overall":
            spec = PROMPTS["interview_overall_debrief"]
            previous.setitem(
                PROMPTS,
                spec.task_type,
                replace(
                    spec,
                    prompt_version="interview_overall_debrief_v5",
                    input_schema_version="interview_overall_debrief-input-v4",
                    output_schema_version="interview_overall_debrief-output-v2",
                    output_schema=CompactOverall,
                    instruction=BASE
                    + "\nAnalyze the authoritative whole source snapshot directly. "
                    "Do not use or wait for other evaluations. "
                    "Cite answered question numbers in evidence across groups, "
                    "never UUIDs or Q/A prose. "
                    "Keep conclusions concise and avoid repeating "
                    "the same conclusion across categories.",
                ),
            )
            previous.setattr(
                debrief,
                "inputs_for",
                lambda snapshot, ref, **kwargs: current_inputs(snapshot, ref, legacy_overall=True),
            )
        previous.setattr(recording, "bind_artifact", fail_save)
        run = await create(
            client,
            source,
            question_analysis="all" if kind == "group" else "none",
            overall_analysis=kind != "group",
        )
        failed = await execute(client, run)
        assert failed["status"] == "failed" and len(provider.inputs) == 1
        assert list(failed["recovery"].values()) == ["recoverable"]
    recovered = await client.post(
        f"/api/v1/interview-debriefs/{run['id']}/retry",
        json=dict(request_id=str(uuid4()), expected_execution_revision=0),
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["status"] == "completed" and len(provider.inputs) == 1
    assert recovered.json()["artifacts"][0]["accepted_model_call_id"]


async def test_unknown_never_replays(client):
    from career_agent.models.contracts import ModelGatewayError

    class Unknown(RecordingProvider):
        async def generate(self, candidate, context, task):
            self.inputs.append((context.task_type, task.inputs))
            raise ModelGatewayError("execution_outcome_unknown", retryable=False)

    provider = Unknown()
    inject(client, provider)
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    run = await create(client, source)
    failed = await execute(client, run)
    assert list(failed["recovery"].values()) == ["unknown"]
    state = (await client.get(f"/api/v1/task-status/interview-debriefs/{run['id']}")).json()
    assert state["state"] == "unknown" and state["reason"] == "execution_outcome_unknown"
    before = len(provider.inputs)
    retry = await client.post(
        f"/api/v1/interview-debriefs/{run['id']}/retry",
        json=dict(request_id=str(uuid4()), expected_execution_revision=0),
    )
    assert retry.status_code == 409 and retry.json()["error"]["code"] == "execution_outcome_unknown"
    await execute(client, run)
    assert len(provider.inputs) == before


async def test_exhausted_budget_is_confirmed_blocked_not_unknown(client, sessions):
    provider = RecordingProvider()
    inject(client, provider)
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    run = await create(client, source, overall_analysis=True)
    async with sessions.begin() as session:
        stored = await session.get(e.DebriefRun, UUID(run["id"]))
        stored.limits = {**stored.limits, "max_model_calls": 1}
    result = await execute(client, run)
    assert result["status"] == "partial" and len(provider.inputs) == 1
    assert list(result["recovery"].values()) == ["blocked"]
    retry = await client.post(
        f"/api/v1/interview-debriefs/{run['id']}/retry",
        json=dict(request_id=str(uuid4()), expected_execution_revision=0),
    )
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "debrief_not_retryable"
    assert len(provider.inputs) == 1


async def test_frozen_content_change_excludes_metadata(client):
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    run = await create(client, source)
    assert run["source_changed"] is False
    source = (
        await client.patch(
            f"/api/v1/interviews/{source['id']}",
            json=dict(expected_revision=source["content_revision"], round_name="改名"),
        )
    ).json()
    path = f"/api/v1/interview-debriefs/{run['id']}?historical=true"
    assert (await client.get(path)).json()["source_changed"] is False
    entries = source["entries"]
    entries[0]["answer"] = "修改后的合成回答"
    await client.patch(
        f"/api/v1/interviews/{source['id']}",
        json=dict(expected_revision=source["content_revision"], entries=entries),
    )
    historical = (await client.get(path)).json()
    assert historical["source_changed"] is True and historical["snapshot"] == run["snapshot"]


async def test_delete_reference_and_execution_protection(client, sessions):
    from career_agent.interview.execution import available
    from career_agent.product.entities import ProductDraft

    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    run = await create(client, source)
    path = f"/api/v1/interview-debriefs/{run['id']}"
    async with sessions.begin() as session:
        assert await available(session, UUID(run["id"]))
        assert (await client.delete(path)).status_code == 409
    await execute(client, run)
    # Preserve an external historical invocation's frozen input reference.
    source = await append(client, source, 2)
    consumer = await create(client, source)
    await execute(client, consumer)
    async with sessions.begin() as session:
        session.add(
            ProductDraft(
                request_id=uuid4(),
                run_id=UUID(consumer["run_id"]),
                logical_operation_id=uuid4(),
                task="legacy_refinement",
                mode="fixture",
                status="completed",
                request={},
                context={"source_debrief_id": run["id"]},
                limits={},
                usage={},
            )
        )
    refused = (await client.delete(path)).json()
    assert not refused["deleted"] and refused["used_by"]
    assert (await client.get(path)).status_code == 200


async def test_note_scope_cas_legacy_time_and_pagination(client, sessions):
    source, job = await actual_session(client)
    _, other = await actual_session(client)
    async with sessions.begin() as session:
        legacy = e.KnowledgeNote(
            interview_id=UUID(source["id"]), title="旧笔记", content="保留\n原文", revision=1
        )
        session.add(legacy)
        await session.flush()
        id = str(legacy.id)
    path = f"/api/v1/knowledge-notes/{id}"
    wrong = await client.patch(
        path,
        json=dict(
            application_id=other["application_id"],
            expected_revision=1,
            title="越界",
            content="保留\n原文",
        ),
    )
    assert wrong.status_code == 409
    listing = (
        await client.get(f"/api/v1/applications/{job['application_id']}/knowledge-notes?limit=1")
    ).json()
    assert listing["items"][0]["updated_at"] is None
    changed = await client.patch(
        path,
        json=dict(
            application_id=job["application_id"],
            expected_revision=1,
            title="编辑",
            content="保留\n原文",
        ),
    )
    assert changed.status_code == 200 and changed.json()["updated_at"] is not None
    assert (
        await client.patch(
            path, json=dict(expected_revision=1, title="旧版覆盖", content="保留\n原文")
        )
    ).status_code == 409
    deleted = await client.delete(
        path, params=dict(expected_revision=2, application_id=job["application_id"])
    )
    assert deleted.status_code == 200, deleted.text
    assert (
        await client.delete(
            path, params=dict(expected_revision=2, application_id=job["application_id"])
        )
    ).status_code == 200


async def test_selected_groups_normalize_and_overall_keeps_full_source(client):
    source, _ = await actual_session(client)
    for n in range(1, 4):
        source = await append(client, source, n)
    ids = [e["entry_id"] for e in source["entries"]]
    payload = dict(
        request_id=str(uuid4()),
        source_kind="actual",
        interview_id=source["id"],
        expected_source_revision=source["content_revision"],
        question_analysis="selected",
        primary_entry_ids=[ids[2], ids[0]],
        overall_analysis=True,
    )
    first = await client.post("/api/v1/interview-debriefs", json=payload)
    assert first.status_code == 201, first.text
    row = first.json()
    assert len(row["snapshot"]["entries"]) == 3
    assert [a["group_ref"] for a in row["artifacts"]] == [ids[0], ids[2], None]
    payload["primary_entry_ids"].reverse()
    again = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    assert again["id"] == row["id"] and again["reused"]


async def test_note_create_request_identity_and_real_modified_time(client):
    _, job = await actual_session(client)
    payload = dict(
        application_id=job["application_id"],
        request_id=str(uuid4()),
        title="学习",
        content="第一行\n第二行",
    )
    first = await client.post("/api/v1/knowledge-notes", json=payload)
    assert first.status_code == 201, first.text
    row = first.json()
    assert (await client.post("/api/v1/knowledge-notes", json=payload)).json()["id"] == row["id"]
    assert (
        await client.post("/api/v1/knowledge-notes", json={**payload, "title": "另一个"})
    ).status_code == 409
    path = f"/api/v1/knowledge-notes/{row['id']}"
    unchanged = (
        await client.patch(
            path, json=dict(expected_revision=1, title=row["title"], content=row["content"])
        )
    ).json()
    assert unchanged["revision"] == 1 and unchanged["updated_at"] == row["updated_at"]
    changed = (
        await client.patch(
            path, json=dict(expected_revision=1, title="更新", content=row["content"])
        )
    ).json()
    assert changed["id"] == row["id"] and changed["revision"] == 2
    assert changed["updated_at"] is not None


async def test_debrief_remove_keeps_audit_but_not_discovery_or_reuse(client):
    source, job = await actual_session(client)
    source = await append(client, source, 1)
    payload = dict(
        request_id=str(uuid4()),
        source_kind="actual",
        interview_id=source["id"],
        expected_source_revision=source["content_revision"],
        question_analysis="all",
    )
    row = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    await client.post(f"/api/v1/interview-debriefs/{row['id']}/execute")
    response = await client.delete(f"/api/v1/interview-debriefs/{row['id']}")
    assert response.status_code == 200, response.text
    assert response.json()["deleted"]
    assert (
        await client.get(f"/api/v1/interview-debriefs/{row['id']}?historical=true")
    ).status_code == 410
    rows = (
        await client.get(f"/api/v1/interview-debriefs?application_id={job['application_id']}")
    ).json()
    assert rows["items"] == []
    assert (await client.post("/api/v1/interview-debriefs", json=payload)).status_code == 410
    payload["request_id"] = str(uuid4())
    fresh = (await client.post("/api/v1/interview-debriefs", json=payload)).json()
    assert fresh["id"] != row["id"]


async def test_generation_chain_removal_summary_and_receipts(client, sessions):
    source, job = await actual_session(client)
    source = await append(client, source, 1)
    root = await create(client, source)
    await execute(client, root)
    child = (
        await client.post(
            f"/api/v1/interview-debriefs/{root['id']}/regenerate", json={"question_analysis": "all"}
        )
    ).json()
    await execute(client, child)
    assert (await client.get(f"/api/v1/interview-debriefs/{root['id']}")).json()["id"] == child[
        "id"
    ]
    assert (await client.delete(f"/api/v1/interview-debriefs/{child['id']}")).json()["deleted"]
    assert (await client.get(f"/api/v1/interview-debriefs/{root['id']}")).json()["id"] == root["id"]
    status = (await client.get(f"/api/v1/task-status/interview-debriefs/{child['id']}")).json()
    assert status["state"] == "removed" and status["selection"] == {}
    summary = (await client.get(f"/api/v1/applications/{job['application_id']}/summary")).json()
    assert summary["debrief"]["count"] == 1
    assert (await client.delete(f"/api/v1/interview-debriefs/{root['id']}")).json()["deleted"]
    summary = (await client.get(f"/api/v1/applications/{job['application_id']}/summary")).json()
    assert summary["debrief"] == {"count": 0, "latest": None}
    async with sessions() as session:
        assert (await session.get(e.DebriefRun, UUID(root["id"]))).snapshot == root["snapshot"]
        assert await session.get(e.DebriefRun, UUID(child["id"]))


async def test_note_concurrent_create_and_legacy_upgrade(client, sessions, migrated_url):
    import asyncio

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    source, job = await actual_session(client)
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "c105c2002601")
    id = uuid4()
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO knowledge_notes (id,created_at,title,content,revision,application_id) "
                "VALUES (:id,now(),'旧记录','旧正文',1,:app)"
            ),
            {"id": id, "app": UUID(job["application_id"])},
        )
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)
    async with sessions() as session:
        legacy = await session.get(e.KnowledgeNote, id)
        assert legacy.updated_at is None and legacy.request_id is None
    payload = dict(
        application_id=job["application_id"],
        title="并发请求",
        content="保留",
        request_id=str(uuid4()),
    )
    first, second = await asyncio.gather(
        *[client.post("/api/v1/knowledge-notes", json=payload) for _ in range(2)]
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    page = (
        await client.get(f"/api/v1/applications/{job['application_id']}/knowledge-notes?limit=1")
    ).json()
    assert page["has_more"] and page["items"][0]["id"] == first.json()["id"]
    page2 = (
        await client.get(
            f"/api/v1/applications/{job['application_id']}/knowledge-notes?limit=1&offset=1"
        )
    ).json()
    assert page2["items"][0]["id"] == str(id)


async def test_concurrent_root_and_child_removal_share_lock_order(client, sessions):
    import asyncio

    from sqlalchemy import select, text

    source, job = await actual_session(client)
    source = await append(client, source, 1)
    root = await create(client, source)
    await execute(client, root)
    child = (
        await client.post(
            f"/api/v1/interview-debriefs/{root['id']}/regenerate", json={"question_analysis": "all"}
        )
    ).json()
    await execute(client, child)

    async def waiting(count):
        for _ in range(200):
            async with sessions() as inspect:
                n = await inspect.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND wait_event_type='Lock'"
                    )
                )
            if n >= count:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("deletion did not reach its application lock")

    async with sessions.begin() as guard:
        await guard.scalar(
            select(e.Application)
            .where(e.Application.id == UUID(job["application_id"]))
            .with_for_update()
        )
        deleting_child = asyncio.create_task(
            client.delete(f"/api/v1/interview-debriefs/{child['id']}")
        )
        await waiting(1)
        deleting_root = asyncio.create_task(
            client.delete(f"/api/v1/interview-debriefs/{root['id']}")
        )
        await waiting(2)
    results = await asyncio.wait_for(asyncio.gather(deleting_child, deleting_root), 10)
    assert [r.status_code for r in results] == [200, 200]
    assert all(r.json()["deleted"] for r in results)


async def test_rejected_overall_evidence_can_explicitly_retry_without_repeating_groups(
    client, sessions
):
    class InvalidEvidence(RecordingProvider):
        invalid_evidence = True

        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if self.invalid_evidence and context.task_type == "interview_overall_debrief":
                response.output["strengths"] = [
                    {"content": "能够说明验证方法。", "evidence": ["99"]}
                ]
            return response

    provider = InvalidEvidence()
    inject(client, provider)
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    first = await execute(client, await create(client, source, overall_analysis=True))
    assert first["status"] == "partial"
    overall = next(a for a in first["artifacts"] if a["kind"] == "overall")
    assert overall["error_code"] == "invalid_evidence_reference"
    assert first["recovery"][overall["id"]] == "retryable"
    from sqlalchemy import select

    async with sessions() as session:
        failed_call = (
            await session.scalars(
                select(e.ModelCall).where(e.ModelCall.error_code == "invalid_evidence_reference")
            )
        ).one()
        diagnostic = failed_call.versions["output_diagnostic"]
        assert diagnostic["guardrail_code"] == "invalid_evidence_reference"
        assert diagnostic["validation_issues"] == [
            {
                "loc": ["strengths", 0, "evidence", 0],
                "type": "unknown_number",
                "message": "canonical schema validation failed",
            }
        ]
        assert diagnostic["reference_diagnostic"]["allowed_count"] == 1
        assert diagnostic["reference_diagnostic"]["reference_kind"] == "number"
        assert "能够说明验证方法" not in str(diagnostic)

    status = (await client.get(f"/api/v1/task-status/interview-debriefs/{first['id']}")).json()
    assert status["state"] == "partial" and status["reason"] == "invalid_evidence_reference"
    before = len(provider.inputs)
    provider.invalid_evidence = False
    retried = await client.post(
        f"/api/v1/interview-debriefs/{first['id']}/retry",
        json=dict(request_id=str(uuid4()), expected_execution_revision=0),
    )
    assert retried.status_code == 200
    result = await execute(client, retried.json())
    assert result["status"] == "completed" and len(provider.inputs) == before + 1
    assert result["artifacts"][0] == first["artifacts"][0]


async def test_independent_create_intents_execute_independently_but_request_replays_do_not(client):
    provider = RecordingProvider()
    inject(client, provider)
    source, _ = await actual_session(client)
    source = await append(client, source, 1)
    request = str(uuid4())
    first = await create(client, source, request_id=request, overall_analysis=True)
    replay = await create(client, source, request_id=request, overall_analysis=True)
    assert replay["id"] == first["id"]
    second = await create(client, source, request_id=str(uuid4()), overall_analysis=True)
    assert second["id"] != first["id"]
    for row in [first, replay, second]:
        assert (await execute(client, row))["status"] == "completed"
    assert len(provider.inputs) == 4
    assert first["root_run_id"] != second["root_run_id"] or first["root_run_id"] is None
