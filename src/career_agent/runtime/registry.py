"""Only coarse, typed business actions. No dynamic imports or arbitrary execution."""

from dataclasses import dataclass
from typing import Literal

from career_agent.runtime.agent_contracts import ActionArgs, ActionName, ActionObservation


@dataclass(frozen=True)
class ActionSpec:
    name: ActionName
    version: str = "business-action-v1"
    args_schema: type[ActionArgs] = ActionArgs
    result_schema: type[ActionObservation] = ActionObservation
    side_effect: Literal["private_domain_write"] = "private_domain_write"
    permission_policy: str = "explicit-scope-and-bindings-v1"
    timeout_seconds: int = 600
    retry_policy: str = "no_action_retry"
    idempotency_policy: str = "checkpoint-cas-and-compatible-artifact-reuse"
    budget_class: str = "shared-root-budget"


REGISTRY: dict[ActionName, ActionSpec] = {
    "prepare_application": ActionSpec("prepare_application"),
    "prepare_interview": ActionSpec("prepare_interview"),
}
