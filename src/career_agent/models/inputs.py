"""Executable block contracts shared by code-managed prompts, before provider dispatch."""

import json
from typing import Any, Literal

from pydantic import Field

from career_agent.domain.schemas import Contract
from career_agent.models.contracts import ModelGatewayError
from career_agent.security.model_view import minimize

JSONKind = Literal["object", "array", "string", "integer", "boolean", "null"]


class InputContract(Contract):
    version: str = "input-block-contract-v1"
    required: dict[str, list[JSONKind]] = Field(default_factory=dict)
    optional: dict[str, list[JSONKind]] = Field(default_factory=dict)
    context_required: dict[str, list[JSONKind]] = Field(default_factory=dict)
    context_optional: dict[str, list[JSONKind]] = Field(default_factory=dict)
    constants: dict[str, str] = Field(default_factory=dict)
    max_bytes: int = Field(default=80000, ge=1, le=1000000)
    reject_contact_pii: bool = True

    def validate_input(self, inputs: dict[str, Any]) -> None:
        def shape(
            value: dict[str, Any],
            required: dict[str, list[JSONKind]],
            optional: dict[str, list[JSONKind]],
        ) -> None:
            if set(required) - value.keys() or value.keys() - (required.keys() | optional.keys()):
                raise ModelGatewayError("prompt_input_blocks_invalid")
            types = {
                dict: "object",
                list: "array",
                str: "string",
                int: "integer",
                bool: "boolean",
                type(None): "null",
            }
            for key, item in value.items():
                if types.get(type(item)) not in (required | optional)[key]:
                    raise ModelGatewayError("prompt_input_type_invalid")

        shape(inputs, self.required, self.optional)
        if self.context_required or self.context_optional:
            context = inputs.get("context")
            if not isinstance(context, dict):
                raise ModelGatewayError("prompt_input_type_invalid")
            shape(context, self.context_required, self.context_optional)
        if any(inputs.get(key) != value for key, value in self.constants.items()):
            raise ModelGatewayError("prompt_input_trust_invalid")
        try:
            raw = json.dumps(inputs, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError):
            raise ModelGatewayError("prompt_input_type_invalid") from None
        if len(raw.encode()) > self.max_bytes:
            raise ModelGatewayError("prompt_input_too_large")

        def privacy(value: Any) -> None:
            if isinstance(value, str) and self.reject_contact_pii and minimize(value) != value:
                raise ModelGatewayError("prompt_input_privacy_invalid")
            if isinstance(value, dict):
                if "trust_level" in value and value["trust_level"] not in {
                    "untrusted_external",
                    "user_verified",
                    "user_context_not_verified",
                }:
                    raise ModelGatewayError("prompt_input_trust_invalid")
                for child in value.values():
                    privacy(child)
            if isinstance(value, list):
                for child in value:
                    privacy(child)

        privacy(inputs)
