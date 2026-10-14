"""Only coarse, typed business actions. No dynamic imports or arbitrary execution."""

from dataclasses import dataclass
from typing import Literal

from career_agent.models.contracts import ModelGatewayError
from career_agent.runtime.agent_contracts import (
    ActionArgs,
    ActionName,
    ActionObservation,
    PlanAction,
)
from career_agent.runtime.contracts import VersionMetadata


@dataclass(frozen=True)
class ActionSpec:
    name: ActionName
    version: str
    args_schema_version: str
    result_schema_version: str
    args_schema: type[ActionArgs] = ActionArgs
    result_schema: type[ActionObservation] = ActionObservation
    side_effect: Literal["private_domain_write"] = "private_domain_write"
    permission_policy: str = "explicit-scope-and-bindings-v1"
    timeout_seconds: int = 600
    retry_policy: str = "no_action_retry"
    idempotency_policy: str = "checkpoint-cas-and-compatible-artifact-reuse"
    budget_class: str = "shared-root-budget"

    def __post_init__(self) -> None:
        VersionMetadata(
            action_name=self.name,
            action_version=self.version,
            input_schema_version=self.args_schema_version,
            output_schema_version=self.result_schema_version,
        )


REGISTRY: dict[ActionName, ActionSpec] = {
    "prepare_application": ActionSpec(
        "prepare_application", "business-action-v1", "action-args-v1", "action-observation-v1"
    ),
    "prepare_interview": ActionSpec(
        "prepare_interview", "business-action-v1", "action-args-v1", "action-observation-v1"
    ),
}


def validate_action_version(action: PlanAction) -> None:
    spec = REGISTRY.get(action.name)
    if spec is None:
        raise ModelGatewayError("unregistered_action")
    # Exact compatibility only. Never silently upgrade an old or unpinned checkpoint.
    if action.action_version != spec.version:
        raise ModelGatewayError("action_version_mismatch")
