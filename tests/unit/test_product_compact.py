from uuid import UUID, uuid4

import pytest

from career_agent.domain.schemas import InterviewEntry
from career_agent.interview.compact import CompactGroup, CompactOverall, canonical
from career_agent.interview.contracts import SourceSnapshot
from career_agent.interview.debrief import inputs_for
from career_agent.interview.validation import validate_evaluation
from career_agent.models.contracts import ModelGatewayError


def source():
    first, follow, other = [uuid4() for _ in range(3)]
    return SourceSnapshot(
        source_kind="actual",
        interview_id=uuid4(),
        content_revision=1,
        entries=[
            InterviewEntry(
                entry_id=first,
                order=1,
                kind="primary",
                question="如何设计事务？",
                answer="保证原子性",
            ),
            InterviewEntry(
                entry_id=follow,
                order=2,
                kind="follow_up",
                primary_entry_id=first,
                question="失败时怎么办？",
                answer="回滚",
            ),
            InterviewEntry(
                entry_id=other, order=3, kind="primary", question="如何验证？", answer=None
            ),
        ],
        notes=[],
    )


def group(evidence):
    return CompactGroup(
        strengths=[],
        issues=[],
        knowledge_gap_hypotheses=[],
        improvement_suggestions=[{"content": "建议补充具体的验证过程。", "evidence": evidence}],
    )


def test_compact_numbers_resolve_to_exact_source_and_reject_cross_group():
    snapshot = source()
    ref = snapshot.entries[0].entry_id
    inputs = inputs_for(snapshot, ref)
    assert [entry["number"] for entry in inputs["group"]["entries"]] == ["1", "1.1"]
    assert str(ref) not in str(inputs)
    output = canonical(group(["1.1"]), snapshot, ref)
    validate_evaluation(output, snapshot, ref)
    assert output.improvement_suggestions[0].evidence_refs == [snapshot.entries[1].entry_id]
    for refs in (["2"], [str(uuid4())], []):
        with pytest.raises(ModelGatewayError):
            canonical(group(refs), snapshot, ref)


def test_single_entry_infers_evidence_but_never_evaluates_missing_answer():
    snapshot = source()
    ref = snapshot.entries[2].entry_id
    resolved = canonical(group([]), snapshot, ref)
    assert resolved.improvement_suggestions[0].evidence_refs == [ref]
    with pytest.raises(ModelGatewayError):
        validate_evaluation(resolved, snapshot, ref)


def test_overall_requires_real_answered_number_and_retains_canonical_evidence():
    snapshot = source()
    output = CompactOverall(
        strengths=[],
        recurring_issues=[],
        knowledge_gap_hypotheses=[],
        knowledge_candidates=[],
        practice_recommendations=[
            {"content": "建议练习事务回滚的表达。", "evidence": ["1", "1.1"]}
        ],
    )
    resolved = canonical(output, snapshot, None)
    validate_evaluation(resolved, snapshot, None)
    assert all(isinstance(ref, UUID) for ref in resolved.practice_recommendations[0].evidence_refs)


def test_eval_refinement_rejects_the_same_invalid_reference_as_production():
    from career_agent.evaluation.components import validate_task

    output = {
        "locale": "zh-CN",
        "greeting_text": "您好，希望交流。",
        "fact_refs": [str(uuid4())],
        "requirement_refs": [],
    }
    with pytest.raises(ModelGatewayError):
        validate_task(
            "greeting_refinement", output, {"context": {"facts": [], "requirements": []}}, {}
        )


@pytest.mark.parametrize("evidence", [None, [], ["问题1"], ["1、1.1"]])
def test_overall_provider_schema_rejects_ambiguous_or_missing_evidence(evidence):
    from pydantic import ValidationError

    from career_agent.interview.prompts import PROMPTS

    finding = {"content": "建议说明验证过程。"}
    if evidence is not None:
        finding["evidence"] = evidence
    value = dict(
        strengths=[finding],
        recurring_issues=[],
        knowledge_gap_hypotheses=[],
        practice_recommendations=[],
        knowledge_candidates=[],
    )
    with pytest.raises(ValidationError):
        PROMPTS["interview_overall_debrief"].output_schema.model_validate(value)


def test_overall_input_and_mapping_share_answered_anchors_with_safe_diagnostic():
    from career_agent.interview.prompts import PROMPTS

    snapshot = source()
    inputs = inputs_for(snapshot, None)
    assert inputs["source"]["evidence_numbers"] == ["1", "1.1"]
    schema = PROMPTS["interview_overall_debrief"].output_schema
    parsed = schema.model_validate(
        dict(
            strengths=[{"content": "合成分析。", "evidence": ["99"]}],
            recurring_issues=[],
            knowledge_gap_hypotheses=[],
            practice_recommendations=[],
            knowledge_candidates=[],
        )
    )
    with pytest.raises(ModelGatewayError) as error:
        canonical(parsed, snapshot, None)
    diagnostic = error.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.validation_issues[0].loc == ["strengths", 0, "evidence", 0]
    assert diagnostic.reference_diagnostic.allowed_count == 2
    assert diagnostic.reference_diagnostic.reason == "unknown_number"
    assert "合成分析" not in diagnostic.model_dump_json()


@pytest.mark.parametrize("kind", ["actual", "mock"])
@pytest.mark.parametrize("refs", [["1"], ["1.1"], ["1", "1.1"]])
def test_current_overall_production_prompt_eval_and_exact_reference_mapping(kind, refs):
    from career_agent.evaluation.components import validate_task
    from career_agent.interview.compact import CompactOverallV3
    from career_agent.models.prompts import application_prompts

    snapshot = source().model_copy(update={"source_kind": kind})
    inputs = inputs_for(snapshot, None)
    spec = application_prompts().resolve("interview_overall_debrief")
    task = spec.task(inputs)
    assert "source.evidence_numbers" in task.instruction
    assert "nonempty evidence array" in task.instruction
    assert task.inputs["source"]["evidence_numbers"] == ["1", "1.1"]
    output = dict(
        strengths=[],
        recurring_issues=[],
        knowledge_gap_hypotheses=[],
        knowledge_candidates=[],
        practice_recommendations=[{"content": "建议练习表达验证步骤。", "evidence": refs}],
    )
    validate_task(spec.task_type, output, inputs, snapshot.model_dump(mode="json"))
    result = canonical(CompactOverallV3.model_validate(output), snapshot, None)
    assert result.practice_recommendations[0].evidence_refs == [
        snapshot.entries[{"1": 0, "1.1": 1}[ref]].entry_id for ref in refs
    ]
    output["practice_recommendations"][0]["evidence"] = ["2"]
    with pytest.raises(ModelGatewayError, match="invalid_evidence_reference"):
        validate_task(spec.task_type, output, inputs, snapshot.model_dump(mode="json"))
