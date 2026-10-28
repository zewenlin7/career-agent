import pytest
from pydantic import SecretStr

from career_agent.config import Settings
from career_agent.evaluation.contracts import EvalRunRequest, EvalSuite
from career_agent.evaluation.fixtures import initial_cases
from career_agent.evaluation.runner import EvalRunner
from career_agent.evaluation.store import put_case, put_suite

pytestmark = pytest.mark.integration


async def test_frozen_initial_suite_real_postgres_typst(sessions, migrated_url):
    cases = initial_cases()
    async with sessions.begin() as session:
        for case in cases:
            await put_case(session, case)
        await put_suite(
            session,
            EvalSuite(
                suite_id="foundation",
                version=1,
                members=[{"case_id": c.case_id, "case_version": c.case_version} for c in cases],
            ),
        )
    runner = EvalRunner(
        sessions, Settings(database_url=SecretStr(migrated_url), live_enabled=False)
    )
    run_id = await runner.create(
        EvalRunRequest(suite_id="foundation", suite_version=1, max_concurrent_trials=1)
    )
    await runner.execute(run_id)
    from sqlalchemy import select

    from career_agent.evaluation import entities as q

    async with sessions() as session:
        trials = list(await session.scalars(select(q.EvalTrialRow)))
        keys = {c.id: c.case_key for c in await session.scalars(select(q.EvalCaseRow))}
        failed = [
            (
                keys[t.case_id],
                t.status,
                (t.result or {}).get("reason_code"),
                (t.result or {}).get("output", {}).get("reason_code"),
                (t.result or {}).get("output", {}).get("status"),
                (t.result or {}).get("output", {}).get("state", {}).get("stop_reason"),
                (t.result or {}).get("output", {}).get("state", {}).get("errors"),
            )
            for t in trials
            if t.status != "completed"
        ]
        assert not failed, failed
        assert len(trials) == 40
        compiler_ops = list(
            await session.scalars(
                select(q.InvocationRow).where(
                    q.InvocationRow.data["name"].astext == "resume_compile"
                )
            )
        )
        assert compiler_ops
        from career_agent.evaluation.components import validate_task

        tailored = list(
            await session.scalars(
                select(q.InvocationRow).where(
                    q.InvocationRow.data["name"].astext == "resume_tailoring"
                )
            )
        )
        for invocation in tailored:
            data = invocation.data
            if data.get("output") and data["provenance"].get("source_snapshot", {}).get("profile"):
                validate_task(
                    data["name"],
                    data["output"],
                    data["input_snapshot"],
                    data["provenance"]["source_snapshot"],
                )
        assert any(op.data["output"]["render_status"] == "accepted" for op in compiler_ops)
        assert all(
            op.data["input_hash"] and op.data["provenance"]["resume_revision_id"]
            for op in compiler_ops
        )


async def test_frozen_regenerate_sampling_judge_feedback_and_capture(client, sessions):
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy import func, select
    from test_interview_loop import actual_session, append

    from career_agent.evaluation import entities as q
    from career_agent.evaluation.contracts import Annotation, Feedback, JudgeSamplingPolicy, Subject
    from career_agent.evaluation.judge import JudgeRunner
    from career_agent.evaluation.monitoring import (
        annotate,
        annotation_queue,
        blind_view,
        enqueue,
        record_feedback,
    )

    interview, _ = await actual_session(client)
    interview = await append(client, interview, 1)
    response = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "actual",
            "interview_id": interview["id"],
            "expected_source_revision": interview["content_revision"],
            "question_analysis": "all",
            "overall_analysis": True,
        },
    )
    assert response.status_code == 201, response.text
    original = response.json()
    assert (
        await client.post(f"/api/v1/interview-debriefs/{original['id']}/execute")
    ).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/interviews/{interview['id']}",
            json={
                "expected_revision": interview["content_revision"],
                "entries": [],
                "status": "draft",
            },
        )
    ).status_code == 200
    regenerated = await client.post(
        f"/api/v1/interview-debriefs/{original['id']}/regenerate",
        json={
            "question_analysis": "all",
            "overall_analysis": True,
        },
    )
    assert regenerated.status_code == 201, regenerated.text
    new = regenerated.json()
    assert new["id"] != original["id"] and new["snapshot"] == original["snapshot"]
    selected = (await client.get(f"/api/v1/interview-debriefs/{original['id']}")).json()
    historical = (
        await client.get(f"/api/v1/interview-debriefs/{original['id']}?historical=true")
    ).json()
    assert selected["id"] == new["id"] and historical["id"] == original["id"]
    async with sessions.begin() as session:
        assert await session.scalar(select(func.count()).select_from(q.FeedbackRow)) == 0
        invocation = await session.scalar(
            select(q.InvocationRow).where(q.InvocationRow.data["output_ref"].astext.is_not(None))
        )
        subject = Subject(
            subject_id=UUID(invocation.data["output_ref"]),
            task_type=invocation.data["name"],
            accepted_model_call_id=invocation.model_call_id,
        )
        policy = JudgeSamplingPolicy(version="test-always-v1", default_rate=Decimal(1))
        await enqueue(session, subject, policy)
        await record_feedback(session, Feedback(subject=subject, vote="thumbs_down"), policy)
        await record_feedback(session, Feedback(subject=subject, vote="thumbs_down"), policy)
        assert await session.scalar(select(func.count()).select_from(q.CaptureRow)) == 1
        assert await session.scalar(select(func.count()).select_from(q.CaptureEventRow)) == 2
        queue = await annotation_queue(session, subject, "random")
        blind = await blind_view(session, queue.id)
        assert blind["blind"] and "judge" not in blind
        for user in ["one", "two"]:
            await annotate(
                session,
                queue.id,
                Annotation(
                    subject=subject,
                    annotator=user,
                    population="random",
                    criteria=[
                        {
                            "criterion": "usefulness",
                            "rating": "pass",
                            "confidence": "high",
                            "uncertainty_reasons": [],
                            "reason": "synthetic annotation",
                            "evidence_refs": ["output"],
                        }
                    ],
                ),
            )
    result = await JudgeRunner(sessions, client._transport.app.state.settings).drain()
    assert result["results"] and all(r["status"] == "completed" for r in result["results"]), result
    async with sessions() as session:
        judges = list(await session.scalars(select(q.JudgeRow)))
        assert all(j.result is not None and j.model_call_id is not None for j in judges)
        assert await session.scalar(select(func.count()).select_from(q.AnnotationRow)) == 2


async def test_case_versions_drift_origin_and_immutable_payload(
    sessions, migrated_url, monkeypatch
):
    from sqlalchemy import select, text
    from sqlalchemy.exc import IntegrityError

    from career_agent.domain.rules import DomainError
    from career_agent.evaluation import entities as q
    from career_agent.evaluation.contracts import ComparisonPolicy, EvalLimits
    from career_agent.evaluation.execution import SharedEvalBudget
    from career_agent.evaluation.identity import candidate_config
    from career_agent.evaluation.reports import comparison

    case = initial_cases()[0]
    async with sessions.begin() as session:
        stored = await put_case(session, case)
        case_id = stored.id
        with pytest.raises(DomainError, match="immutable_case_version"):
            await put_case(session, case.model_copy(update={"tags": ["changed"]}))
        await put_suite(
            session,
            EvalSuite(
                suite_id="one", version=1, members=[{"case_id": case.case_id, "case_version": 1}]
            ),
        )
    with pytest.raises(IntegrityError, match="immutable_evaluation_payload"):
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE eval_cases SET content_hash = repeat('a', 64) WHERE id=:id"),
                {"id": case_id},
            )
    settings = Settings(database_url=SecretStr(migrated_url), live_enabled=False)
    runner = EvalRunner(sessions, settings)
    request = EvalRunRequest(suite_id="one", suite_version=1, trials=3)
    baseline = await runner.create(request)
    await runner.execute(baseline)
    candidate = await runner.create(request)
    await runner.execute(candidate)
    async with sessions.begin() as session:
        report = await comparison(session, baseline, candidate, ComparisonPolicy())
        assert report.data["gate"] == "PASS"
        assert report.data["cases"][0]["baseline_distribution"]["sample_count"] == 3
        assert report.data["cases"][0]["headline"] == "UNCHANGED"
    from uuid import UUID

    from career_agent.evaluation.contracts import Subject
    from career_agent.evaluation.judge import JudgeRunner
    from career_agent.evaluation.monitoring import request_explicit_judge

    async with sessions.begin() as session:
        invocations = list(await session.scalars(select(q.InvocationRow)))
        for invocation in invocations:
            await request_explicit_judge(
                session,
                Subject(
                    subject_id=UUID(invocation.data["output_ref"]),
                    task_type=invocation.data["name"],
                    accepted_model_call_id=invocation.model_call_id,
                    origin="evaluation",
                ),
            )
    judged = await JudgeRunner(sessions, settings).drain()
    assert all(r["status"] == "completed" for r in judged["results"]), judged
    async with sessions.begin() as session:
        quality_report = await comparison(session, baseline, candidate, ComparisonPolicy())
        assert quality_report.data["gate"] == "PASS"
        assert any(k.startswith("judge_criterion:") for k in quality_report.data["aggregate"])

    drift = await runner.create(request)
    changed = candidate_config(settings).model_copy(update={"config_hash": "changed"})
    with monkeypatch.context() as patch:
        patch.setattr("career_agent.evaluation.runner.candidate_config", lambda *args: changed)
        result = await runner.execute(drift)
        assert result["reason_code"] == "candidate_config_drift"
    async with sessions() as session:
        trials = list(
            await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == drift))
        )
        assert all(t.status == "cancelled" for t in trials)
    original = case.model_copy(update={"origin_provenance": {"provider": "unavailable"}})
    result, operations = await runner.run_case(
        original,
        request.model_copy(update={"mode": "origin_reexecution", "explicit_diagnostic": True}),
        SharedEvalBudget(EvalLimits()),
    )
    assert result.reason_code == "origin_model_unavailable" and operations == []
    with pytest.raises(DomainError, match="explicit_origin_reexecution_required"):
        await runner.create(request.model_copy(update={"mode": "origin_reexecution"}))


async def test_private_capture_explicit_sanitized_promotion(sessions):
    from uuid import uuid4

    from sqlalchemy import select, text
    from sqlalchemy.exc import IntegrityError

    from career_agent.domain.rules import DomainError
    from career_agent.evaluation import entities as q
    from career_agent.evaluation.contracts import CapturePayload, Subject
    from career_agent.evaluation.store import capture, promote, sanitize, triage

    case = initial_cases()[0]
    payload = CapturePayload(
        subject=Subject(subject_id=uuid4(), task_type="job_requirement_extraction"),
        source_snapshot={"note": "synthetic@example.invalid"},
        model_input=case.model_input,
        output={},
        provenance={"private_ref": "/private/synthetic/input.txt"},
    )
    async with sessions.begin() as session:
        row = await capture(session, payload, "manual")
        capture_id = row.id
        original_hash = row.content_hash
        await capture(
            session,
            payload.model_copy(update={"output": {"different": True}}),
            "deterministic_warning",
        )
        assert row.content_hash == original_hash and row.payload["output"] == {}
        await triage(session, row.id, "triaged", "reviewed_synthetic")
        safe = sanitize(row.payload)
        exported = case.model_copy(
            update={
                "source_type": "sanitized",
                "source_snapshot": safe["source_snapshot"],
                "model_input": safe["model_input"],
            }
        )
        with pytest.raises(DomainError, match="explicit_review_required"):
            await promote(session, row.id, exported, confirmed_repo_safe=False)
        result = await promote(session, row.id, exported, confirmed_repo_safe=True)
        assert "synthetic@example.invalid" not in str(result.data)
        assert result.data["origin_provenance"]["capture_hash"] == original_hash
    with pytest.raises(IntegrityError, match="immutable_evaluation_payload"):
        async with sessions.begin() as session:
            await session.execute(
                text(
                    "UPDATE bad_case_captures SET payload=jsonb_set(payload, '{output}', "
                    "jsonb_build_object('changed', true)) WHERE id=:id"
                ),
                {"id": capture_id},
            )
    async with sessions() as session:
        events = list(await session.scalars(select(q.CaptureEventRow)))
        assert [e.kind for e in events] == [
            "manual",
            "deterministic_warning",
            "triaged",
            "promoted",
        ]


async def test_concurrent_capture_promotion_workflow_and_agent_replay(sessions, migrated_url):
    from uuid import UUID, uuid4

    from sqlalchemy import select

    from career_agent.domain.rules import DomainError
    from career_agent.evaluation import entities as q
    from career_agent.evaluation.captured import replay_source
    from career_agent.evaluation.contracts import Subject
    from career_agent.evaluation.monitoring import payload_from_invocation
    from career_agent.evaluation.store import capture, promote, sanitize, triage

    cases = [c for c in initial_cases() if c.case_id in {"workflow.fit", "agent.fit"}]
    settings = Settings(database_url=SecretStr(migrated_url), live_enabled=False)
    runner = EvalRunner(sessions, settings)
    async with sessions.begin() as session:
        for case in cases:
            await put_case(session, case)
        await put_suite(
            session,
            EvalSuite(
                suite_id="concurrent",
                version=1,
                members=[{"case_id": c.case_id, "case_version": 1} for c in cases],
            ),
        )
    run_id = await runner.create(
        EvalRunRequest(suite_id="concurrent", suite_version=1, trials=2, max_concurrent_trials=2)
    )
    await runner.execute(run_id)
    promoted_cases = []
    async with sessions.begin() as session:
        trials = list(
            await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == run_id))
        )
        assert len(trials) == 4 and all(t.status == "completed" for t in trials), [
            (t.status, t.result.get("reason_code")) for t in trials
        ]
        invocations = list(await session.scalars(select(q.InvocationRow)))
        for task, case_key in [("fit_analysis", "workflow.fit"), ("goal_planning", "agent.fit")]:
            invocation = next(
                i for i in invocations if i.data["name"] == task and i.data.get("output_ref")
            )
            subject = Subject(
                subject_id=UUID(invocation.data["output_ref"]),
                task_type=task,
                accepted_model_call_id=invocation.model_call_id,
                operation_id=invocation.id,
            )
            payload = payload_from_invocation(subject, invocation)
            bad = payload.model_copy(
                update={"subject": subject.model_copy(update={"subject_id": uuid4()})}
            )
            with pytest.raises(DomainError, match="subject_provenance"):
                await capture(session, bad, "manual")
            row = await capture(session, payload, "manual")
            await triage(session, row.id, "triaged", "synthetic_review")
            safe = sanitize(row.payload)
            original = next(c for c in cases if c.case_id == case_key)
            promoted = original.model_copy(
                update={
                    "case_id": "captured." + case_key,
                    "source_type": "sanitized",
                    "source_snapshot": replay_source(safe["source_snapshot"]),
                    "origin_provenance": {},
                    "content_hash": None,
                }
            )
            with pytest.raises(DomainError, match="origin_identity_override"):
                await promote(
                    session,
                    row.id,
                    promoted.model_copy(update={"origin_provenance": {"model": "invented"}}),
                    confirmed_repo_safe=True,
                )
            stored = await promote(session, row.id, promoted, confirmed_repo_safe=True)
            promoted_cases.append(stored)
        await put_suite(
            session,
            EvalSuite(
                suite_id="captured",
                version=1,
                members=[{"case_id": c.case_key, "case_version": 1} for c in promoted_cases],
            ),
        )
    replay_id = await runner.create(
        EvalRunRequest(suite_id="captured", suite_version=1, max_concurrent_trials=2)
    )
    await runner.execute(replay_id)
    async with sessions() as session:
        trials = list(
            await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == replay_id))
        )
        assert all(t.status == "completed" for t in trials), [
            (t.status, t.result.get("reason_code")) for t in trials
        ]


async def test_judge_drain_uses_configured_deadline(sessions, migrated_url, monkeypatch):
    from career_agent.evaluation import judge
    from career_agent.evaluation.contracts import EvalLimits
    from career_agent.evaluation.execution import SharedEvalBudget

    configured = []

    def budget(limits, max_seconds=600):
        configured.append(max_seconds)
        return SharedEvalBudget(limits, max_seconds)

    monkeypatch.setattr(judge, "SharedEvalBudget", budget)
    runner = judge.JudgeRunner(
        sessions, Settings(database_url=SecretStr(migrated_url), live_enabled=False)
    )
    result = await runner.drain(limits=EvalLimits(max_active_seconds=0.5))
    assert configured == [0.5]
    assert result["usage"]["model_calls"] == 0


@pytest.mark.parametrize("target", ["fit_analysis", "resume_tailoring"])
async def test_frozen_dependencies_preserve_reuse_without_new_model_calls(
    sessions, migrated_url, target
):
    from uuid import UUID

    from career_agent.evaluation.captured import freeze_inputs
    from career_agent.evaluation.contracts import EvalLimits, FaultPlan
    from career_agent.evaluation.execution import SharedEvalBudget
    from career_agent.evaluation.faults import FaultController, FrozenResearch
    from career_agent.evaluation.sandbox import bootstrap, replace_refs, sandbox
    from career_agent.evaluation.store import repo_safe, sanitize
    from career_agent.models.gateway import ModelGateway
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

    case = next(c for c in initial_cases() if c.case_id == "workflow.fit").model_copy(deep=True)
    settings = Settings(database_url=SecretStr(migrated_url), live_enabled=False)
    gateway = ModelGateway(registry(settings, False), POLICY, {"fixture": FixtureTaskProvider()})
    research = FrozenResearch({}, FaultController(FaultPlan()))
    async with sandbox(settings, gateway, research) as (client, isolated_sessions):
        refs = await bootstrap(client, case.source_snapshot["bootstrap"])
        # Live is business/cache identity only: dependency injection still pins fixture adapters.
        request = replace_refs(case.source_snapshot["request"], refs)
        request.update(targets=[target], mode="live")
        response = await client.post("/api/v1/workflows/prepare_application", json=request)
        assert response.status_code == 201
        assert response.json()["state"]["status"] == "completed", response.json()["state"][
            "stop_reason"
        ]
        async with isolated_sessions() as session:
            frozen = await freeze_inputs(
                session,
                UUID(refs["$profile"]),
                UUID(refs["$job_revision"]),
                UUID(refs["$resume_revision"]),
                request,
                session.info["evaluation_data_dir"],
            )
    assert frozen["closure_complete"]
    from datetime import datetime

    case.source_type = "private_capture"
    case.evaluation_clock = datetime.fromisoformat(frozen["evaluation_clock"])
    case.source_snapshot = {"captured": frozen, "request": request}
    if target == "resume_tailoring":
        assert frozen["artifact_files"]
        assert not repo_safe(case.model_dump(mode="json"))
        assert "private_pdf_base64" not in str(sanitize(case.model_dump(mode="json")))
    result, ops = await EvalRunner(sessions, settings).run_case(
        case, EvalRunRequest(suite_id="test", suite_version=1), SharedEvalBudget(EvalLimits())
    )
    assert result.status == "completed", result.reason_code
    assert result.output["status"] == "completed", result.output.get("state", {}).get("stop_reason")
    assert result.output["model_calls"] == 0
    assert not any(op.kind == "model_task" or op.name == "resume_compile" for op in ops)


async def test_explicit_paid_gateway_boundary_with_offline_adapter(sessions, migrated_url):
    """Exercise the opt-in boundary with no network or API credentials."""
    from sqlalchemy import select

    from career_agent.evaluation import entities as q
    from career_agent.evaluation.contracts import EvalLimits
    from career_agent.models.gateway import ModelGateway
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

    settings = Settings(database_url=SecretStr(migrated_url), live_enabled=True)
    gateway = ModelGateway(registry(settings, True), POLICY, {"openai": FixtureTaskProvider()})
    case = next(c for c in initial_cases() if c.case_id == "workflow.fit")
    async with sessions.begin() as session:
        await put_case(session, case)
        await put_suite(
            session,
            EvalSuite(
                suite_id="injected",
                version=1,
                members=[{"case_id": case.case_id, "case_version": 1}],
            ),
        )
    runner = EvalRunner(sessions, settings, gateway, allow_paid_models=True)
    id = await runner.create(
        EvalRunRequest(
            suite_id="injected", suite_version=1, limits=EvalLimits(max_web_search_calls=0)
        )
    )
    await runner.execute(id)
    async with sessions() as session:
        row = await session.get(q.EvalRunRow, id)
        assert all(c["provider"] == "openai" for c in row.candidate["model_policy"]["candidates"])
        trial = await session.scalar(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == id))
        assert trial.status == "completed"
        assert trial.result["output"]["status"] == "completed"
        assert row.summary["usage"]["search_calls"] == 0
        ops = list(
            await session.scalars(
                select(q.InvocationRow).where(q.InvocationRow.trial_id == trial.id)
            )
        )
        assert ops and all(
            op.data["provenance"]["provider"] == "openai" for op in ops if op.model_call_id
        )
