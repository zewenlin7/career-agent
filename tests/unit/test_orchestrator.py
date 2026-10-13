from uuid import uuid4

import pytest
from pydantic import ValidationError

from career_agent.infrastructure.entities import JobRequirement
from career_agent.preparation.contracts import FitItem, FitOutput, WorkflowRequest
from career_agent.preparation.orchestrator import fit_gate


@pytest.mark.parametrize(
    "statuses,must,expected",
    [
        (["explicit_gap", "partial"], 2, "low_fit"),
        (["explicit_gap", "explicit_gap", "partial", "partial", "partial"], 5, "low_fit"),
        (["no_evidence", "partial"], 2, "insufficient_evidence"),
        (["matched", "partial"], 2, None),
        (["explicit_gap", "no_evidence"], 0, None),
        (["explicit_gap", "partial", "partial"], 3, None),
        (["partial", "explicit_gap"], 1, None),
    ],
)
def test_gate_exact_must_policy(statuses, must, expected):
    requirements = [
        JobRequirement(id=uuid4(), importance="must" if i < must else "preferred")
        for i in range(len(statuses))
    ]
    fit = FitOutput(
        locale="zh-CN",
        items=[
            FitItem(
                requirement_ref=r.id,
                status=s,
                fact_refs=[],
                explanation="合成解释。",
                missing_evidence="",
            )
            for r, s in zip(requirements, statuses, strict=True)
        ],
        strong_matches=[],
        partial_matches=[],
        evidence_missing=[],
        clear_gaps=[],
    )
    assert fit_gate(fit, requirements) == expected


@pytest.mark.parametrize(
    "extra",
    [
        {"targets": []},
        {"targets": ["fit_analysis", "fit_analysis"]},
        {
            "targets": ["greeting_generation"],
            "bindings": {"greeting_generation": {"output_of": "resume_tailoring"}},
        },
        {"bindings": {"resume_tailoring": {"output_of": "resume_tailoring"}}},
        {
            "bindings": {
                "greeting_generation": {
                    "output_of": "resume_tailoring",
                    "resume_revision_id": str(uuid4()),
                }
            }
        },
    ],
)
def test_invalid_target_binding_contract(extra):
    with pytest.raises(ValidationError):
        WorkflowRequest(profile_id=uuid4(), job_revision_id=uuid4(), **extra)
