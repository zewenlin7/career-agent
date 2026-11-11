"""Instruction contracts, not evidence of a real model's decision quality."""

import json
from pathlib import Path

import pytest
from input_fixtures import valid_inputs

from career_agent.models.prompts import application_prompts


def test_mock_has_no_debrief_task_instructions():
    spec = application_prompts().resolve("mock_interview_turn_generation")
    instruction = spec.task(valid_inputs(spec)).instruction
    for phrase in (
        "Findings must cite",
        "return empty findings",
        "personal example answers",
        "Knowledge candidates",
        "Do not copy source questions/answers into evaluations",
    ):
        assert phrase not in instruction


@pytest.mark.parametrize(
    "principle",
    [
        "重要遗漏、歧义、矛盾",
        "追问价值高于进入下一主问题",
        "简短但准确",
        "不能仅因回答短",
        "原问题未要求",
        "新增验证价值",
        "剩余面试覆盖面",
    ],
)
def test_final_mock_instruction_contains_substantive_decision_standards(principle):
    spec = application_prompts().resolve("mock_interview_turn_generation")
    assert principle in spec.task(valid_inputs(spec)).instruction


def test_other_prompt_consumers_keep_exact_identity():
    before = json.loads((Path(__file__).parents[1] / "fixtures/mock_prompt_v7.json").read_text())
    specs = application_prompts().specs
    unaffected = {
        name: value
        for name, value in before["other_prompt_hashes"].items()
        if name != "interview_overall_debrief"
    }
    assert {name: specs[name].prompt_hash for name in unaffected} == unaffected
    overall = specs["interview_overall_debrief"]
    assert overall.prompt_version == "interview_overall_debrief_v6"
    assert overall.prompt_hash != before["other_prompt_hashes"]["interview_overall_debrief"]


def test_prompt_only_upgrade_changes_execution_identity_not_schemas():
    from dataclasses import replace

    from career_agent.application.compatibility import model_execution_versions
    from career_agent.models.contracts import ModelGatewayError, ModelRequestContext

    before = json.loads((Path(__file__).parents[1] / "fixtures/mock_prompt_v7.json").read_text())
    prompts = application_prompts()
    current = prompts.resolve("mock_interview_turn_generation")
    legacy = replace(
        current,
        instruction=before["mock_instruction"],
        prompt_version="mock_interview_turn_generation_v7",
    )
    assert legacy.metadata == before["mock_metadata"]
    assert current.prompt_version == "mock_interview_turn_generation_v8"
    assert current.prompt_hash != legacy.prompt_hash
    assert current.input_schema_version == legacy.input_schema_version
    assert current.output_schema_version == legacy.output_schema_version
    versions = model_execution_versions(current.task_type)
    assert versions["prompt_hash"] == current.prompt_hash
    assert versions["prompt_version"] == current.prompt_version
    context = ModelRequestContext(
        task_type=current.task_type, output_schema=current.output_schema, **legacy.metadata
    )
    with pytest.raises(ModelGatewayError, match="prompt_contract_mismatch"):
        prompts.trace_metadata(context, legacy.task(valid_inputs(legacy)))


@pytest.mark.parametrize(
    "mode,primary,followup",
    [
        ("quick", 3, 1),
        ("standard", 5, 3),
        ("long", 8, 5),
        ("custom", 4, 3),
        ("custom", 2, 0),
    ],
)
@pytest.mark.parametrize("stage", ["initial", "answered", "last_answered"])
def test_quality_standards_and_dynamic_tail_through_production_builder(
    mode, primary, followup, stage
):
    import copy
    from uuid import UUID

    from career_agent.evaluation.mock_quality import fixture_inputs, quality_cases
    from career_agent.interview.contracts import MockPolicy

    source = quality_cases()[0].source_snapshot
    original = source["decision_fixture"]["history"][0]
    count = 0 if stage == "initial" else primary if stage == "last_answered" else 1
    history = [
        {**copy.deepcopy(original), "entry_id": str(UUID(int=100 + i))} for i in range(count)
    ]
    policy = MockPolicy(mode=mode, primary_target=primary, followup_max=followup).model_dump(
        mode="json"
    )
    inputs = fixture_inputs(source["context"], {"policy": policy, "history": history})
    task = application_prompts().resolve("mock_interview_turn_generation").task(inputs)
    assert "追问价值高于进入下一主问题" in task.instruction
    assert "首题回答同样可以有值得追问的具体缺口" in task.instruction
    if followup == 0:
        assert task.instruction.endswith(
            "本次追问额度已用尽，禁止生成任何追问；仍有主问题则继续主问题，否则结束。"
        )
        assert "ask_follow_up" not in inputs["policy"]["legal_actions"]
    else:
        assert task.instruction.endswith("根据回答判断必要性，不要求使用全部追问额度。")
    if stage == "initial":
        assert inputs["policy"]["legal_actions"] == ["ask_primary"]
    elif stage == "last_answered":
        assert "finish" in inputs["policy"]["legal_actions"]
        assert "ask_primary" not in inputs["policy"]["legal_actions"]
    else:
        assert inputs["policy"]["legal_actions"][0] == "ask_primary"
        assert "finish" not in inputs["policy"]["legal_actions"]
