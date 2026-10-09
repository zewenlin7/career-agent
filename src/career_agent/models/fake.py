from decimal import Decimal
from typing import Any

from career_agent.models.contracts import (
    ModelCandidate,
    ModelRequestContext,
    ProviderResponse,
    TaskSpec,
)
from career_agent.runtime.contracts import Usage


class FakeProvider:
    """Returns explicit synthetic output. No networking, prompt interpretation or paid calls."""

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls = 0

    async def generate(
        self,
        candidate: ModelCandidate,
        context: ModelRequestContext,
        task: TaskSpec,
    ) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(
            output=self.output,
            usage=Usage(
                input_tokens=0,
                output_tokens=0,
                cached_tokens=None,
                estimated_cost=Decimal("0"),
                pricing_version=None,
            ),
            finish_reason="fake_completed",
        )
