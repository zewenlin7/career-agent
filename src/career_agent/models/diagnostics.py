"""Allowlisted diagnostics only: never copy validation inputs or provider prose."""

import re
from typing import Any

from pydantic import BaseModel, ValidationError

from career_agent.runtime.contracts import OutputDiagnostic, ValidationIssue


def validation_issues(error: ValidationError, schema: type[BaseModel]) -> list[ValidationIssue]:
    allowed: set[str] = set()

    def fields(node: Any) -> None:
        if isinstance(node, dict):
            allowed.update(node.get("properties", {}))
            for value in node.values():
                fields(value)
        elif isinstance(node, list):
            for value in node:
                fields(value)

    fields(schema.model_json_schema())
    issues = []
    for item in error.errors(include_input=False, include_context=False, include_url=False)[:20]:
        location = [
            part if isinstance(part, int) or part in allowed else "unknown_field"
            for part in item["loc"][:12]
        ]
        kind = item["type"]
        if not re.fullmatch(r"[a-z_]{1,80}", kind):
            kind = "validation_error"
        # Exact whitelist of repository-owned validator messages, never provider/user prose.
        safe_messages = {
            "duplicate fact references",
            "short_text must be shorter",
            "control characters are not supported",
            "duplicate IDs or section names",
            "at least one required factual item is needed",
            "document too large",
        }
        message = "canonical schema validation failed"
        for safe in safe_messages:
            if item["msg"] == "Value error, " + safe:
                message = safe
                break
        issues.append(
            ValidationIssue.model_validate({"loc": location, "type": kind, "message": message})
        )
    return issues


def response_diagnostic(data: dict[str, Any]) -> OutputDiagnostic:
    response_id = data.get("id")
    model = data.get("model")
    status = data.get("status")
    details = data.get("incomplete_details")
    reason = details.get("reason") if isinstance(details, dict) else None
    return OutputDiagnostic(
        response_id=response_id
        if isinstance(response_id, str) and re.fullmatch(r"resp_[A-Za-z0-9_-]{1,120}", response_id)
        else None,
        actual_model=model
        if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", model)
        else None,
        response_status=status
        if status in {"completed", "incomplete", "failed", "cancelled", "queued", "in_progress"}
        else "unknown",
        incomplete_reason=reason if reason in {"max_output_tokens", "content_filter"} else None,
    )
