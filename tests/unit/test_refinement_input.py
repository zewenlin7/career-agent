from copy import deepcopy

from career_agent.product.prompts import generation_inputs


def test_resume_generation_has_one_authoritative_body_and_keeps_evidence():
    original = {"sections": [{"items": [{"text": "原始经历", "fact_refs": ["exact"]}]}]}
    inputs = {
        "original": original,
        "feedback": "突出验证",
        "context": {
            "resume": original,
            "profile": {"skills_text": "大量重复资料" * 2000},
            "document_template": {},
            "profile_refs": {},
            "profile_id": "profile",
            "profile_revision": 8,
            "job_revision_id": "jd",
            "job": {"jd_text": "职位要求"},
            "facts": [{"id": "exact", "statement": "原始经历"}],
            "requirements": [{"id": "r"}],
        },
    }
    frozen = deepcopy(inputs)
    projected = generation_inputs("resume_refinement", inputs)
    assert projected["original"] == original
    assert (
        not {"resume", "profile", "document_template", "profile_refs"} & projected["context"].keys()
    )
    for key in (
        "facts",
        "requirements",
        "profile_id",
        "profile_revision",
        "job_revision_id",
        "job",
    ):
        assert projected["context"][key] == inputs["context"][key]
    assert inputs == frozen
    assert generation_inputs("greeting_refinement", inputs) == inputs


def test_projection_passes_real_preflight_without_increasing_limits():
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from career_agent.config import Settings
    from career_agent.interview.calls import InterviewCalls
    from career_agent.interview.policy import CallPolicy
    from career_agent.models.gateway import ModelGateway
    from career_agent.preparation.budget import input_bound
    from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
    from career_agent.product.prompts import PROMPTS

    gateway = ModelGateway(registry(Settings(), False), POLICY, {"fixture": FixtureTaskProvider()})
    calls = InterviewCalls(async_sessionmaker(), gateway)
    policy = CallPolicy()
    inputs = {
        "original": {"sections": []},
        "feedback": "保留事实",
        "context": {
            "resume": {"sections": []},
            "profile": {"skills_text": "合成背景资料" * 2000},
            "facts": [],
            "requirements": [],
        },
    }
    context = calls.request("resume_refinement", "fixture", policy)
    assert input_bound(context, PROMPTS["resume_refinement"].task(inputs)) > policy.max_input_tokens
    assert calls.preflight("resume_refinement", "fixture", inputs, policy) < policy.max_input_tokens
