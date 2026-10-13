from uuid import uuid4

import pytest
from pydantic import ValidationError

from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import (
    ExtractedRequirement,
    FitItem,
    FitOutput,
    GreetingOutput,
    PrivateResult,
    RequirementsOutput,
    ResearchConclusion,
    ResearchOutput,
)
from career_agent.preparation.guardrails import (
    minimize,
    validate_extraction,
    validate_fit,
    validate_greeting,
    validate_research,
)


def requirement(**updates):
    return ExtractedRequirement.model_validate(
        {
            "evidence_span": "必须掌握 Python。",
            "normalized_requirement": "掌握 Python",
            "requirement_kind": "must",
            "category": "技能",
            "skills": ["Python"],
            **updates,
        }
    )


def test_extraction_evidence_dedup_and_inference():
    good = requirement()
    assert (
        len(
            validate_extraction(
                RequirementsOutput(requirements=[good, good]), good.evidence_span
            ).requirements
        )
        == 1
    )
    for bad in [
        requirement(evidence_span="不存在"),
        requirement(skills=["Rust"]),
        requirement(normalized_requirement="必须有 8 年经验"),
    ]:
        with pytest.raises(ModelGatewayError):
            validate_extraction(RequirementsOutput(requirements=[bad]), good.evidence_span)
    with pytest.raises(ValidationError):
        requirement(requirement_kind="invented")


@pytest.mark.parametrize("status", ["matched", "partial", "no_evidence", "explicit_gap"])
def test_fit_status_distinctions(status):
    r, f = uuid4(), uuid4()
    refs = [] if status == "no_evidence" else [f]
    summary = {
        "strong_matches": [],
        "partial_matches": [],
        "evidence_missing": [],
        "clear_gaps": [],
    }
    key = {
        "matched": "strong_matches",
        "partial": "partial_matches",
        "no_evidence": "evidence_missing",
        "explicit_gap": "clear_gaps",
    }[status]
    summary[key] = [r]
    fit = FitOutput(
        locale="zh-CN",
        items=[
            FitItem(
                requirement_ref=r,
                status=status,
                fact_refs=refs,
                explanation="依据现有事实对照，不推断未知能力。",
                missing_evidence="",
            )
        ],
        **summary,
    )
    facts = {f: {"category": "explicit_gap", "statement": "用户确认需要补充分布式系统经验。"}}
    validate_fit(fit, {r}, facts)
    if status == "explicit_gap":
        with pytest.raises(ModelGatewayError, match="gap_requires_explicit_evidence"):
            validate_fit(fit, {r}, {f: {"category": "project"}})
    with pytest.raises(ModelGatewayError, match="requirement_coverage_invalid"):
        validate_fit(fit, {uuid4()}, facts)
    for explanation in ["匹配率 83%", "83% match，中文说明", "83% 匹配", "录用机会 90%"]:
        fit.items[0].explanation = explanation
        with pytest.raises(ModelGatewayError, match="fake_probability"):
            validate_fit(fit, {r}, facts)


def test_greeting_references_and_fabricated_number():
    r, f = uuid4(), uuid4()
    output = GreetingOutput(
        locale="zh-CN",
        greeting_text="您好，我有 Python 项目经验。",
        fact_refs=[f],
        requirement_refs=[r],
    )
    facts = {f: {"statement": "使用 Python 完成合成项目。"}}
    validate_greeting(output, {r}, facts)
    with pytest.raises(ModelGatewayError, match="invalid_reference"):
        validate_greeting(output, set(), facts)
    output.greeting_text = "提升效率 99%。"
    with pytest.raises(ModelGatewayError, match="hard_field_mismatch"):
        validate_greeting(output, {r}, facts)
    with pytest.raises(ValidationError):
        PrivateResult(kind="fit", output=output)


def test_research_citations_and_pii_minimization():
    evidence = uuid4()
    output = ResearchOutput(
        locale="zh-CN",
        conclusions=[ResearchConclusion(text="公开业务资料。", evidence_refs=[evidence])],
        unknowns=["未知信息。"],
        inference=[],
    )
    validate_research(output, {evidence})
    with pytest.raises(ModelGatewayError, match="invalid_reference"):
        validate_research(output, set())
    result = minimize(
        "合成姓名 synthetic@example.invalid 13800138000 +1 (212) 555-0100", "合成姓名"
    )
    assert "合成姓名" not in result and "@" not in result and "13800138000" not in result


@pytest.fixture
def compression_pair():
    import json
    from pathlib import Path

    from career_agent.resume.schemas import ResumeDocument

    before = ResumeDocument.model_validate(
        json.loads(Path("tests/fixtures/resumes/normal_one_page_zh_cn.json").read_text())[
            "document"
        ]
    )
    # A controlled shortening that preserves every hard field and every reference.
    before.sections[0].items[0].text += "，保留合成测试验证记录。"
    after = before.model_copy(deep=True)
    after.sections[0].items[0].text = (
        after.sections[0].items[0].text.removesuffix("，保留合成测试验证记录。")
    )
    return before, after


def test_compression_preserves_identity_and_required_facts(compression_pair):
    from career_agent.preparation.guardrails import validate_compression

    before, after = compression_pair
    validate_compression(before, after, [])
    changed = after.model_copy(deep=True)
    changed.sections[0].items[0].fact_refs.append(uuid4())
    with pytest.raises(ModelGatewayError, match="compression_facts_changed"):
        validate_compression(before, changed, [])
    changed = after.model_copy(deep=True)
    changed.sections[0].items = []
    with pytest.raises(ModelGatewayError, match="compression_required_changed"):
        validate_compression(before, changed, [])
    changed = after.model_copy(deep=True)
    changed.profile_revision += 1
    with pytest.raises(ModelGatewayError, match="compression_identity_changed"):
        validate_compression(before, changed, [])
    changed = after.model_copy(deep=True)
    changed.sections[0].items[0].text += "提升 999%。"
    with pytest.raises(ModelGatewayError, match="compression_hard_field_changed"):
        validate_compression(before, changed, [])
