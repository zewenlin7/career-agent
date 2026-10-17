"""Private immutable snapshots, explicit case publication and structured retrieval."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.evaluation import entities as q
from career_agent.evaluation.contracts import CapturePayload, EvalCase, EvalSuite, Expectation
from career_agent.evaluation.identity import digest
from career_agent.security.model_view import model_view


async def put_case(session: AsyncSession, case: EvalCase) -> q.EvalCaseRow:
    hash_value = digest(case.model_dump(mode="json", exclude={"content_hash"}))
    if case.content_hash and case.content_hash != hash_value:
        raise DomainError("case_hash_mismatch")
    case = case.model_copy(update={"content_hash": hash_value})
    old = await session.scalar(
        select(q.EvalCaseRow).where(
            q.EvalCaseRow.case_key == case.case_id, q.EvalCaseRow.version == case.case_version
        )
    )
    if old:
        if old.content_hash != hash_value:
            raise DomainError("immutable_case_version")
        return old
    row = q.EvalCaseRow(
        case_key=case.case_id,
        version=case.case_version,
        content_hash=hash_value,
        data=case.model_dump(mode="json"),
    )
    session.add(row)
    await session.flush()
    return row


async def put_suite(session: AsyncSession, suite: EvalSuite) -> q.EvalSuiteRow:
    for member in suite.members:
        if (
            await session.scalar(
                select(q.EvalCaseRow.id).where(
                    q.EvalCaseRow.case_key == member.case_id,
                    q.EvalCaseRow.version == member.case_version,
                )
            )
            is None
        ):
            raise DomainError("suite_member_missing")
    old = await session.scalar(
        select(q.EvalSuiteRow).where(
            q.EvalSuiteRow.suite_key == suite.suite_id, q.EvalSuiteRow.version == suite.version
        )
    )
    data = suite.model_dump(mode="json")
    if old:
        if old.data != data:
            raise DomainError("immutable_suite_version")
        return old
    row = q.EvalSuiteRow(suite_key=suite.suite_id, version=suite.version, data=data)
    session.add(row)
    await session.flush()
    return row


async def capture(
    session: AsyncSession, payload: CapturePayload, trigger: str, reference_id: UUID | None = None
) -> q.CaptureRow:
    # Lock the authority (accepted call) to serialize first capture for the same subject.
    # Serialize even subjects without a ModelCall (deterministic failures).
    from sqlalchemy import text

    from career_agent.infrastructure import entities as e

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 0))"),
        {"subject": str(payload.subject.subject_id)},
    )
    if payload.subject.accepted_model_call_id:
        from career_agent.evaluation.monitoring import payload_from_invocation, resolve_subject

        await require(session, e.ModelCall, payload.subject.accepted_model_call_id, lock=True)
        invocation = await resolve_subject(session, payload.subject)
        authoritative = payload_from_invocation(payload.subject, invocation)
        if payload.provenance.get("logical_operation_id") not in {
            None,
            authoritative.provenance.get("logical_operation_id"),
        }:
            raise DomainError("subject_provenance_mismatch")
        payload = authoritative
    old = await session.scalar(
        select(q.CaptureRow)
        .where(q.CaptureRow.subject_id == payload.subject.subject_id)
        .with_for_update()
    )
    if old is None:
        hash_value = digest(payload.model_dump(mode="json", exclude={"content_hash"}))
        payload = payload.model_copy(update={"content_hash": hash_value})
        old = q.CaptureRow(
            subject_id=payload.subject.subject_id,
            content_hash=hash_value,
            payload=payload.model_dump(mode="json"),
        )
        session.add(old)
        await session.flush()
    session.add(q.CaptureEventRow(capture_id=old.id, kind=trigger, reference_id=reference_id))
    await session.flush()
    return old


async def triage(session: AsyncSession, id: UUID, status: str, reason: str) -> q.CaptureRow:
    row = await require(session, q.CaptureRow, id, lock=True)
    if status not in {"triaged", "dismissed"} or row.status not in {"captured", "triaged"}:
        raise DomainError("invalid_capture_transition")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reason):
        raise DomainError("invalid_reason_code")
    row.status = status
    session.add(q.CaptureEventRow(capture_id=id, kind=status, reason_code=reason))
    return row


def sanitize(value: dict[str, Any]) -> dict[str, Any]:
    names: set[str] = set()

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "display_name" and isinstance(child, str):
                    names.add(child)
                collect(child)
        if isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    cleaned = model_view(value)
    for name in sorted(names):
        cleaned = model_view(cleaned, name=name)

    def paths(item: Any) -> Any:
        if isinstance(item, str):
            item = re.sub(r"(?:/Users/|/home/|/private/)[^\s\"']+", "[PRIVATE_PATH]", item)
            item = re.sub(r"\b(?:sk-|tvly-)[A-Za-z0-9_-]{8,}", "[SECRET]", item)
            return item
        if isinstance(item, dict):
            return {
                k: paths(v)
                for k, v in item.items()
                if k.lower()
                not in {"api_key", "authorization", "secret", "password", "private_pdf_base64"}
            }
        if isinstance(item, list):
            return [paths(v) for v in item]
        return item

    result: dict[str, Any] = paths(cleaned)
    return result


def repo_safe(value: dict[str, Any]) -> bool:
    return sanitize(value) == value


async def promote(
    session: AsyncSession, id: UUID, case: EvalCase, *, confirmed_repo_safe: bool
) -> q.EvalCaseRow:
    row = await require(session, q.CaptureRow, id, lock=True)
    if row.status not in {"triaged", "promoted"} or not confirmed_repo_safe:
        raise DomainError("explicit_review_required")
    # Caller constructs expectations explicitly; sanitized output is NOT expected prose.
    if not case.expectations or any(not isinstance(x, Expectation) for x in case.expectations):
        raise DomainError("expectations_required")
    if case.source_type != "sanitized" or not repo_safe(case.model_dump(mode="json")):
        raise DomainError("case_not_repo_safe")
    sanitized = sanitize(row.payload)
    expected_source = sanitized["source_snapshot"]
    if (
        case.entrypoint.kind in {"business_workflow", "agent_goal"}
        or case.entrypoint.component_kind == "business_action"
    ):
        from career_agent.evaluation.captured import replay_source
        from career_agent.models.contracts import ModelGatewayError

        try:
            expected_source = replay_source(expected_source)
        except ModelGatewayError:
            raise DomainError("case_incompatible") from None
    if case.source_snapshot != expected_source:
        raise DomainError("capture_source_mismatch")
    frozen = expected_source.get("captured", {})
    if frozen and datetime.fromisoformat(frozen["evaluation_clock"]) != case.evaluation_clock:
        raise DomainError("capture_clock_mismatch")
    if any(
        not file.get("failure") and "private_pdf_base64" not in file
        for file in frozen.get("artifact_files", {}).values()
    ):
        raise DomainError("case_incompatible")
    if (
        case.entrypoint.component_kind == "model_task"
        and case.model_input != sanitized["model_input"]
    ):
        raise DomainError("capture_input_mismatch")
    authoritative_origin = sanitize(row.payload["provenance"])
    if any(
        key not in {"note", "metadata"} and authoritative_origin.get(key) != value
        for key, value in case.origin_provenance.items()
    ):
        raise DomainError("origin_identity_override")
    provenance = {
        **authoritative_origin,
        **{k: v for k, v in case.origin_provenance.items() if k in {"note", "metadata"}},
        "capture_id": str(row.id),
        "capture_hash": row.content_hash,
    }
    promoted = await put_case(
        session, case.model_copy(update={"origin_provenance": provenance, "content_hash": None})
    )
    row.status = "promoted"
    session.add(q.CaptureEventRow(capture_id=id, kind="promoted", reference_id=promoted.id))
    return promoted
