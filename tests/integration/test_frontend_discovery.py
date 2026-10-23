"""Offline Web discovery contracts against PostgreSQL, including metadata-only boundaries."""

import asyncio
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import select
from test_recovery_ops import SPEC, context, make

from career_agent.evaluation import entities as q
from career_agent.evaluation.contracts import (
    CapturePayload,
    EvalRunRequest,
    EvalSuite,
    JudgeSpec,
    SamplingDecision,
    Subject,
)
from career_agent.evaluation.fixtures import initial_cases
from career_agent.evaluation.runner import EvalRunner
from career_agent.evaluation.store import put_case, put_suite
from career_agent.infrastructure import entities as e
from career_agent.ops.entities import AttemptJournal, RecoveryIncident

pytestmark = pytest.mark.integration
HEADERS = {"X-Ops-Token": "synthetic-discovery-token"}


def authorize(client):
    client._transport.app.state.settings.ops_token = SecretStr(HEADERS["X-Ops-Token"])


async def test_application_knowledge_direct_legacy_global_and_conflict(client, synthetic, sessions):
    job = (await client.post("/api/v1/jobs", json=synthetic["job"])).json()
    other = (await client.post("/api/v1/jobs", json=synthetic["job"])).json()
    app_id = job["application_id"]
    interview = (
        await client.post(
            "/api/v1/interviews",
            json={
                "application_id": app_id,
                "round_name": "技术一面",
                "expected_revision": 0,
            },
        )
    ).json()
    note = {"title": "Synthetic note", "content": "Synthetic content"}
    global_note = (await client.post("/api/v1/knowledge-notes", json=note)).json()
    legacy = (
        await client.post(
            "/api/v1/knowledge-notes",
            json={
                **note,
                "interview_id": interview["id"],
            },
        )
    ).json()
    direct = (
        await client.post(
            "/api/v1/knowledge-notes",
            json={
                **note,
                "application_id": app_id,
            },
        )
    ).json()
    both = (
        await client.post(
            "/api/v1/knowledge-notes",
            json={
                **note,
                "application_id": app_id,
                "interview_id": interview["id"],
            },
        )
    ).json()
    assert (
        await client.post(
            "/api/v1/knowledge-notes",
            json={
                **note,
                "application_id": other["application_id"],
                "interview_id": interview["id"],
            },
        )
    ).status_code == 409
    assert (
        await client.post(
            "/api/v1/knowledge-notes",
            json={
                **note,
                "application_id": str(uuid4()),
            },
        )
    ).status_code == 404
    # Equal sort keys still have deterministic pagination; a note with both links appears once.
    async with sessions.begin() as session:
        notes = list(await session.scalars(select(e.KnowledgeNote)))
        for row in notes:
            row.created_at = notes[0].created_at
    url = f"/api/v1/applications/{app_id}/knowledge-notes"
    first = (await client.get(url, params={"limit": 2})).json()
    second = (await client.get(url, params={"limit": 2, "offset": 2})).json()
    assert first["has_more"] and not second["has_more"]
    assert {n["id"] for n in first["items"] + second["items"]} == {
        legacy["id"],
        direct["id"],
        both["id"],
    }
    all_notes = (await client.get("/api/v1/knowledge-notes")).json()
    assert len(all_notes) == 4 and global_note["id"] in {x["id"] for x in all_notes}
    assert not (
        await client.get(f"/api/v1/applications/{other['application_id']}/knowledge-notes")
    ).json()["items"]
    assert (await client.get(f"/api/v1/applications/{uuid4()}/knowledge-notes")).status_code == 404


async def test_internal_discovery_auth_filters_pagination_and_private_boundary(client, sessions):
    authorize(client)
    paths = [
        "suites",
        "runs",
        "comparisons",
        "judges",
        "captures",
        "trials",
        "sampling-records",
        "case-index",
        "feedback",
    ]
    for path in paths:
        assert (await client.get(f"/api/v1/evaluation/{path}")).status_code == 403
    case = initial_cases()[0]
    async with sessions.begin() as session:
        case_row = await put_case(session, case)
        suite = await put_suite(
            session,
            EvalSuite(
                suite_id="discovery",
                version=1,
                members=[{"case_id": case.case_id, "case_version": case.case_version}],
            ),
        )
    runner = EvalRunner(sessions, client._transport.app.state.settings)
    runs = [
        await runner.create(EvalRunRequest(suite_id="discovery", suite_version=1)) for _ in range(2)
    ]
    subject = Subject(subject_id=uuid4(), task_type="greeting_generation")
    async with sessions.begin() as session:
        sampling = q.SamplingRow(
            subject_id=subject.subject_id,
            decision_key="a" * 64,
            data=SamplingDecision(
                subject=subject,
                policy_version="sampling-v1",
                effective_rate=1,
                sampled=True,
                reason="forced_manual",
                decision_key="a" * 64,
                population="targeted",
            ).model_dump(mode="json"),
        )
        session.add(sampling)
        await session.flush()
        judge = q.JudgeRow(
            sampling_id=sampling.id,
            spec=JudgeSpec(
                target=subject.task_type,
                prompt_version="judge-v1",
                prompt_hash="c" * 64,
                model_policy_version="model-v1",
            ).model_dump(mode="json"),
            status="failed",
            reason_code="provider_timeout",
        )
        capture = q.CaptureRow(
            subject_id=subject.subject_id,
            status="captured",
            content_hash="b" * 64,
            payload=CapturePayload(
                subject=subject,
                source_snapshot={"private": "DO_NOT_LIST"},
                model_input={"private": "DO_NOT_LIST"},
                output={"private": "DO_NOT_LIST"},
                provenance={},
            ).model_dump(mode="json"),
        )
        comparison = q.ComparisonRow(
            baseline_id=runs[0],
            candidate_id=runs[1],
            policy_version="comparison-priority-v2",
            data={"private": "DO_NOT_LIST"},
        )
        trial = await session.scalar(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == runs[0]))
        session.add_all([judge, capture, comparison])

    async def get(path, **params):
        response = await client.get(f"/api/v1/evaluation/{path}", params=params, headers=HEADERS)
        assert response.status_code == 200, response.text
        assert "DO_NOT_LIST" not in response.text
        return response.json()

    assert (await get("suites", suite_key="discovery"))["items"][0]["id"] == str(suite.id)
    assert (await get(f"suites/{suite.id}"))["suite"]["members"]
    page1 = await get("runs", suite_id=str(suite.id), limit=1)
    page2 = await get("runs", suite_id=str(suite.id), limit=1, offset=1)
    assert page1["has_more"] and not page2["has_more"]
    assert page1["items"][0]["id"] != page2["items"][0]["id"]
    assert not (await get("runs", status="failed"))["items"]
    assert (await get("comparisons", baseline_run_id=str(runs[0])))["items"][0]["id"] == str(
        comparison.id
    )
    assert (await get("trials", run_id=str(runs[0])))["items"][0]["id"] == str(trial.id)
    assert (
        await get("judges", status="failed", task_type=subject.task_type, population="targeted")
    )["items"][0]["id"] == str(judge.id)
    assert not (await get("judges", population="random"))["items"]
    assert (await get("captures", task_type=subject.task_type))["items"][0]["id"] == str(capture.id)
    assert not (await get("captures", status="dismissed"))["items"]
    assert (await get("sampling-records", sampled=True))["items"][0]["subject_id"] == str(
        subject.subject_id
    )
    assert not (await get("sampling-records", sampled=False))["items"]
    assert (await get("case-index", tag=case.tags[0]))["items"][0]["id"] == str(case_row.id)
    assert not (await get("case-index", tag="absent"))["items"]
    for path in paths:
        assert (
            await client.get(f"/api/v1/evaluation/{path}?limit=0", headers=HEADERS)
        ).status_code == 422


async def test_attention_distinguishes_uncertainty_incident_failure_and_resolution(
    client, sessions
):
    authorize(client)
    owner, gateway = make(sessions)
    await owner.start()
    client._transport.app.state.control_owner = owner
    try:
        ctx = await gateway.prepare(context(), SPEC.task({}))
        await owner.intent(ctx)
        # Restart converts dispatch intent to unknown, without replaying a provider call.
        await owner.close()
        owner, gateway = make(sessions, owner.scope)
        await owner.start()
        client._transport.app.state.control_owner = owner
        async with sessions.begin() as session:
            run = e.AgentRun(
                workflow="prepare_application",
                status="failed",
                stop_reason="attempt_limit_exceeded",
            )
            session.add(run)
            # Unrelated quota scope must never appear.
            session.add(RecoveryIncident(scope="other", attempt_id=uuid4(), reason="unknown"))
        response = await client.get("/api/v1/ops/attention", headers=HEADERS)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert {x["category"] for x in items} == {
            "execution_failure",
            "unknown_outcome",
            "recovery_incident",
        }
        failed = next(x for x in items if x["source"] == "run")
        assert failed["allowed_actions"] == ["inspect"]
        incident = next(x for x in items if x["source"] == "recovery_incident")
        assert incident["allowed_actions"] == ["inspect", "reconcile"]
        assert not any(key in response.text for key in ('"selection"', '"payload"', '"prompt"'))
        async with sessions.begin() as session:
            row = await session.get(RecoveryIncident, UUID(incident["id"]))
            row.status = "acknowledged"
            journal = await session.scalar(
                select(AttemptJournal).where(AttemptJournal.scope == owner.scope)
            )
            journal.data = {**journal.data, "recovered": True}
        filtered = (
            await client.get("/api/v1/ops/attention?source=recovery_incident", headers=HEADERS)
        ).json()
        assert not filtered["items"]
        history = (
            await client.get(
                "/api/v1/ops/attention?source=recovery_incident&include_resolved=true",
                headers=HEADERS,
            )
        ).json()
        assert len(history["items"]) == 1
        assert gateway.adapters["synthetic"].calls == 0
    finally:
        await owner.close()
        client._transport.app.state.control_owner = None


async def test_knowledge_migration_history_and_drift(migrated_url, sessions, client, synthetic):
    job = (await client.post("/api/v1/jobs", json=synthetic["job"])).json()
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "ad04c0402601")
    from sqlalchemy import text

    id = uuid4()
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO knowledge_notes (id,created_at,title,content) "
                "VALUES (:id,now(),'legacy','legacy')"
            ),
            {"id": id},
        )
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)
    notes = (await client.get("/api/v1/knowledge-notes")).json()
    assert notes[0]["application_id"] is None
    assert (
        await client.post(
            "/api/v1/knowledge-notes",
            json={
                "title": "direct",
                "content": "direct",
                "application_id": job["application_id"],
            },
        )
    ).status_code == 201


async def test_attention_product_states_and_attempt_detail(client, sessions):
    from career_agent.preparation.contracts import WorkflowRequest
    from career_agent.product.contracts import OperationCreate
    from career_agent.product.entities import ProductOperation

    authorize(client)
    owner, gateway = make(sessions)
    await owner.start()
    client._transport.app.state.control_owner = owner
    try:
        ids = {}
        async with sessions.begin() as session:
            for state in ("recovery_required", "failure", "decision_required", "success"):
                request = OperationCreate(
                    request_id=uuid4(),
                    kind="prepare_application",
                    request=WorkflowRequest(
                        profile_id=uuid4(), job_revision_id=uuid4(), targets=["fit_analysis"]
                    ),
                )
                row = ProductOperation(
                    request_id=request.request_id,
                    kind=request.kind,
                    run_id=uuid4(),
                    payload=request.model_dump(mode="json"),
                    status=state,
                    reason="recovery_decision_required" if state == "recovery_required" else None,
                )
                session.add(row)
                await session.flush()
                ids[state] = str(row.id)
        url = "/api/v1/ops/attention?source=product_operation"
        response = await client.get(url, headers=HEADERS)
        found = response.json()["items"]
        assert {x["id"] for x in found} == {
            ids[s] for s in ("failure", "recovery_required", "decision_required")
        }
        assert {x["category"] for x in found} == {
            "execution_failure",
            "recovery_required",
            "user_input_or_decision",
        }
        assert all(x["allowed_actions"] == ["inspect"] for x in found)
        first = (await client.get(url + "&limit=1", headers=HEADERS)).json()
        second = (await client.get(url + "&limit=1&offset=1", headers=HEADERS)).json()
        assert first["has_more"] and first["items"][0]["id"] != second["items"][0]["id"]
        assert (
            len((await client.get(url + "&status=failure", headers=HEADERS)).json()["items"]) == 1
        )
        ctx = await gateway.prepare(context(), SPEC.task({}))
        await gateway.generate(ctx, SPEC.task({}))
        id = ctx.selection.attempt_id
        detail = await client.get(f"/api/v1/ops/attempts/{id}", headers=HEADERS)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["status"] == "settled" and body["usage"] is not None
        assert body["attempt_id"] == str(id)
        assert not {"selection", "prompt", "input", "output", "raw_error"} & body.keys()
        assert (await client.get(f"/api/v1/ops/attempts/{id}")).status_code == 403
        assert (
            await client.get(f"/api/v1/ops/attempts/{uuid4()}", headers=HEADERS)
        ).status_code == 404
    finally:
        await owner.close()
        client._transport.app.state.control_owner = None


async def test_queue_and_feedback_discovery_preserve_independent_semantics(client, sessions):
    from career_agent.evaluation.contracts import Feedback

    authorize(client)
    subjects = [Subject(subject_id=uuid4(), task_type="greeting_generation") for _ in range(2)]
    async with sessions.begin() as session:
        for index, subject in enumerate(subjects):
            session.add(
                q.AnnotationQueueRow(
                    subject_id=subject.subject_id,
                    population="targeted" if index else "random",
                    rubric_version="quality-rubric-v1",
                    status="pending",
                )
            )
            session.add(
                q.FeedbackRow(
                    subject_id=subject.subject_id,
                    data=Feedback(
                        subject=subject, vote="thumbs_down", reason="personal_preference"
                    ).model_dump(mode="json"),
                )
            )
    queue = await client.get(
        "/api/v1/evaluation/annotations/queue?population=random&status=pending&limit=1"
    )
    assert queue.status_code == 200 and isinstance(queue.json(), list)
    assert queue.json()[0]["subject_id"] == str(subjects[0].subject_id)
    assert "criteria" not in queue.text
    feedback = await client.get(
        f"/api/v1/evaluation/feedback?subject_id={subjects[1].subject_id}", headers=HEADERS
    )
    assert feedback.json()["items"][0]["reason"] == "personal_preference"
    assert len(feedback.json()["items"]) == 1
    # Feedback is not synthesized into a Judge evaluation or ground-truth annotation.
    assert not (await client.get("/api/v1/evaluation/judges", headers=HEADERS)).json()["items"]
