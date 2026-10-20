"""Responses API native Pydantic output; no tools, storage or hidden SDK retries."""

import json
from decimal import Decimal
from typing import Literal

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    ProviderResponse,
    TaskSpec,
)
from career_agent.models.control.contracts import ControlPolicy
from career_agent.models.control.feedback import normalized_feedback
from career_agent.models.diagnostics import response_diagnostic, validation_issues
from career_agent.models.timeouts import ModelTimeoutPolicy
from career_agent.runtime.contracts import OutputDiagnostic, Usage


class _UsageEnvelope(BaseModel):
    # Metadata only; tolerate additional SDK fields without weakening task output schemas.
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    input_tokens_details: dict[str, int] = Field(default_factory=dict)
    output_tokens_details: dict[str, int] = Field(default_factory=dict)


class OpenAIProvider:
    def __init__(
        self,
        client: AsyncOpenAI,
        timeout_policy: ModelTimeoutPolicy | None = None,
        control_policy: ControlPolicy | None = None,
    ) -> None:
        self.client = client
        self.control_policy = control_policy or ControlPolicy()
        self.timeout_policy = timeout_policy or ModelTimeoutPolicy()

    async def generate(
        self, candidate: ModelCandidate, context: ModelRequestContext, task: TaskSpec
    ) -> ProviderResponse:
        timeout = self.timeout_policy.for_task(context.task_type)
        bucket = self.control_policy.feedback_bucket(
            candidate.provider, f"{candidate.provider}:{candidate.model}"
        )
        try:
            raw_response = await self.client.responses.with_raw_response.parse(
                timeout=timeout,
                model=candidate.model,
                input=[
                    {"role": "system", "content": task.instruction},
                    {"role": "user", "content": json.dumps(task.inputs, ensure_ascii=False)},
                ],
                text_format=context.output_schema,
                max_output_tokens=context.max_output_tokens,
                store=False,
                service_tier="default",
            )
        except APITimeoutError as exc:
            # Only a closed set of transport phase names, never exception text/request details.
            phase: Literal["connect", "read", "write", "pool", "unknown"] = "unknown"
            cause_name = type(exc.__cause__).__name__
            if cause_name == "ReadTimeout":
                phase = "read"
            elif cause_name == "ConnectTimeout":
                phase = "connect"
            elif cause_name == "WriteTimeout":
                phase = "write"
            elif cause_name == "PoolTimeout":
                phase = "pool"
            raise ModelGatewayError(
                "provider_timeout",
                retryable=True,
                diagnostic=OutputDiagnostic(
                    failure_kind="provider_timeout",
                    request_timeout_seconds=timeout,
                    timeout_policy_version=self.timeout_policy.version,
                    timeout_phase=phase,
                ),
            ) from None
        except APIConnectionError:
            raise ModelGatewayError("provider_connection", retryable=True) from None
        except APIStatusError as exc:
            code = (
                "provider_authentication_failed"
                if exc.status_code == 401
                else "provider_permission_denied"
                if exc.status_code == 403
                else "provider_model_unavailable"
                if exc.status_code == 404
                else "provider_429"
                if exc.status_code == 429
                else "provider_5xx"
                if exc.status_code >= 500
                else "provider_rejected"
            )
            raise ModelGatewayError(
                code,
                retryable=exc.status_code == 429 or exc.status_code >= 500,
                capacity_feedback=normalized_feedback(
                    exc.response.headers, quota_scope=self.control_policy.quota_scope, bucket=bucket
                ),
            ) from None
        # Read metadata before canonical parsing invokes custom validators. No body persistence.
        try:
            data = raw_response.http_response.json()
        except ValueError:
            raise ModelGatewayError("structured_output_invalid") from None
        if not isinstance(data, dict):
            raise ModelGatewayError("structured_output_invalid")
        feedback = normalized_feedback(
            raw_response.http_response.headers,
            quota_scope=self.control_policy.quota_scope,
            bucket=bucket,
        )
        diagnostic = response_diagnostic(data)
        diagnostic.request_timeout_seconds = timeout
        diagnostic.timeout_policy_version = self.timeout_policy.version
        try:
            raw = _UsageEnvelope.model_validate(data["usage"]) if data.get("usage") else None
        except ValidationError:
            raw = None  # Unknown usage remains conservatively reserved by the caller.
        usage = Usage()
        if raw is not None:
            cached = raw.input_tokens_details.get("cached_tokens", 0)
            cost = (
                (raw.input_tokens - cached) * candidate.input_cost_per_million
                + cached
                * (
                    candidate.cached_input_cost_per_million
                    if candidate.cached_input_cost_per_million is not None
                    else candidate.input_cost_per_million
                )
                + raw.output_tokens * candidate.output_cost_per_million
            ) / Decimal(1000000)
            usage = Usage(
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cached_tokens=raw.input_tokens_details.get("cached_tokens"),
                # Preserve provider usage without assuming a separate write surcharge.
                cache_write_tokens=raw.input_tokens_details.get("cache_write_tokens"),
                reasoning_tokens=raw.output_tokens_details.get("reasoning_tokens"),
                actual_model=diagnostic.actual_model,
                estimated_cost=cost,
                pricing_version=candidate.pricing_version,
                measurement="reported",
            )
        if diagnostic.response_status == "incomplete":
            diagnostic.failure_kind = "provider_incomplete"
            raise ModelGatewayError(
                "provider_incomplete",
                usage=usage,
                diagnostic=diagnostic,
                capacity_feedback=feedback,
            )
        output = data.get("output")
        if not isinstance(output, list):
            diagnostic.failure_kind = "structured_output_invalid"
            raise ModelGatewayError(
                "structured_output_invalid",
                usage=usage,
                diagnostic=diagnostic,
                capacity_feedback=feedback,
            )
        if any(
            isinstance(message, dict)
            and message.get("type") == "message"
            and isinstance(message.get("content"), list)
            and any(
                isinstance(block, dict) and block.get("type") == "refusal"
                for block in message["content"]
            )
            for message in output
        ):
            diagnostic.failure_kind = "provider_refusal"
            raise ModelGatewayError(
                "provider_refusal", usage=usage, diagnostic=diagnostic, capacity_feedback=feedback
            )
        if diagnostic.response_status != "completed":
            raise ModelGatewayError(
                "structured_output_invalid",
                usage=usage,
                diagnostic=diagnostic,
                capacity_feedback=feedback,
            )
        try:
            response = raw_response.parse()
        except ValidationError as exc:
            diagnostic.validation_issues = validation_issues(exc, context.output_schema)
            validation_code: Literal["structured_output_invalid", "output_validation_failed"] = (
                "structured_output_invalid"
                if any(issue.type == "json_invalid" for issue in diagnostic.validation_issues)
                else "output_validation_failed"
            )
            diagnostic.failure_kind = validation_code
            raise ModelGatewayError(
                validation_code, usage=usage, diagnostic=diagnostic, capacity_feedback=feedback
            ) from None
        if response.output_parsed is None:
            raise ModelGatewayError(
                "structured_output_invalid",
                usage=usage,
                diagnostic=diagnostic,
                capacity_feedback=feedback,
            )
        return ProviderResponse(
            output=response.output_parsed.model_dump(mode="json"),
            usage=usage,
            finish_reason="completed",
            diagnostic=diagnostic,
            capacity_feedback=feedback,
        )
