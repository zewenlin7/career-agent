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
