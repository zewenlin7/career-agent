"""Shared code-managed prompt contracts; definitions remain in their owning features."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, TaskSpec
from career_agent.runtime.contracts import VersionMetadata


@dataclass(frozen=True)
class PromptSpec:
    prompt_name: str
    prompt_version: str
    task_type: str
    input_schema_version: str
    output_schema_version: str
    instruction: str
    input_contract: dict[str, Any]
    output_schema: type[BaseModel]

    @property
    def prompt_hash(self) -> str:
        # Excludes per-request private data and task routing: planning/replanning can share
        # one prompt. Includes the complete stable contract, not just instruction text.
        payload = {
            "hash_contract": "prompt-sha256-v1",
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "instruction": self.instruction,
            "input_schema_version": self.input_schema_version,
            "input_contract": self.input_contract,
            "output_schema_version": self.output_schema_version,
            "output_schema": self.output_schema.model_json_schema(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "input_schema_version": self.input_schema_version,
            "output_schema_version": self.output_schema_version,
        }

    def task(self, inputs: dict[str, Any]) -> TaskSpec:
        return TaskSpec(instruction=self.instruction, inputs=inputs, **self.metadata)


class PromptRegistry:
    def __init__(self, specs: list[PromptSpec]) -> None:
        if len({spec.task_type for spec in specs}) != len(specs):
            raise ValueError("duplicate_prompt_task")
        identities: dict[tuple[str, str], str] = {}
        for spec in specs:
            VersionMetadata(**spec.metadata)
            key = (spec.prompt_name, spec.prompt_version)
            if key in identities and identities[key] != spec.prompt_hash:
                raise ValueError("conflicting_prompt_identity")
            identities[key] = spec.prompt_hash
        self._specs = {spec.task_type: spec for spec in specs}

    def resolve(self, task_type: str) -> PromptSpec:
        try:
            return self._specs[task_type]
        except KeyError:
            raise ModelGatewayError("unregistered_prompt_task") from None

    def trace_metadata(self, context: ModelRequestContext, task: TaskSpec) -> VersionMetadata:
        spec = self.resolve(context.task_type)
        if (
            context.output_schema is not spec.output_schema
            or task.instruction != spec.instruction
            or any(
                getattr(context, key) != value or getattr(task, key) != value
                for key, value in spec.metadata.items()
            )
        ):
            raise ModelGatewayError("prompt_contract_mismatch")
        return VersionMetadata(workflow_version=context.workflow_version, **spec.metadata)


def application_prompts() -> PromptRegistry:
    # Composition only; no feature prompt text or provider configuration lives here.
    from career_agent.preparation.prompts import PROMPTS as preparation
    from career_agent.runtime.prompts import PROMPTS as runtime

    return PromptRegistry([*preparation.values(), *runtime.values()])
