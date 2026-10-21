"""Deterministic provider serialization; this stores no response cache."""

import json
from typing import Any

from pydantic import Field

from career_agent.domain.schemas import Contract


class Composition(Contract):
    version: str = "provider-composition-v1"
    # Feature-owned order at selected object paths; other objects use lexical key order.
    orders: dict[str, list[str]] = Field(default_factory=dict)

    def compose(self, value: dict[str, Any]) -> dict[str, Any]:
        def visit(item: Any, path: str) -> Any:
            if isinstance(item, dict):
                preferred = self.orders.get(path, [])
                keys = [k for k in preferred if k in item]
                keys += sorted(set(item) - set(keys))
                return {k: visit(item[k], f"{path}.{k}" if path else k) for k in keys}
            if isinstance(item, list):
                return [visit(v, f"{path}[]") for v in item]
            return item

        result: dict[str, Any] = visit(value, "")
        return result


def serialize(inputs: dict[str, Any]) -> str:
    return json.dumps(inputs, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
