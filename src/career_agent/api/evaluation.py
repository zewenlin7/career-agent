"""Explicit private eval/monitoring operations. No paid default and no background drain."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select

from career_agent.api.dependencies import DB
from career_agent.application.services import require
from career_agent.domain.rules import DomainError
from career_agent.domain.schemas import Contract
from career_agent.evaluation import entities as q
from career_agent.evaluation import monitoring, reports, store
from career_agent.evaluation.contracts import (
    Annotation,
    CapturePayload,
    ComparisonPolicy,
    EvalCase,
    EvalLimits,
    EvalRunRequest,
    EvalSuite,
    Feedback,
    SamplingReason,
    Subject,
)
from career_agent.evaluation.judge import JudgeRunner
from career_agent.evaluation.runner import EvalRunner

router = APIRouter(prefix="/api/v1/evaluation")


@router.post("/cases", status_code=201)
async def put_case(payload: EvalCase, session: DB) -> dict[str, Any]:
    row = await store.put_case(session, payload)
    return {"id": row.id, "case": row.data}


@router.get("/cases")
async def cases(session: DB, tag: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(q.EvalCaseRow)
            .order_by(q.EvalCaseRow.case_key, q.EvalCaseRow.version)
            .limit(min(max(limit, 1), 500))
        )
    )
    return [{"id": r.id, "case": r.data} for r in rows if tag is None or tag in r.data["tags"]]


@router.post("/suites", status_code=201)
async def put_suite(payload: EvalSuite, session: DB) -> dict[str, Any]:
    row = await store.put_suite(session, payload)
    return {"id": row.id, "suite": row.data}


@router.post("/runs", status_code=201)
async def create_run(payload: EvalRunRequest, request: Request) -> dict[str, Any]:
    runner = EvalRunner(request.app.state.sessions, request.app.state.settings)
    id = await runner.create(payload)
    return await runner.view(id)


@router.post("/runs/{id}/execute")
async def execute_run(id: UUID, request: Request) -> dict[str, Any]:
    return await EvalRunner(request.app.state.sessions, request.app.state.settings).execute(id)


@router.get("/runs/{id}")
async def get_run(id: UUID, request: Request) -> dict[str, Any]:
    return await EvalRunner(request.app.state.sessions, request.app.state.settings).view(id)


@router.post("/runs/{id}/cancel")
async def cancel_run(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.EvalRunRow, id, lock=True)
    if row.status not in {"pending", "running"}:
        raise DomainError("eval_run_terminal")
    row.status = "cancelled"
    return {"id": id, "status": row.status}


@router.get("/trials/{id}")
async def trial(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.EvalTrialRow, id)
    operations = list(
        await session.scalars(
            select(q.InvocationRow)
            .where(q.InvocationRow.trial_id == id)
            .order_by(q.InvocationRow.created_at)
        )
    )
    return {
        "id": id,
        "result": row.result,
        "operations": [{"id": o.id, **o.data} for o in operations],
    }


@router.get("/operations/{id}")
async def operation(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.InvocationRow, id)
    return {"id": id, **row.data}


@router.get("/cases/{id}/origin")
async def origin_reconstruction(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.EvalCaseRow, id)
    capture_id = row.data["origin_provenance"].get("capture_id")
    captured = await session.get(q.CaptureRow, UUID(capture_id)) if capture_id else None
    return {
        "mode": "origin_reconstruction",
        "model_calls": 0,
        "original_output": captured.payload["output"] if captured else None,
        "original_trace_refs": captured.payload["evaluation_refs"] if captured else [],
        "origin_output_available": captured is not None,
        "origin_provenance": row.data["origin_provenance"],
        "frozen_source": row.data["source_snapshot"],
        "frozen_input": row.data["model_input"],
        "external_observations": row.data["frozen_external_observations"],
    }


class CompareRequest(Contract):
    baseline_run_id: UUID
    candidate_run_id: UUID
    policy: ComparisonPolicy = Field(default_factory=ComparisonPolicy)


@router.post("/comparisons", status_code=201)
async def compare(payload: CompareRequest, session: DB) -> dict[str, Any]:
    row = await reports.comparison(
        session, payload.baseline_run_id, payload.candidate_run_id, payload.policy
    )
    return {"id": row.id, **row.data}


@router.get("/comparisons/{id}")
async def get_comparison(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.ComparisonRow, id)
    return {"id": id, **row.data}


class SamplingRequest(Contract):
    subject: Subject
    reason: SamplingReason | None = None


@router.post("/sampling", status_code=201)
async def sample(payload: SamplingRequest, request: Request, session: DB) -> dict[str, Any]:
    row = await monitoring.enqueue(
        session, payload.subject, request.app.state.settings.judge_sampling, payload.reason
    )
    return (
        {"id": row.id, "decision": row.data}
        if row
        else {"reason_code": "evaluation_origin_excluded"}
    )


@router.get("/sampling")
async def sampling(session: DB, subject_id: UUID) -> list[dict[str, Any]]:
    return [
        {"id": r.id, **r.data}
        for r in await session.scalars(
            select(q.SamplingRow).where(q.SamplingRow.subject_id == subject_id)
        )
    ]


class Drain(Contract):
    limit: int = Field(default=20, ge=1, le=200)
    concurrency: int = Field(default=2, ge=1, le=8)
    limits: EvalLimits = Field(default_factory=EvalLimits)


@router.post("/judges/drain")
async def drain(payload: Drain, request: Request) -> dict[str, Any]:
    return await JudgeRunner(request.app.state.sessions, request.app.state.settings).drain(
        **payload.model_dump(exclude={"limits"}), limits=payload.limits
    )


@router.get("/judges/{id}")
async def judge(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.JudgeRow, id)
    return {
        "id": id,
        "status": row.status,
        "spec": row.spec,
        "result": row.result,
        "severity": row.severity,
        "model_call_id": row.model_call_id,
        "reason_code": row.reason_code,
    }


@router.post("/feedback", status_code=201)
async def feedback(payload: Feedback, request: Request, session: DB) -> dict[str, Any]:
    row = await monitoring.record_feedback(
        session, payload, request.app.state.settings.judge_sampling
    )
    return {"id": row.id}


class QueueRequest(Contract):
    subject: Subject
    population: Literal["random", "targeted"]


@router.post("/annotations/queue", status_code=201)
async def queue_annotation(payload: QueueRequest, session: DB) -> dict[str, Any]:
    row = await monitoring.annotation_queue(session, payload.subject, payload.population)
    return {"id": row.id}


@router.get("/annotations/queue")
async def list_queue(session: DB) -> list[dict[str, Any]]:
    return [
        {"id": r.id, "subject_id": r.subject_id, "population": r.population, "status": r.status}
        for r in await session.scalars(select(q.AnnotationQueueRow).limit(100))
    ]


@router.get("/annotations/queue/{id}")
async def blind_annotation(id: UUID, session: DB) -> dict[str, Any]:
    return await monitoring.blind_view(session, id)


@router.post("/annotations/queue/{id}", status_code=201)
async def annotate(id: UUID, payload: Annotation, session: DB) -> dict[str, Any]:
    row = await monitoring.annotate(session, id, payload)
    return {"id": row.id}


@router.get("/calibration")
async def calibration(session: DB) -> dict[str, Any]:
    return await reports.calibration(session)


class CaptureRequest(Contract):
    payload: CapturePayload
    trigger: Literal["manual", "deterministic_warning", "unexpected_retry", "partial_failure"]


@router.post("/captures", status_code=201)
async def capture(payload: CaptureRequest, session: DB) -> dict[str, Any]:
    row = await store.capture(session, payload.payload, payload.trigger)
    return {"id": row.id, "status": row.status}


@router.get("/captures/{id}")
async def get_capture(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.CaptureRow, id)
    events = list(
        await session.scalars(
            select(q.CaptureEventRow)
            .where(q.CaptureEventRow.capture_id == id)
            .order_by(q.CaptureEventRow.created_at)
        )
    )
    return {
        "id": id,
        "status": row.status,
        "payload": row.payload,
        "events": [
            {"kind": x.kind, "reference_id": x.reference_id, "reason_code": x.reason_code}
            for x in events
        ],
    }


class Triage(Contract):
    status: Literal["triaged", "dismissed"]
    reason_code: str


@router.post("/captures/{id}/triage")
async def triage(id: UUID, payload: Triage, session: DB) -> dict[str, Any]:
    row = await store.triage(session, id, payload.status, payload.reason_code)
    return {"id": id, "status": row.status}


@router.get("/captures/{id}/sanitized")
async def sanitized(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.CaptureRow, id)
    return {"payload": store.sanitize(row.payload), "requires_explicit_promotion": True}


class Promote(Contract):
    case: EvalCase
    confirmed_repo_safe: bool = False


@router.post("/captures/{id}/promote", status_code=201)
async def promote(id: UUID, payload: Promote, session: DB) -> dict[str, Any]:
    row = await store.promote(
        session, id, payload.case, confirmed_repo_safe=payload.confirmed_repo_safe
    )
    return {"id": row.id, "case": row.data}


@router.get("/cases/{id}/export")
async def export_case(id: UUID, session: DB) -> dict[str, Any]:
    row = await require(session, q.EvalCaseRow, id)
    if row.data["source_type"] == "private_capture" or not store.repo_safe(row.data):
        from career_agent.domain.rules import DomainError

        raise DomainError("case_not_repo_safe")
    return row.data


@router.post("/judges", status_code=201)
async def explicit_judge(subject: Subject, session: DB) -> dict[str, Any]:
    row = await monitoring.request_explicit_judge(session, subject)
    return {"id": row.id, "status": row.status}
