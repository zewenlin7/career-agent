from dataclasses import replace

from career_agent.models.composition import Composition, serialize
from career_agent.models.prompts import application_prompts


def test_stable_objects_preserve_semantic_array_order():
    contract = Composition(orders={"": ["stable", "volatile"]})
    a = {"volatile": 2, "stable": {"z": 1, "a": 2}, "refs": ["b", "a"]}
    b = {"refs": ["b", "a"], "stable": {"a": 2, "z": 1}, "volatile": 2}
    assert serialize(contract.compose(a)) == serialize(contract.compose(b))
    assert contract.compose(a)["refs"] == ["b", "a"]
    assert serialize(contract.compose(a)).startswith('{"stable":')


def test_all_feature_prompts_have_versioned_composition():
    registry = application_prompts()
    from career_agent.interview.prompts import PROMPTS

    for task, spec in registry.specs.items():
        assert spec.composition.version == "provider-composition-v1"
        if task in PROMPTS:
            assert spec.composition.orders[""][0] == "stable_context"
        changed = replace(spec, composition=Composition(version="changed"))
        assert changed.prompt_hash != spec.prompt_hash


def test_mock_stable_prefix_changes_only_at_volatile_suffix():
    import copy

    from career_agent.interview.prompts import PROMPTS

    spec = PROMPTS["mock_interview_turn_generation"]
    payload = {
        "policy": {"primary_question_count": 1},
        "current_answer": "新的回答",
        "current_question": {"question": "当前问题"},
        "question_history": [{"question": "历史问题", "fact_refs": ["ref-b", "ref-a"]}],
        "stable_context": {"job": {"title": "合成岗位"}, "facts": [{"id": "ref-a"}]},
    }
    first = serialize(spec.task(payload).inputs)
    changed = copy.deepcopy(payload)
    changed["current_answer"] = "另一个回答"
    changed["policy"]["primary_question_count"] = 2
    second = serialize(spec.task(changed).inputs)
    assert first.split('"current_answer":')[0] == second.split('"current_answer":')[0]
    assert payload["question_history"][0]["fact_refs"] == ["ref-b", "ref-a"]


def test_uncomposed_task_cannot_claim_composed_prompt_contract():
    import pytest

    from career_agent.models.contracts import ModelGatewayError, ModelRequestContext
    from career_agent.preparation.contracts import TaskType
    from career_agent.preparation.prompts import task_spec

    registry = application_prompts()
    spec = registry.resolve(TaskType.EXTRACTION.value)
    task = task_spec(TaskType.EXTRACTION, {"job": {"jd_text": "合成岗位"}})
    ctx = ModelRequestContext(
        task_type=TaskType.EXTRACTION.value, output_schema=spec.output_schema, **spec.metadata
    )
    registry.trace_metadata(ctx, task)
    unordered = task.model_copy(update={"inputs": dict(reversed(list(task.inputs.items())))})
    with pytest.raises(ModelGatewayError, match="prompt_composition_mismatch"):
        registry.trace_metadata(ctx, unordered)
