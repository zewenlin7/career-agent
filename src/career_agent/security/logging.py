"""Allowlisted operational logging; never log arbitrary caller strings or exceptions."""

import json
import logging
import re
from enum import StrEnum
from uuid import UUID


class SafeEvent(StrEnum):
    REQUEST_FAILED = "request_failed"
    PROVIDER_FAILED = "provider_failed"
    VALIDATION_FAILED = "validation_failed"


class SafeCode(StrEnum):
    INTERNAL_ERROR = "internal_error"
    PROVIDER_ERROR = "provider_error"
    INVALID_REQUEST = "invalid_request"


def redact(text: str) -> str:
    """Defense in depth for diagnostic text, not a promise to detect arbitrary PII."""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    text = re.sub(r"(?<!\w)\+?\d[\d ()-]{7,}\d", "[PHONE]", text)
    text = re.sub(r"(?i)(?:[A-Z]:\\|/|~/)[^\s\"'<>]+", "[PATH]", text)
    text = re.sub(
        r"(?i)(bearer\s+|(?:api[_-]?key|password|secret)\s*[:=]\s*)\S+", r"\1[SECRET]", text
    )
    return text


def safe_log(
    logger: logging.Logger,
    event: SafeEvent,
    *,
    code: SafeCode,
    run_id: UUID | None = None,
    latency_ms: int | None = None,
) -> None:
    if not isinstance(event, SafeEvent) or not isinstance(code, SafeCode):
        raise ValueError("safe logging requires enum values")
    if run_id is not None and not isinstance(run_id, UUID):
        raise ValueError("run_id must be UUID")
    if latency_ms is not None and (type(latency_ms) is not int or latency_ms < 0):
        raise ValueError("latency must be a nonnegative integer")
    payload = {
        "event": event.value,
        "code": code.value,
        "run_id": str(run_id) if run_id else None,
        "latency_ms": latency_ms,
    }
    logger.warning(json.dumps(payload))
