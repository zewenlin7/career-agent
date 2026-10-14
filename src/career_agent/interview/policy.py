"""Operator-tunable safety ceilings, not calibrated product prices or quality targets."""

from decimal import Decimal

from pydantic import Field

from career_agent.domain.schemas import Contract
from career_agent.interview.contracts import InterviewLimits


class CallPolicy(Contract):
    max_input_tokens: int = Field(default=30000, ge=1000, le=75000)
    max_output_tokens: int = Field(default=4096, ge=128, le=16384)
    max_estimated_cost: Decimal = Field(default=Decimal("2"), gt=0, le=20)
    max_seconds: float = Field(default=120, gt=0, le=300)


class InterviewPolicy(Contract):
    version: str = "interview-budget-v1"
    transport_retries: int = Field(default=1, ge=0, le=2)
    schema_repairs: int = Field(default=1, ge=0, le=1)
    concurrency: int = Field(default=3, ge=1, le=8)
    mock_generation: CallPolicy = Field(default_factory=CallPolicy)
    mock_group: CallPolicy = Field(default_factory=CallPolicy)
    actual_group: CallPolicy = Field(
        default_factory=lambda: CallPolicy(max_input_tokens=60000, max_output_tokens=8192)
    )
    mock_overall: CallPolicy = Field(
        default_factory=lambda: CallPolicy(max_input_tokens=50000, max_output_tokens=6000)
    )
    actual_overall: CallPolicy = Field(
        default_factory=lambda: CallPolicy(max_input_tokens=75000, max_output_tokens=12000)
    )
    mock_session: InterviewLimits = Field(default_factory=InterviewLimits)
    mock_debrief: InterviewLimits = Field(default_factory=InterviewLimits)
    actual_debrief: InterviewLimits = Field(
        default_factory=lambda: InterviewLimits(
            max_input_tokens=5000000, max_output_tokens=500000, max_estimated_cost=Decimal("50")
        )
    )
