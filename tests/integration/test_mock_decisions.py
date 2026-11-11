"""Model decisions pass through the real Gateway, validators, transactions and receipts."""

from uuid import uuid4

import pytest
from test_preparation import inject
from test_preparation import prep_input as preparation_fixture

from career_agent.preparation.providers import FixtureTaskProvider

prep_input = preparation_fixture
pytestmark = pytest.mark.integration


class Decisions(FixtureTaskProvider):
    def __init__(self, choices):
        self.choices = iter(choices)
        self.requests = []

    async def generate(self, candidate, context, task):
        response = await super().generate(candidate, context, task)
        if context.task_type != "mock_interview_turn_generation":
            return response
        self.requests.append((context, task))
        choice = next(self.choices)
        if choice == "finish":
            value = {"action": "finish", "turn": None}
        else:
            policy = task.inputs["policy"]
            turn = {
                "kind": choice,
                "question": "请说明这项设计如何验证。",
                "question_type": "technical",
                "primary_entry_id": policy.get("current_primary_id", policy.get("parent"))
                if choice == "follow_up"
                else None,
                "requirement_refs": [],
                "fact_refs": [],
                "reason_code": "clarify_answer" if choice == "follow_up" else "next_primary",
            }
            value = {"action": "ask", "turn": turn}
            if context.output_schema_version.endswith("-v2"):
                value = turn
        response.output = value
        return response


async def call(client, row, name, **extra):
    response = await client.post(
        f"/api/v1/mock-interviews/{row['id']}/{name}",
        json={
            "expected_revision": row["revision"],
            "request_id": str(uuid4()),
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_model_can_skip_followup_after_first_primary(client, prep_input):
    provider = Decisions(["primary", "primary"])
    inject(client, provider)
    response = await client.post("/api/v1/mock-interviews", json={"context": prep_input})
    assert response.status_code == 201
    row = await call(client, response.json(), "generate")
    row = await call(
        client,
        row,
        "answers",
        pending_question_id=row["pending_question_id"],
        answer="已说明验证过程。",
    )
    assert row["status"] == "waiting_answer", row["stop_reason"]
    assert [t["question"]["kind"] for t in row["turns"]] == ["primary", "primary"]
    assert row["followup_count"] == 0


MODES = [("quick", 3, 1), ("standard", 5, 3), ("long", 8, 5), ("custom", 4, 3), ("custom", 2, 0)]


@pytest.mark.parametrize("mode,primary,followup", MODES)
@pytest.mark.parametrize("scenario", ["skip", "delayed", "last_group"])
async def test_dynamic_choices_all_modes(client, prep_input, mode, primary, followup, scenario):
    if scenario == "skip":
        choices = ["primary"] * primary
        used = 0
    elif scenario == "delayed":
        used = min(2, followup)
        choices = ["primary", "primary"] + ["follow_up"] * used + ["primary"] * (primary - 2)
    else:
        used = min(1, followup)
        choices = ["primary"] * primary + ["follow_up"] * used
    if followup > used:
        choices += ["finish"]
    provider = Decisions(choices)
    inject(client, provider)
    policy = {"mode": mode, "primary_target": primary, "followup_max": followup}
    row = (
        await client.post("/api/v1/mock-interviews", json={"context": prep_input, "policy": policy})
    ).json()
    row = await call(client, row, "generate")
    for _ in range(primary + used):
        row = await call(
            client,
            row,
            "answers",
            pending_question_id=row["pending_question_id"],
            answer="通过事务与重复请求测试验证。",
        )
    assert row["status"] == "completed", row
    assert row["completion_type"] == "target_reached"
    assert row["primary_question_count"] == primary
    assert row["followup_count"] == used
    assert len(row["turns"]) == primary + used
    assert len(provider.requests) == len(choices)
    parent = None
    for turn in row["turns"]:
        if turn["question"]["kind"] == "primary":
            parent = turn["id"]
        else:
            assert turn["question"]["primary_entry_id"] == parent
    if scenario == "delayed" and used:
        assert row["turns"][2]["question_number"] == "2.1"
        if used > 1:
            assert row["turns"][3]["question_number"] == "2.2"
    for _, task in provider.requests:
        p = task.inputs["policy"]
        assert p["all_answered"]
        if p["remaining_followup"] == 0:
            assert task.instruction.endswith(
                "本次追问额度已用尽，禁止生成任何追问；仍有主问题则继续主问题，否则结束。"
            )
            assert "ask_follow_up" not in p["legal_actions"]
        else:
            assert task.instruction.endswith("根据回答判断必要性，不要求使用全部追问额度。")
        group = task.inputs["current_group"]["entries"]
        if group:
            assert p["current_question_id"] == group[-1]["entry_id"]
            assert group[-1]["answer"]
        assert not set(t["entry_id"] for t in group) & set(
            t["entry_id"] for t in task.inputs["question_history"]
        )
    status = (
        await client.get(
            f"/api/v1/task-status/mock-interviews/{row['id']}?request_id={row['latest_request_id']}"
        )
    ).json()
    assert status["state"] == "success"
    assert status["decision"]["action"] == "finish"
    assert "question" not in status["selection"]


@pytest.mark.parametrize(
    "bad", ["early_finish", "first_followup", "unknown_kind", "missing_question", "wrong_parent"]
)
async def test_illegal_decisions_never_consume_question_quota(client, prep_input, bad):
    class Bad(Decisions):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if bad == "early_finish":
                response.output = {"action": "finish", "turn": None}
            else:
                turn = response.output["turn"]
                if bad == "first_followup":
                    turn["kind"], turn["reason_code"] = "follow_up", "clarify_answer"
                elif bad == "unknown_kind":
                    turn["kind"] = "invented"
                elif bad == "missing_question":
                    turn.pop("question")
                else:
                    turn["primary_entry_id"] = str(uuid4())
            return response

    provider = Bad(["primary"] * 10)
    inject(client, provider)
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    row = await call(client, row, "generate")
    assert row["status"] == "ready_to_generate" and row["stop_reason"]
    assert row["turns"] == []
    assert row["primary_question_count"] == row["followup_count"] == 0
    assert row["usage"]["model_calls"] >= 1


@pytest.mark.parametrize("mode,primary,followup", MODES)
async def test_spent_allowance_is_a_hard_rejection(client, prep_input, mode, primary, followup):
    provider = Decisions(["primary"] + ["follow_up"] * (followup + 1))
    inject(client, provider)
    row = (
        await client.post(
            "/api/v1/mock-interviews",
            json={
                "context": prep_input,
                "policy": {"mode": mode, "primary_target": primary, "followup_max": followup},
            },
        )
    ).json()
    row = await call(client, row, "generate")
    for _ in range(followup + 1):
        row = await call(
            client,
            row,
            "answers",
            pending_question_id=row["pending_question_id"],
            answer="合成回答。",
        )
    assert row["stop_reason"] == "illegal_question_kind"
    assert row["followup_count"] == followup and row["primary_question_count"] == 1
    assert all(t["answer"] is not None for t in row["turns"])
    assert provider.requests[-1][1].inputs["policy"]["remaining_followup"] == 0


async def test_finish_save_failure_recovers_exact_decision_without_new_call(
    client, prep_input, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    from career_agent.evaluation import recording

    provider = Decisions(["primary", "finish"])
    inject(client, provider)
    row = (
        await client.post(
            "/api/v1/mock-interviews",
            json={
                "context": prep_input,
                "policy": {"mode": "custom", "primary_target": 1, "followup_max": 1},
            },
        )
    ).json()
    row = await call(client, row, "generate")
    original = recording.bind_artifact

    async def fail(*args, **kwargs):
        raise OperationalError("synthetic finish persistence failure", {}, None)

    monkeypatch.setattr(recording, "bind_artifact", fail)
    row = await call(
        client,
        row,
        "answers",
        pending_question_id=row["pending_question_id"],
        answer="最后一题已保存。",
    )
    assert row["stop_reason"] == "artifact_save_failed"
    failed_request = row["latest_request_id"]
    assert len(row["turns"]) == 1 and row["turns"][0]["answer"]
    monkeypatch.setattr(recording, "bind_artifact", original)
    row = await call(client, row, "recover")
    assert row["status"] == "completed" and row["pending_question_id"] is None
    assert len(row["turns"]) == 1 and len(provider.requests) == 2
    status = (
        await client.get(
            f"/api/v1/task-status/mock-interviews/{row['id']}?request_id={failed_request}"
        )
    ).json()
    assert status["state"] == "success" and status["decision"]["action"] == "finish"
    assert status["selection"] == {"session": row["id"]}


async def test_cannot_ask_extra_primary_or_attach_followup_to_previous_group(client, prep_input):
    class WrongParent(Decisions):
        async def generate(self, candidate, context, task):
            response = await super().generate(candidate, context, task)
            if response.output.get("turn", {}).get("kind") == "follow_up":
                response.output["turn"]["primary_entry_id"] = task.inputs["question_history"][0][
                    "entry_id"
                ]
            return response

    provider = WrongParent(["primary", "primary", "follow_up"])
    inject(client, provider)
    row = (await client.post("/api/v1/mock-interviews", json={"context": prep_input})).json()
    row = await call(client, row, "generate")
    for _ in range(2):
        row = await call(
            client,
            row,
            "answers",
            pending_question_id=row["pending_question_id"],
            answer="合成回答。",
        )
    assert row["stop_reason"] == "illegal_question_kind" and len(row["turns"]) == 2
    provider = Decisions(["primary", "primary"])
    inject(client, provider)
    row = (
        await client.post(
            "/api/v1/mock-interviews",
            json={
                "context": prep_input,
                "policy": {"mode": "custom", "primary_target": 1, "followup_max": 1},
            },
        )
    ).json()
    row = await call(client, row, "generate")
    row = await call(
        client, row, "answers", pending_question_id=row["pending_question_id"], answer="合成回答。"
    )
    assert row["stop_reason"] == "illegal_question_kind" and len(row["turns"]) == 1


async def test_finish_concurrency_and_replayed_response_do_not_redispatch(client, prep_input):
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(Decisions):
        async def generate(self, candidate, context, task):
            result = await super().generate(candidate, context, task)
            if result.output.get("action") == "finish":
                entered.set()
                await release.wait()
            return result

    provider = Delayed(["primary", "finish"])
    inject(client, provider)
    row = (
        await client.post(
            "/api/v1/mock-interviews",
            json={
                "context": prep_input,
                "policy": {"mode": "custom", "primary_target": 1, "followup_max": 1},
            },
        )
    ).json()
    row = await call(client, row, "generate")
    payload = {
        "expected_revision": row["revision"],
        "request_id": str(uuid4()),
        "pending_question_id": row["pending_question_id"],
        "answer": "已持久化回答。",
    }
    path = f"/api/v1/mock-interviews/{row['id']}/answers"
    first = asyncio.create_task(client.post(path, json=payload))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        concurrent = await client.post(path, json=payload)
        assert concurrent.status_code == 409
    finally:
        release.set()
    result = await first
    assert result.status_code == 200 and result.json()["status"] == "completed"
    assert (await client.post(path, json=payload)).json() == result.json()
    assert len(result.json()["turns"]) == 1 and len(provider.requests) == 2
