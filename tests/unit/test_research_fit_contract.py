from uuid import uuid4

import pytest
from pydantic import ValidationError

from career_agent.application.compatibility import compatible, execution_versions
from career_agent.preparation.contracts import FitOutput, PrivateResult, TaskType
from career_agent.preparation.prompts import OUTPUTS, PROMPTS


def fit_payload():
    ref = str(uuid4())
    return dict(
        locale="zh-CN",
        items=[
            dict(
                requirement_ref=ref,
                status="no_evidence",
                fact_refs=[],
                explanation="材料未说明工具调用链，可补充项目执行案例。",
            )
        ],
        strong_matches=[],
        partial_matches=[],
        evidence_missing=[ref],
        clear_gaps=[],
    )


def test_new_fit_has_one_explanation_and_legacy_preserves_gap():
    payload = fit_payload()
    output = OUTPUTS[TaskType.FIT].model_validate(payload)
    assert "missing_evidence" not in output.model_dump()["items"][0]
    payload["items"][0]["missing_evidence"] = "旧结果中的补充方向"
    with pytest.raises(ValidationError):
        OUTPUTS[TaskType.FIT].model_validate(payload)
    old = PrivateResult.model_validate({"kind": "fit", "output": payload})
    assert isinstance(old.output, FitOutput)
    assert old.model_dump()["output"]["items"][0]["missing_evidence"] == "旧结果中的补充方向"


def test_research_compatibility_tracks_synthesis_without_changing_search_identity():
    versions = execution_versions("company_research")
    assert versions["research_prompt"] == PROMPTS[TaskType.RESEARCH].prompt_hash
    legacy = {k: v for k, v in versions.items() if k != "research_prompt"}
    assert not compatible(legacy, versions).reusable_for_current_execution
    assert compatible(legacy, versions).historical_readable


@pytest.mark.parametrize(
    "prose",
    [
        "未提供目标职位 JD，无法分析岗位要求。",
        "未提供个人经历，无法判断匹配度。",
        "建议你在面试中询问团队规模。",
    ],
)
def test_company_scope_rejects_personal_assessment_and_advice(prose):
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.contracts import ResearchOutput
    from career_agent.preparation.guardrails import validate_company_scope

    report = ResearchOutput(locale="zh-CN", conclusions=[], inference=[], unknowns=[prose])
    with pytest.raises(ModelGatewayError, match="research_scope_invalid"):
        validate_company_scope(report)


def test_company_unknowns_are_not_globally_banned():
    from career_agent.preparation.contracts import ResearchOutput
    from career_agent.preparation.guardrails import validate_company_scope

    validate_company_scope(
        ResearchOutput(
            locale="zh-CN",
            conclusions=[],
            inference=[],
            unknowns=["公开资料未披露研发团队规模和产品营收。", "公司招聘岗位数量尚未披露。"],
        )
    )


def test_research_input_contract_rejects_personal_and_job_body_blocks():
    from career_agent.models.contracts import ModelGatewayError
    from career_agent.preparation.prompts import task_spec

    with pytest.raises((ModelGatewayError, ValueError)):
        task_spec(
            TaskType.RESEARCH,
            {
                "company": {"name": "合成公司"},
                "evidence": [],
                "job": {"jd_text": "不应进入公司研究"},
            },
        )
    assert "Only supplied verified personal facts" not in PROMPTS[TaskType.RESEARCH].instruction
