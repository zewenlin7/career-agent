"""Legacy accepted outputs remain recoverable across the spoken-question contract change."""

from contextlib import asynccontextmanager
from dataclasses import fields
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from test_preparation import inject
from test_preparation import prep_input as preparation_fixture

from career_agent.evaluation import recording
from career_agent.interview.contracts import LegacyTurnOutput, TurnOutput
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.gateway import ModelGateway
from career_agent.models.inputs import InputContract
from career_agent.models.prompts import PromptRegistry, PromptSpec, application_prompts
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.preparation.research import FixtureResearchAdapter

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("failure_mode", ["save", "known", "unknown", "unsettled"])
async def test_legacy_output_recovery_then_decision_and_debrief(
    client, prep_input, monkeypatch, version, failure_mode, sessions
):
    class Provider(FixtureTaskProvider):
        inputs = []
        legacy = True

        async def generate(self, candidate, context, task):
            self.inputs.append(task.inputs)
            if self.legacy and len(self.inputs) == 2 and failure_mode != "save":
                raise ModelGatewayError(
                    "provider_timeout"
                    if failure_mode in {"known", "unsettled"}
                    else "recovery_decision_required"
                )
            result = await super().generate(candidate, context, task)
            if (
                self.legacy
                and version == 1
                and context.task_type == "mock_interview_turn_generation"
            ):
                result.output["topic"] = "旧考点标题"
            return result

    provider = Provider()
    specs = application_prompts().specs
    old_fields = {
        f.name: getattr(specs["mock_interview_turn_generation"], f.name) for f in fields(PromptSpec)
    }
    blocks = ["stable_context", "question_history", "current_question", "current_answer", "policy"]
    old_fields.update(
        executable_input=InputContract(
            required={
                "stable_context": ["object"],
                "question_history": ["array"],
                "current_question": ["object", "null"],
                "current_answer": ["string", "null"],
                "policy": ["object"],
            },
            optional={"repair_reason": ["string"]},
            max_bytes=300000,
        ),
        input_contract={"ordered_blocks": blocks},
        prompt_version=f"mock_interview_turn_generation_v{version + 4}",
        input_schema_version=f"mock_interview_turn_generation-input-v{version + 3}",
        output_schema_version=f"mock_interview_turn_generation-output-v{version}",
        output_schema=LegacyTurnOutput if version == 1 else TurnOutput,
        instruction="Ask exactly one question of requested next_kind. Never end the session. "
        "Follow-ups must use the supplied current primary ID; "
        "primary has null parent. No grading.",
    )

    specs["mock_interview_turn_generation"] = PromptSpec(**old_fields)

    @asynccontextmanager
    async def legacy_dependencies(settings, mode):
        yield (
            ModelGateway(
                registry(settings, False),
                POLICY,
                {"fixture": provider},
                prompts=PromptRegistry(list(specs.values())),
            ),
            FixtureResearchAdapter(),
        )

    client._transport.app.state.preparation_dependencies = legacy_dependencies
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    path = f"/api/v1/mock-interviews/{row['id']}"

    async def action(name, **extra):
        response = await client.post(
            path + "/" + name,
            json={
                "expected_revision": row["revision"],
                "request_id": str(uuid4()),
                **extra,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    row = await action("generate")
    assert ("topic" in row["turns"][0]["question"]) == (version == 1)
    frozen = row["context"]
    first = row["turns"][0]["id"]
    original_bind = recording.bind_artifact

    async def fail_save(*args, **kwargs):
        raise OperationalError("synthetic persistence fault", {}, None)

    if failure_mode == "save":
        monkeypatch.setattr(recording, "bind_artifact", fail_save)
    row = await action("answers", pending_question_id=first, answer="合成的已保存回答。")
    assert (
        row["stop_reason"]
        == {
            "save": "artifact_save_failed",
            "known": "provider_timeout",
            "unknown": "recovery_decision_required",
            "unsettled": "provider_timeout",
        }[failure_mode]
    ), row
    assert row["turns"][0]["answer"] == "合成的已保存回答。"
    assert ("topic" in provider.inputs[-1]["question_history"][0]) == (version == 1)
    assert len(provider.inputs) == 2

    if failure_mode == "unsettled":
        # Simulate an incomplete legacy call journal. The receipt alone must not authorize
        # changing contracts or dispatching a replacement decision.
        from sqlalchemy import select

        from career_agent.domain.rules import CallStatus
        from career_agent.infrastructure import entities as e

        async with sessions.begin() as session:
            call = (
                await session.scalars(
                    select(e.ModelCall).where(
                        e.ModelCall.task_type == "mock_interview_turn_generation",
                        e.ModelCall.error_code == "provider_timeout",
                    )
                )
            ).one()
            call.status, call.error_code = CallStatus.RUNNING, None

    # Switch deployment without substituting the frozen source or an accepted old output.
    monkeypatch.setattr(recording, "bind_artifact", original_bind)
    provider.legacy = False
    inject(client, provider)
    if failure_mode in {"unknown", "unsettled"}:
        for operation in ("recover", "generate"):
            response = await client.post(
                path + "/" + operation,
                json={
                    "expected_revision": row["revision"],
                    "request_id": str(uuid4()),
                },
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "execution_outcome_unknown"
        assert len(provider.inputs) == 2
        assert (await client.get(path)).json() == row
        return
    row = await action("recover" if failure_mode == "save" else "generate")
    assert row["status"] == "waiting_answer", row
    assert row["context"] == frozen
    assert ("topic" in row["turns"][1]["question"]) == (version == 1 and failure_mode == "save")
    assert row["turns"][1]["question"]["primary_entry_id"] == first
    expected_calls = 2 if failure_mode == "save" else 3
    assert len(provider.inputs) == expected_calls
    if failure_mode == "known":
        calls = (await client.get(f"/api/v1/runs/{row['run_id']}/calls")).json()["model_calls"]
        failed = next(c for c in calls if c["error_code"] == "provider_timeout")
        assert failed["logical_operation_id"] != row["turns"][1]["logical_operation_id"]
    assert row["primary_question_count"] == 1 and row["followup_count"] == 1
    row = await action(
        "answers", pending_question_id=row["pending_question_id"], answer="追问回答。"
    )
    assert len(provider.inputs) == expected_calls + 1
    assert all("topic" not in turn for turn in provider.inputs[-1]["question_history"])
    assert "topic" not in row["turns"][-1]["question"]
    assert (await client.get(path)).json() == row
    row = await action("end")
    response = await client.post(
        "/api/v1/interview-debriefs",
        json={
            "source_kind": "mock",
            "interview_id": row["id"],
            "expected_source_revision": row["revision"],
            "overall_analysis": True,
        },
    )
    assert response.status_code == 201, response.text
    debrief = response.json()
    snapshot = debrief["snapshot"]
    assert "旧考点标题" not in str(snapshot)
    assert "合成的已保存回答。" in str(snapshot)
    executed = await client.post(f"/api/v1/interview-debriefs/{debrief['id']}/execute")
    assert "run_completed" in executed.text, executed.text
    reread = (await client.get(f"/api/v1/interview-debriefs/{debrief['id']}")).json()
    assert reread["status"] == "completed"
    assert reread["snapshot"] == snapshot
    assert reread["source_hash"] == debrief["source_hash"]
