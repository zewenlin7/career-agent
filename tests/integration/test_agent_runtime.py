"""All runtime acceptance uses synthetic data, fake planners/models, real PG and Typst."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_preparation import inject
from test_preparation import prep_input as preparation_fixture

from career_agent.infrastructure import entities as e
from career_agent.preparation.providers import FixtureTaskProvider

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


def payload(prep_input, targets=None, **extra):
    return {
        "goal": "分析匹配情况，修改简历并生成招呼语。",
        "bindings": prep_input,
        "authorized_scope": {
            "targets": targets or ["fit_analysis", "resume_tailoring", "greeting_generation"]
        },
        **extra,
    }


async def create(client, data):
    response = await client.post("/api/v1/agent-runs", json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def resume(client, result, **extra):
    response = await client.post(
        f"/api/v1/agent-runs/{result['run_id']}/resume",
        json={
            "expected_checkpoint_revision": result["state"]["state_revision"],
            "request_id": str(uuid4()),
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_goal_to_existing_orchestrator_outcome(client, prep_input, sessions):
    result = await create(client, payload(prep_input))
    assert result["state"]["phase"] == "completed", result
    assert result["outcome"]["status"] == "completed"
    assert result["state"]["usage"]["model_calls"] == 5
    assert result["state"]["usage"]["business_actions"] == 1
    assert result["state"]["dispatch_reservation"] is None
    async with sessions() as session:
        root = await session.get(e.AgentRun, UUID(result["run_id"]))
        assert root.status.value == "completed"
        children = list(
            await session.scalars(select(e.AgentRun).where(e.AgentRun.parent_run_id == root.id))
        )
        assert len(children) == 1 and children[0].status.value == "succeeded"
        app = await session.scalar(select(e.Application))
        assert app.status.value == "tracking"
    for value in result["outcome"]["targets"].values():
        assert (
            await client.get(f"/api/v1/preparation-artifacts/{value['artifact_id']}")
        ).status_code == 200
    observations = (await client.get(f"/api/v1/agent-runs/{result['run_id']}/observations")).json()
    assert observations[0]["observation"]["disposition"] == "executed"
    assert observations[0]["observation"]["guardrails"] == "passed"


async def test_multi_action_checkpoint_resume_and_reuse(client, prep_input):
    result = await create(
        client,
        payload(
            prep_input,
            goal="分别分析匹配，再生成招呼语。",
            authorized_scope={"targets": ["fit_analysis", "greeting_generation"]},
            action_slice=1,
        ),
    )
    assert result["state"]["phase"] == "ready", result
    assert result["state"]["usage"]["model_calls"] == 3
    assert result["state"]["progress"]["requested_targets"]["fit_analysis"]["status"] == "completed"
    continued = await resume(client, result)
    assert continued["state"]["phase"] == "completed", continued
    assert continued["state"]["usage"]["model_calls"] == 4
    assert continued["state"]["usage"]["business_actions"] == 2
    reused = await create(
        client,
        payload(
            prep_input,
            goal="分析匹配并生成招呼语。",
            authorized_scope={"targets": ["fit_analysis", "greeting_generation"]},
        ),
    )
    assert reused["state"]["phase"] == "completed", reused
    assert reused["state"]["usage"]["model_calls"] == 1  # planner only


async def test_missing_binding_wait_and_user_selection_replan(client, prep_input):
    data = payload(prep_input, targets=["greeting_generation"], goal="生成招呼语。")
    data["bindings"] = {k: v for k, v in prep_input.items() if k != "resume_revision_id"}
    result = await create(client, data)
    assert result["state"]["phase"] == "waiting_input", result
    assert result["outcome"] is None
    assert result["state"]["usage"]["model_calls"] == 1
    assert result["state"]["usage"]["business_actions"] == 0
    continued = await resume(client, result, resume_revision_id=prep_input["resume_revision_id"])
    assert continued["state"]["phase"] == "completed", continued
    assert continued["state"]["replan_count"] == 1
    plans = (await client.get(f"/api/v1/agent-runs/{result['run_id']}/plans")).json()
    assert [p["revision"] for p in plans] == [1, 2]


@pytest.mark.parametrize("corruption", ["action", "ref", "scope", "policy"])
async def test_untrusted_planner_output_rejected(client, prep_input, corruption):
    class Invalid(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if context.task_type == "goal_planning":
                if corruption == "action":
                    response.output["actions"][0]["name"] = "shell"
                elif corruption == "ref":
                    response.output["bindings"]["resume_revision_id"] = str(uuid4())
                elif corruption == "scope":
                    response.output["requested_targets"].append("interview_preparation")
                else:
                    response.output["policies"]["fit_gate"] = "gate_downstream"
            return response

    inject(client, Invalid())
    result = await create(client, payload(prep_input))
    assert result["state"]["phase"] == "failed", result
    assert result["state"]["usage"]["model_calls"] == 1
    assert result["state"]["usage"]["business_actions"] == 0


async def test_resume_compare_and_swap_idempotency(client, prep_input):
    result = await create(
        client,
        payload(
            prep_input,
            goal="分别分析匹配并生成招呼语。",
            authorized_scope={"targets": ["fit_analysis", "greeting_generation"]},
            action_slice=1,
        ),
    )
    path = f"/api/v1/agent-runs/{result['run_id']}/resume"
    body = {
        "expected_checkpoint_revision": result["state"]["state_revision"],
        "request_id": str(uuid4()),
    }
    first = await client.post(path, json=body)
    assert first.status_code == 200, first.text
    second = await client.post(path, json=body)
    assert second.status_code == 200
    assert second.json()["state"]["usage"] == first.json()["state"]["usage"]
    stale = await client.post(path, json={**body, "request_id": str(uuid4())})
    assert stale.status_code == 409


async def test_root_budget_includes_planner_and_child(client, prep_input):
    result = await create(client, payload(prep_input, limits={"max_model_calls": 2}))
    assert result["state"]["phase"] == "failed", result
    assert result["state"]["usage"]["model_calls"] == 2
    assert not any(t["status"] == "completed" for t in result["outcome"]["targets"].values())


@pytest.mark.parametrize("requested_fit", [True, False])
async def test_fit_gate_wait_requires_explicit_user_decision(client, prep_input, requested_fit):
    class Gate(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if context.task_type == "job_requirement_extraction":
                for r in response.output["requirements"]:
                    r["requirement_kind"] = "must"
            if context.task_type == "fit_analysis":
                for item in response.output["items"]:
                    item.update(status="no_evidence", fact_refs=[])
                response.output["partial_matches"] = []
                response.output["evidence_missing"] = [
                    i["requirement_ref"] for i in response.output["items"]
                ]
            return response

    inject(client, Gate())
    result = await create(
        client,
        payload(
            prep_input,
            goal="分析匹配并生成招呼语。",
            authorized_scope={
                "targets": ["fit_analysis", "greeting_generation"]
                if requested_fit
                else ["greeting_generation"],
                "fit_gate": "gate_downstream",
            },
        ),
    )
    assert result["state"]["phase"] == "waiting_decision", result
    assert result["state"]["usage"]["model_calls"] == 3
    denied = await client.post(
        f"/api/v1/agent-runs/{result['run_id']}/resume",
        json={
            "expected_checkpoint_revision": result["state"]["state_revision"],
            "request_id": str(uuid4()),
        },
    )
    assert denied.status_code == 409
    result = await resume(client, result, decision="continue")
    assert result["state"]["phase"] == "completed", result
    assert result["state"]["usage"]["model_calls"] == 5


async def test_explicit_interview_dependency(client, prep_input):
    result = await create(
        client,
        payload(
            prep_input,
            goal="修改简历并准备面试。",
            authorized_scope={"targets": ["resume_tailoring", "interview_preparation"]},
        ),
    )
    assert result["state"]["phase"] == "completed", result
    assert result["state"]["usage"]["business_actions"] == 2
    assert set(result["outcome"]["targets"]) == {"resume_tailoring", "interview_preparation"}


async def test_runtime_real_overflow_fake_compression(client, prep_input):
    class Overflow(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if context.task_type == "resume_tailoring":
                response.output["sections"][0]["items"][0].update(
                    text=("使\n用\nPython\n和\nFastAPI\n构\n建\n模\n拟\n服\n务。\n" * 5).strip(),
                    short_text=None,
                    required=True,
                )
            if context.task_type == "resume_compression":
                response.output["sections"][0]["items"][0]["text"] = (
                    "使用 Python 和 FastAPI 构建模拟服务。"
                )
            return response

    inject(client, Overflow())
    result = await create(
        client, payload(prep_input, targets=["resume_tailoring"], goal="修改简历。")
    )
    assert result["state"]["phase"] == "completed", result
    assert result["state"]["usage"]["semantic_compressions"] == 1
    assert result["state"]["usage"]["tool_calls"] == 2


async def test_resume_revalidates_verified_fact_snapshot(client, prep_input, sessions):
    result = await create(
        client,
        payload(
            prep_input,
            goal="分别分析匹配并生成招呼语。",
            authorized_scope={"targets": ["fit_analysis", "greeting_generation"]},
            action_slice=1,
        ),
    )
    fact_id = next(iter(result["state"]["fact_snapshot"]))
    async with sessions.begin() as session:
        fact = await session.get(e.PersonalFact, UUID(fact_id))
        from career_agent.domain.rules import FactStatus

        fact.status = FactStatus.REJECTED
    resumed = await resume(client, result)
    assert resumed["state"]["phase"] == "waiting_input"
    assert resumed["state"]["usage"]["model_calls"] == result["state"]["usage"]["model_calls"]


@pytest.mark.parametrize(
    "limits,reason",
    [
        ({"max_total_business_actions": 0}, "action_budget_exhausted"),
        ({"max_steps": 1}, "step_budget_exhausted"),
    ],
)
async def test_dispatch_limits(client, prep_input, limits, reason):
    result = await create(client, payload(prep_input, limits=limits))
    assert result["state"]["phase"] == "failed"
    assert result["state"]["pending_reason"] == reason
    assert result["state"]["usage"]["model_calls"] == 1


async def test_model_success_business_guardrail_failure_and_private_trace(
    client, prep_input, sessions
):
    class InvalidFact(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if context.task_type == "greeting_generation":
                response.output["fact_refs"] = [str(uuid4())]
            return response

    inject(client, InvalidFact())
    goal = "生成招呼语。synthetic-private-goal-marker"
    result = await create(client, payload(prep_input, targets=["greeting_generation"], goal=goal))
    assert result["state"]["phase"] == "failed", result
    observations = (await client.get(f"/api/v1/agent-runs/{result['run_id']}/observations")).json()
    assert observations[0]["observation"]["disposition"] == "failed"
    async with sessions() as session:
        models = list(
            await session.scalars(
                select(e.ModelCall).where(e.ModelCall.task_type == "greeting_generation")
            )
        )
        assert models[0].status.value == "succeeded"
        checkpoints = list(await session.scalars(select(e.AgentCheckpoint)))
        assert all(goal not in str(row.state) for row in checkpoints)
        steps = list(await session.scalars(select(e.AgentStep)))
        assert all(goal not in str(row.versions) for row in steps)
    assert goal not in str(result)


async def test_resume_detects_corrupt_completed_pdf(client, prep_input, sessions):
    result = await create(
        client,
        payload(
            prep_input,
            goal="分别修改简历并生成招呼语。",
            authorized_scope={"targets": ["resume_tailoring", "greeting_generation"]},
            action_slice=1,
        ),
    )
    assert (
        result["state"]["progress"]["requested_targets"]["resume_tailoring"]["status"]
        == "completed"
    )
    async with sessions() as session:
        report = await session.scalar(
            select(e.RenderArtifact).where(
                e.RenderArtifact.report["render_status"].astext == "accepted"
            )
        )
        ref = report.artifact_ref
    path = client._transport.app.state.settings.data_dir / "artifacts" / f"{ref}.pdf"
    original = path.read_bytes()
    path.write_bytes(b"synthetic corruption")
    resumed = await resume(client, result)
    assert resumed["state"]["phase"] == "waiting_input"
    assert resumed["state"]["pending_reason"] == "pdf_invalid"
    assert resumed["state"]["usage"]["model_calls"] == result["state"]["usage"]["model_calls"]
    path.write_bytes(original)
    continued = await resume(client, resumed)
    assert continued["state"]["phase"] == "completed", continued
    assert continued["state"]["usage"]["model_calls"] == result["state"]["usage"]["model_calls"] + 1
    assert continued["state"]["replan_count"] == 0


async def test_planner_context_cap_prevents_call(client, prep_input):
    result = await create(client, payload(prep_input, goal="合成目标" * 950))
    assert result["state"]["pending_reason"] == "planner_context_too_large", result
    assert result["state"]["usage"]["model_calls"] == 0


async def test_replan_limit_preserves_usage(client, prep_input):
    data = payload(
        prep_input, targets=["greeting_generation"], goal="生成招呼语。", limits={"max_replans": 0}
    )
    data["bindings"] = {k: v for k, v in prep_input.items() if k != "resume_revision_id"}
    result = await create(client, data)
    result = await resume(client, result, resume_revision_id=prep_input["resume_revision_id"])
    assert result["state"]["phase"] == "failed"
    assert result["state"]["pending_reason"] == "replan_budget_exhausted"
    assert result["state"]["usage"]["model_calls"] == 1


async def test_no_progress_ignores_cosmetic_plan_changes(client, prep_input):
    class Waiting(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            result = await super().generate(candidate, context, task)
            if context.task_type in {"goal_planning", "goal_replanning"}:
                result.output["actions"] = []
                result.output["missing_inputs"] = ["goal_clarification_required"]
                result.output["reason_code"] = (
                    "input_required" if context.task_type == "goal_planning" else "goal_routed"
                )
            return result

    inject(client, Waiting())
    result = await create(client, payload(prep_input, targets=["fit_analysis"], goal="分析匹配。"))
    assert result["state"]["phase"] == "waiting_input"
    result = await resume(client, result, authorized_targets=["fit_analysis"])
    assert result["state"]["pending_reason"] == "no_progress", result
    assert result["state"]["usage"]["model_calls"] == 2
    assert result["state"]["usage"]["business_actions"] == 0


async def test_legal_replan_removes_failed_dependency_without_retry(client, prep_input):
    calls = []

    class Alternate(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            calls.append(context.task_type)
            response = await super().generate(candidate, context, task)
            if context.task_type == "goal_planning":
                actions = response.output["actions"]
                actions[1]["dependencies"] = [actions[0]["action_id"]]
            if context.task_type == "fit_analysis":
                response.output["items"][0]["fact_refs"] = [str(uuid4())]
            return response

    inject(client, Alternate())
    result = await create(
        client,
        payload(
            prep_input,
            goal="分别分析匹配并生成招呼语。",
            authorized_scope={"targets": ["fit_analysis", "greeting_generation"]},
        ),
    )
    assert result["state"]["phase"] == "partial", result
    assert result["state"]["replan_count"] == 1
    assert calls.count("fit_analysis") == 1
    assert calls.count("goal_replanning") == 1
    assert calls.count("greeting_generation") == 1
    assert result["outcome"]["targets"]["greeting_generation"]["status"] == "completed"
    assert result["outcome"]["targets"]["fit_analysis"]["status"] == "failed"


async def test_resume_rejects_scope_and_binding_changes(client, prep_input):
    data = payload(prep_input, targets=["greeting_generation"], goal="生成招呼语。")
    data["bindings"] = {k: v for k, v in prep_input.items() if k != "resume_revision_id"}
    result = await create(client, data)
    path = f"/api/v1/agent-runs/{result['run_id']}/resume"
    response = await client.post(
        path,
        json={
            "expected_checkpoint_revision": result["state"]["state_revision"],
            "request_id": str(uuid4()),
            "authorized_targets": ["interview_preparation"],
        },
    )
    assert response.status_code == 409
    cancelled = await resume(client, result, decision="cancel")
    assert cancelled["state"]["phase"] == "cancelled"
    assert cancelled["state"]["usage"]["model_calls"] == 1


async def test_child_retry_consumes_root_budget_without_replan(client, prep_input):
    from career_agent.models.contracts import ModelGatewayError

    class Retry(FixtureTaskProvider):
        attempts = 0

        async def generate(self, candidate, context, task):
            if context.task_type == "greeting_generation":
                self.attempts += 1
                if self.attempts == 1:
                    raise ModelGatewayError("provider_timeout", retryable=True)
            return await super().generate(candidate, context, task)

    inject(client, Retry())
    result = await create(
        client, payload(prep_input, targets=["greeting_generation"], goal="生成招呼语。")
    )
    assert result["state"]["phase"] == "completed", result
    assert result["state"]["usage"]["model_calls"] == 4
    assert result["state"]["usage"]["unknown_usage_attempts"] == 1
    assert result["state"]["usage"]["reserved_input_tokens"] > 0
    assert result["state"]["usage"]["actual_billed_cost_usd"] is None
    assert result["state"]["replan_count"] == 0


@pytest.mark.parametrize("invalid_kind", ["cross_profile", "missing"])
async def test_rejected_resume_binding_does_not_poison_confirmed_state(
    client, prep_input, sessions, invalid_kind
):
    data = payload(
        prep_input,
        targets=["fit_analysis", "greeting_generation"],
        goal="生成招呼语。",
    )
    data["bindings"] = {k: v for k, v in prep_input.items() if k != "resume_revision_id"}
    waiting = await create(client, data)
    assert waiting["state"]["phase"] == "waiting_input"
    invalid_id = str(uuid4())
    if invalid_kind == "cross_profile":
        profile = (await client.get("/api/v1/profile")).json()
        response = await client.put(
            "/api/v1/profile",
            json={"expected_revision": profile["revision"], "data": profile["data"]},
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        async with sessions() as session:
            base = await session.get(
                e.ResumeVariantRevision, UUID(prep_input["resume_revision_id"])
            )
            document = dict(base.document)
        document.update(profile_id=updated["id"], profile_revision=updated["revision"])
        response = await client.post("/api/v1/resume-variants", json=document)
        assert response.status_code == 201, response.text
        invalid_id = response.json()["resume_revision_id"]

    rejected = await resume(
        client, waiting, resume_revision_id=invalid_id, authorized_targets=["greeting_generation"]
    )
    assert rejected["state"]["phase"] == "waiting_input"
    assert rejected["state"]["pending_reason"] in {"context_revision_mismatch", "not_found"}
    confirmed_fields = (
        "bindings",
        "scope",
        "original_scope",
        "gate_approved",
        "needs_plan",
        "progress",
        "fact_snapshot",
        "usage",
        "plan_revision",
        "replan_count",
    )
    for field in confirmed_fields:
        assert rejected["state"][field] == waiting["state"][field], field
    persisted = (await client.get(f"/api/v1/agent-runs/{waiting['run_id']}")).json()
    assert persisted["state"] == rejected["state"]

    continued = await resume(client, rejected, resume_revision_id=prep_input["resume_revision_id"])
    assert continued["state"]["phase"] == "completed", continued
    assert continued["state"]["bindings"]["resume_revision_id"] == prep_input["resume_revision_id"]
    assert continued["state"]["plan_revision"] == 2
    assert continued["state"]["replan_count"] == 1


async def test_rejected_gate_approval_remains_pending_until_context_is_valid(
    client, prep_input, monkeypatch
):
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.runtime.engine import AgentEngine

    class Gate(FixtureTaskProvider):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if context.task_type == "fit_analysis":
                for item in response.output["items"]:
                    item.update(status="no_evidence", fact_refs=[])
                response.output["partial_matches"] = []
                response.output["evidence_missing"] = [
                    item["requirement_ref"] for item in response.output["items"]
                ]
            return response

    inject(client, Gate())
    waiting = await create(
        client,
        payload(
            prep_input,
            goal="分析匹配并生成招呼语。",
            authorized_scope={
                "targets": ["fit_analysis", "greeting_generation"],
                "fit_gate": "gate_downstream",
            },
        ),
    )
    assert waiting["state"]["phase"] == "waiting_decision"
    assert waiting["state"]["usage"]["model_calls"] == 3
    original_validate = AgentEngine.validate_context

    async def unavailable_context(self, session, state):
        await original_validate(self, session, state)
        # Simulate a transient context/artifact failure after candidate validation has begun.
        raise ModelGatewayError("pdf_invalid")

    with monkeypatch.context() as patch:
        patch.setattr(AgentEngine, "validate_context", unavailable_context)
        rejected = await resume(client, waiting, decision="continue")

    assert rejected["state"]["phase"] == "waiting_decision"
    assert rejected["state"]["pending_reason"] == "pdf_invalid"
    for field in (
        "bindings",
        "scope",
        "gate_approved",
        "needs_plan",
        "progress",
        "usage",
        "fact_snapshot",
        "plan_revision",
        "replan_count",
    ):
        assert rejected["state"][field] == waiting["state"][field], field
    persisted = (await client.get(f"/api/v1/agent-runs/{waiting['run_id']}")).json()
    assert persisted["state"] == rejected["state"]
    denied = await client.post(
        f"/api/v1/agent-runs/{waiting['run_id']}/resume",
        json={
            "expected_checkpoint_revision": rejected["state"]["state_revision"],
            "request_id": str(uuid4()),
        },
    )
    assert denied.status_code == 409
    continued = await resume(client, rejected, decision="continue")
    assert continued["state"]["phase"] == "completed", continued
    assert continued["state"]["gate_approved"] is True
    assert continued["state"]["plan_revision"] == 2
    assert continued["state"]["replan_count"] == 1
    assert continued["state"]["usage"]["model_calls"] == 5
    assert continued["outcome"]["targets"]["greeting_generation"]["status"] == "completed"
