"""Allowlisted capacity metadata only. Never retain provider headers or diagnostic bodies."""

import re
from collections.abc import Mapping

from career_agent.models.control.contracts import CapacityFeedback, FeedbackBucket


def seconds(value: str | None) -> float | None:
    if value is None or len(value) > 64:
        return None
    try:
        result = float(value)
    except ValueError:
        parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
        if not parts or "".join(number + unit for number, unit in parts) != value:
            return None
        result = sum(
            float(number) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
            for number, unit in parts
        )
    return result if 0 <= result <= 3600 else None


def normalized_feedback(
    headers: Mapping[str, str],
    *,
    quota_scope: str | None = None,
    bucket: FeedbackBucket | None = None,
) -> CapacityFeedback:
    def count(name: str) -> int | None:
        raw = headers.get(name, "")
        return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 12 else None

    return CapacityFeedback(
        quota_scope=quota_scope,
        bucket=bucket,
        remaining_requests=count("x-ratelimit-remaining-requests"),
        remaining_tokens=count("x-ratelimit-remaining-tokens"),
        reset_requests_seconds=seconds(headers.get("x-ratelimit-reset-requests")),
        reset_tokens_seconds=seconds(headers.get("x-ratelimit-reset-tokens")),
        retry_after_seconds=seconds(headers.get("retry-after")),
    )
