"""Static transport timeout policy, independent of token/cost budgets and task content."""

from typing import Annotated

from pydantic import Field

from career_agent.domain.schemas import Contract
from career_agent.runtime.contracts import Identifier

TimeoutSeconds = Annotated[float, Field(gt=0, le=300, allow_inf_nan=False)]


class ModelTimeoutPolicy(Contract):
    version: Identifier = "model-request-timeout-v1"
    default_seconds: TimeoutSeconds = 60
    task_seconds: dict[Identifier, TimeoutSeconds] = Field(default_factory=dict)

    def for_task(self, task_type: str) -> float:
        return self.task_seconds.get(task_type, self.default_seconds)
