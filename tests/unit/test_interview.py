from uuid import uuid4

import pytest
from pydantic import ValidationError

from career_agent.domain.rules import DomainError
from career_agent.domain.schemas import InterviewEntry
from career_agent.interview.actual import validate_entries
from career_agent.interview.contracts import DebriefCreate, MockPolicy, SourceSnapshot
from career_agent.interview.fixture import output
from career_agent.interview.policy import InterviewPolicy
from career_agent.interview.validation import groups, validate_evaluation
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.prompts import application_prompts


def source(answer="我通过测试验证。"):
    primary = InterviewEntry(order=1, kind="primary", question="项目如何验证？", answer=answer)
    follow = InterviewEntry(
        order=2,
        kind="follow_up",
        question="如何覆盖边界？",
        answer="补充边界测试。",
        primary_entry_id=primary.entry_id,
    )
    other = InterviewEntry(
        order=3, kind="primary", question="如何建模？", answer="根据业务关系建模。"
    )
    return SourceSnapshot(
        source_kind="actual",
        interview_id=uuid4(),
        content_revision=1,
        entries=[other, follow, primary],
        notes=[],
    )


@pytest.mark.parametrize(
    "policy",
    [
        {"mode": "quick", "primary_target": 2},
        {"mode": "standard", "followup_max": 4},
        {"mode": "custom"},
        {"mode": "custom", "primary_target": 1, "followup_max": 2},
        {"mode": "custom", "primary_target": 9, "followup_max": 0},
    ],
)
def test_mock_invalid_quota(policy):
    with pytest.raises(ValidationError):
        MockPolicy.model_validate(policy)


def test_actual_entry_graph():
    snap = source()
    validate_entries(snap.entries)
    group = groups(snap)
    assert len(group) == 2 and len(group[0]["entries"]) == 2
    follow = snap.entries[1]
    for parent in (uuid4(), follow.entry_id):
        invalid = follow.model_copy(update={"primary_entry_id": parent})
        with pytest.raises(DomainError):
            validate_entries([snap.entries[2], invalid])
    with pytest.raises(DomainError):
        validate_entries(snap.entries + [snap.entries[0]])
    with pytest.raises(ValidationError):
        InterviewEntry(order=1, kind="primary", question="问题", primary_entry_id=uuid4())


@pytest.mark.parametrize(
    "targets",
    [
        {},
        {"question_analysis": "single"},
        {"question_analysis": "all", "primary_entry_id": str(uuid4())},
        {"question_analysis": "all", "subset": [str(uuid4())]},
    ],
)
def test_invalid_debrief_targets(targets):
    with pytest.raises(ValidationError):
        DebriefCreate(
            source_kind="actual", interview_id=uuid4(), expected_source_revision=1, **targets
        )


def test_evidence_group_scope_and_missing_answer():
    from career_agent.interview.compact import CompactGroup, canonical
    from career_agent.interview.debrief import inputs_for

    snap = source()
    data = output("interview_group_debrief", inputs_for(snap, snap.entries[2].entry_id))
    result = canonical(CompactGroup.model_validate(data), snap, snap.entries[2].entry_id)
    validate_evaluation(result, snap, snap.entries[2].entry_id)
    for ref in (uuid4(), snap.entries[0].entry_id):
        bad = result.model_copy(deep=True)
        bad.improvement_suggestions[0].evidence_refs = [ref]
        with pytest.raises(ModelGatewayError):
            validate_evaluation(bad, snap, snap.entries[2].entry_id)
    snap.entries[2].answer = None
    with pytest.raises(ModelGatewayError):
        validate_evaluation(result, snap, snap.entries[2].entry_id)


def test_shared_prompt_contract_and_independent_profiles():
    registry = application_prompts()
    for name in (
        "mock_interview_turn_generation",
        "interview_group_debrief",
        "interview_overall_debrief",
    ):
        spec = registry.resolve(name)
        assert spec.prompt_hash and spec.input_schema_version and spec.output_schema_version
    policy = InterviewPolicy()
    assert policy.actual_group.max_input_tokens > policy.mock_group.max_input_tokens
    assert policy.actual_overall.max_input_tokens > policy.mock_overall.max_input_tokens


async def test_interview_provider_needs_no_research_key(monkeypatch, stub_control_owner):
    from unittest.mock import MagicMock

    from pydantic import SecretStr

    from career_agent.config import Settings
    from career_agent.preparation import providers
    from career_agent.preparation.research import FixtureResearchAdapter

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(providers, "AsyncOpenAI", lambda **kwargs: Client())
    research = MagicMock(side_effect=AssertionError("unexpected research adapter"))
    monkeypatch.setattr(providers, "TavilyResearchAdapter", research)
    settings = Settings(
        _env_file=None,
        live_enabled=True,
        openai_api_key=SecretStr("synthetic-key"),
        tavily_api_key=None,
    )
    async with providers.dependencies(settings, "live", require_research=False) as (
        gateway,
        adapter,
    ):
        assert isinstance(adapter, FixtureResearchAdapter)
        assert set(gateway.adapters) == {"openai"}
    research.assert_not_called()
