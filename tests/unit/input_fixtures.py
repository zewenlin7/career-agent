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
    result.update(contract.constants)
    if contract.context_required:
        result["context"] = {
            key: defaults[kinds[0]] for key, kinds in contract.context_required.items()
        }
    return result


def blocks(task):
    from career_agent.preparation.prompts import PROMPTS

    return valid_inputs(PROMPTS[task])["context"]
