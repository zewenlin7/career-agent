"""Structurally valid empty blocks for isolated adapter/metadata tests, never live inputs."""

from career_agent.models.prompts import PromptSpec


def valid_inputs(spec: PromptSpec):
    contract = spec.executable_input
    assert contract is not None
    defaults = {
        "object": {},
        "array": [],
        "string": "synthetic",
        "integer": 1,
        "boolean": False,
        "null": None,
    }
    result = {key: defaults[kinds[0]] for key, kinds in contract.required.items()}
    if spec.task_type == "mock_interview_turn_generation":
        result["policy"] = {
            "decision_contract_version": "mock-decision-v1",
            "focus": "mixed",
            "primary_question_count": 0,
            "followup_count": 0,
            "interviewer_turn_count": 0,
            "remaining_primary": 3,
            "remaining_followup": 1,
            "all_answered": True,
            "current_primary_id": None,
            "current_question_id": None,
            "legal_actions": ["ask_primary"],
            "mode": "quick",
            "primary_target": 3,
            "followup_max": 1,
        }
        result["current_group"] = {"primary_entry_id": None, "entries": []}
    result.update(contract.constants)
    if contract.context_required:
        result["context"] = {
            key: defaults[kinds[0]] for key, kinds in contract.context_required.items()
        }
    return result


def blocks(task):
    from career_agent.preparation.prompts import PROMPTS

    return valid_inputs(PROMPTS[task])["context"]
