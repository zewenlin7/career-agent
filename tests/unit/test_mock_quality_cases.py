"""Exercise labels and the real Eval chain; controlled outputs are not quality evidence."""

import copy
import json
from pathlib import Path

import pytest

from career_agent.config import Settings
from career_agent.evaluation.contracts import EvalRunRequest
from career_agent.evaluation.execution import SharedEvalBudget
from career_agent.evaluation.mock_quality import fixture_inputs, quality_cases
from career_agent.evaluation.runner import EvalRunner
from career_agent.models.fake import FakeProvider
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.providers import POLICY, registry

CASES = quality_cases()


def test_pairs_only_change_the_answer_not_materials_questions_or_allowances():
    assert len(CASES) == 9
    pairs = {}
    for case in CASES:
        source = case.source_snapshot
        assert case.model_input == fixture_inputs(source["context"], source["decision_fixture"])
        assert "decision_quality" not in case.model_input
        annotation = source["decision_quality"]
        assert annotation["preferred"] in annotation["acceptable"]
        inputs = copy.deepcopy(case.model_input)
        inputs["current_group"]["entries"][-1]["answer"] = "<paired-variable>"
        pairs.setdefault(annotation["pair"], []).append(inputs)
    assert set(pairs) == {"first_answer", "current_group", "last_answer"}
    for variants in pairs.values():
        assert all(v == variants[0] for v in variants)
    last = pairs["last_answer"][0]["policy"]
    assert last["remaining_followup"] > 0 and last["remaining_primary"] == 0
    assert last["legal_actions"] == ["ask_follow_up", "finish"]


def test_quality_suite_file_matches_annotated_cases():
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/evaluation/mock_decision_quality.json").read_text()
    )
    assert data["cases"] == [c.model_dump(mode="json") for c in CASES]
    assert data["suite"]["members"] == [
        {"case_id": c.case_id, "case_version": c.case_version} for c in CASES
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
async def test_default_fixture_quality_misses_remain_visible(case):
    request = EvalRunRequest(suite_id="mock-decision-quality", suite_version=1)
    result, operations = await EvalRunner(None, Settings()).run_case(
        case, request, SharedEvalBudget(request.limits)
    )
    # Fixture still prefers follow-up. Its legally executed answer must not be
    # relabeled as high quality simply to make this suite green.
    assert result.output["valid"] is True
    assert result.output["output"]["turn"]["kind"] == "follow_up"
    checks = {c.check_id: c for c in result.checks}
    annotation = case.source_snapshot["decision_quality"]
    assert checks["execution_legal"].status == "pass"
    assert checks["decision_acceptable"].status == (
        "pass" if "follow_up" in annotation["acceptable"] else "fail"
    )
    if "decision_preferred" in checks:
        assert checks["decision_preferred"].status == (
            "pass" if annotation["preferred"] == "follow_up" else "fail"
        )
    assert len(operations) == 1 and operations[0].input_snapshot == case.model_input


async def run_choice(case, choice):
    value = {"action": "finish", "turn": None}
    if choice != "finish":
        value = {
            "action": "ask",
            "turn": {
                "kind": choice,
                "question": "请说明该边界如何验证。",
                "question_type": "technical",
                "primary_entry_id": case.model_input["policy"]["current_primary_id"]
                if choice == "follow_up"
                else None,
                "requirement_refs": [],
                "fact_refs": [],
                "reason_code": "clarify_answer" if choice == "follow_up" else "next_primary",
            },
        }
    provider = FakeProvider(value)
    settings = Settings()
    gateway = ModelGateway(registry(settings, False), POLICY, {"fixture": provider})
    request = EvalRunRequest(suite_id="mock-decision-quality", suite_version=1)
    result, _ = await EvalRunner(None, settings, gateway).run_case(
        case, request, SharedEvalBudget(request.limits)
    )
    assert provider.calls == 1
    return result


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
async def test_preferred_labels_pass_real_parser_validator_and_eval_checks(case):
    result = await run_choice(case, case.source_snapshot["decision_quality"]["preferred"])
    assert result.status == "completed"
    assert all(check.status == "pass" for check in result.checks)


async def test_reasonable_alternative_is_acceptable_but_not_marked_preferred():
    case = next(c for c in CASES if c.case_id.endswith("conditional_judgment"))
    result = await run_choice(case, "follow_up")
    checks = {c.check_id: c for c in result.checks}
    assert checks["decision_acceptable"].status == "pass"
    assert result.status == "completed"
    assert "decision_preferred" not in checks
    assert case.source_snapshot["decision_quality"]["preferred"] == "primary"
