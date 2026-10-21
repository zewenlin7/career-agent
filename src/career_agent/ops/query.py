"""Metadata-only operational projections. Journals are counted once per attempt."""

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.evaluation.entities import JudgeRow, SamplingRow
from career_agent.infrastructure.entities import AgentRun, AgentStep
from career_agent.models.control.controller import HEALTH_FAILURES
from career_agent.models.control.recovery_contracts import JournalData, utcnow
from career_agent.ops.entities import AttemptJournal, ControlEvent, RecoveryIncident
from career_agent.preparation.observation_store import ReuseDecision


def cache_telemetry(facts: list[JournalData]) -> dict[str, Any]:
    """Provider-reported attempt usage only. Missing fields are never inferred as zero."""
    output: dict[str, Any] = {"attempts": len(facts), "actual_billed_savings_usd": None}
    for field in ("input_tokens", "cached_tokens", "cache_write_tokens"):
        known = [
            getattr(d.usage, field)
            for d in facts
            if d.usage and d.usage.measurement == "reported" and getattr(d.usage, field) is not None
        ]
        output[field] = {
            "known_sum": sum(known) if known else None,
            "reported_attempts": len(known),
            "unknown_attempts": len(facts) - len(known),
        }
    pairs = [
        d
        for d in facts
        if d.usage
        and d.usage.measurement == "reported"
        and d.usage.input_tokens is not None
        and d.usage.cached_tokens is not None
    ]
    inputs = sum(d.usage.input_tokens or 0 for d in pairs if d.usage)
    output["token_cache_hit_rate"] = (
        sum(d.usage.cached_tokens or 0 for d in pairs if d.usage) / inputs if inputs else None
    )
    output["token_cache_rate_attempts"] = len(pairs)
    for label, hit in (("hit", True), ("miss", False)):
        members = [
            d
            for d in facts
            if d.usage
            and d.usage.measurement == "reported"
            and d.usage.cached_tokens is not None
            and (d.usage.cached_tokens > 0) == hit
        ]
        latencies = sorted(d.latency_ms for d in members if d.latency_ms is not None)
        output[label] = {
            "attempts": len(members),
            "latency_observations": len(latencies),
            "latency_p50_ms": latencies[len(latencies) // 2] if latencies else None,
        }
    denominator = output["hit"]["attempts"] + output["miss"]["attempts"]
    output["cache_hit_call_rate"] = output["hit"]["attempts"] / denominator if denominator else None
    return output


async def metrics(
    session: AsyncSession, scope: str, window_seconds: int, now: datetime | None = None
) -> dict[str, Any]:
    since = (now or utcnow()) - timedelta(seconds=window_seconds)
    rows = list(
        await session.scalars(
            select(AttemptJournal).where(
                AttemptJournal.scope == scope, AttemptJournal.created_at >= since
            )
        )
    )
    dispatched = [
        r
        for r in rows
        if JournalData.model_validate(r.data).dispatched_at is not None
        and r.status != "not_dispatched"
    ]
    facts = [JournalData.model_validate(r.data) for r in dispatched]
    confirmed = [d for d in facts if d.dispatch_confirmed]
    known = [d for d in facts if d.usage and d.usage.estimated_cost is not None]
    unknown = [d for d in facts if not d.usage or d.usage.estimated_cost is None]
    latencies = sorted(d.latency_ms for d in facts if d.latency_ms is not None)
    accuracy = [d for d in facts if d.usage and d.usage.output_tokens is not None]
    populations: dict[str, dict[str, Any]] = {}
    sampling = list(
        await session.scalars(select(SamplingRow).where(SamplingRow.created_at >= since))
    )
    for population in ("random", "targeted"):
        members = [s for s in sampling if s.data["population"] == population]
        judges = (
            list(
                await session.scalars(
                    select(JudgeRow).where(JudgeRow.sampling_id.in_([s.id for s in members]))
                )
            )
            if members
            else []
        )
        populations[population] = {
            "subjects": len({s.subject_id for s in members}),
            "decisions": len(members),
            "sampled": sum(bool(s.data["sampled"]) for s in members),
            "not_sampled": sum(not s.data["sampled"] for s in members),
            "judge_evaluations": len(judges),
            "judge_status": dict(Counter(j.status for j in judges)),
            "completed_severity": dict(
                Counter(j.severity for j in judges if j.status == "completed")
            ),
        }
    control_events = list(
        await session.scalars(
            select(ControlEvent).where(
                ControlEvent.scope == scope, ControlEvent.created_at >= since
            )
        )
    )
    recovery = list(
        await session.scalars(select(RecoveryIncident).where(RecoveryIncident.scope == scope))
    )
    admission = {}
    adjustments: Counter[str] = Counter()
    operators: Counter[str] = Counter()
    for event in control_events:
        kind = event.data["kind"]
        if kind == "admission_denied":
            for d in event.data.get("decisions", []):
                key = (event.data.get("logical_operation_id") or str(event.id), d.get("sequence"))
                admission[key] = d["reason"]
        elif kind == "tick":
            adjustments.update(d["reason"] for d in event.data.get("decisions", []))
        else:
            operators[kind] += 1
    outstanding_rows = await session.scalars(
        select(AttemptJournal).where(
            AttemptJournal.scope == scope,
            AttemptJournal.status.in_(
                ["dispatch_intent", "unknown", "settled", "business_committed"]
            ),
        )
    )
    outstanding = [JournalData.model_validate(r.data) for r in outstanding_rows]
    outstanding = [
        d
        for d in outstanding
        if d.dispatched_at and (d.usage is None or d.usage.estimated_cost is None)
    ]

    def reserved(d: JournalData) -> Decimal:
        return (
            d.usage.budget_reserved_usd
            if d.usage and d.usage.budget_reserved_usd
            else d.financial_reservation.budget_reserved_usd
        )

    reuse = list(
        await session.scalars(select(ReuseDecision).where(ReuseDecision.created_at >= since))
    )
    return {
        "provider_token_cache": cache_telemetry(confirmed),
        # Global business decisions, not provider/quota-scoped usage or measured savings.
        "reuse_global_population": {
            category: {
                "decisions": sum(r.category == category for r in reuse),
                "dispositions": dict(
                    Counter(r.disposition for r in reuse if r.category == category)
                ),
                "operations": dict(Counter(r.operation for r in reuse if r.category == category)),
                "estimated_savings_usd": None,
                "actual_billed_savings_usd": None,
            }
            for category in ("external_observation", "business_artifact")
        },
        "admission_decisions": dict(Counter(admission.values())),
        "automatic_adjustments": dict(adjustments),
        "operator_and_lifecycle_events": dict(operators),
        "window_unknown_budget_reserved_usd": str(sum((reserved(d) for d in unknown), Decimal(0))),
        "outstanding_unknown_budget_reserved_usd": str(
            sum((reserved(d) for d in outstanding), Decimal(0))
        ),
        "outstanding_unknown_attempts": len(outstanding),
        "recovery_incidents": dict(Counter(r.status for r in recovery)),
        "task_type": dict(Counter(d.selection["task_type"] for d in facts)),
        "scope": scope,
        "window_seconds": window_seconds,
        "window_start": since,
        "attempts": len(confirmed),
        "unknown_dispatch_intents": sum(not d.dispatch_confirmed for d in facts),
        "logical_operations": len({r.operation_id for r in dispatched}),
        "journal_status": dict(Counter(r.status for r in rows)),
        "attempt_outcome": dict(Counter(d.provider_outcome or "unknown" for d in facts)),
        "provider_health": {
            "success": sum(d.provider_outcome == "completed" for d in confirmed),
            "failure": sum(d.provider_outcome in HEALTH_FAILURES for d in confirmed),
            "neutral": sum(
                d.provider_outcome != "completed" and d.provider_outcome not in HEALTH_FAILURES
                for d in confirmed
            ),
        },
        "retry_attempts": sum(d.selection["attempt_index"] > 1 for d in confirmed),
        "routes": dict(Counter(d.selection["route"] for d in facts)),
        "routing_roles": dict(Counter(d.selection["routing_role"] for d in facts)),
        "unknown_usage_attempts": len(unknown),
        "estimated_cost_usd_known": str(
            sum((d.usage.estimated_cost or Decimal(0) for d in known if d.usage), Decimal(0))
        ),
        "unknown_budget_reserved_usd": str(
            sum(
                (
                    d.usage.budget_reserved_usd
                    if d.usage and d.usage.budget_reserved_usd
                    else d.financial_reservation.budget_reserved_usd
                    for d in unknown
                ),
                Decimal(0),
            )
        ),
        "actual_billed_cost_usd": None,
        "latency_ms": {
            "observations": len(latencies),
            "p50": latencies[len(latencies) // 2] if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "reservation_accuracy": {
            "known_outputs": len(accuracy),
            "under_reserved": sum(
                bool(
                    d.usage
                    and d.usage.output_tokens is not None
                    and d.usage.output_tokens > d.selection["reserved_output_tokens"]
                )
                for d in accuracy
            ),
        },
        # Separate populations; never sum parent and child usage/cost.
        "workflow_runs": await session.scalar(
            select(func.count()).select_from(AgentRun).where(AgentRun.created_at >= since)
        ),
        "business_actions": await session.scalar(
            select(func.count(func.distinct(tuple_(AgentStep.run_id, AgentStep.action_id)))).where(
                AgentStep.created_at >= since, AgentStep.action_id.is_not(None)
            )
        ),
        "steps": await session.scalar(
            select(func.count()).select_from(AgentStep).where(AgentStep.created_at >= since)
        ),
        "quality_global_population": populations,
    }


async def events(session: AsyncSession, scope: str, after: int, limit: int) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(ControlEvent)
        .where(ControlEvent.scope == scope, ControlEvent.sequence > after)
        .order_by(ControlEvent.sequence)
        .limit(limit)
    )
    return [
        {"id": r.id, "sequence": r.sequence, **{k: v for k, v in r.data.items() if k != "snapshot"}}
        for r in rows
    ]


async def incidents(session: AsyncSession, scope: str, limit: int) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(RecoveryIncident)
        .where(RecoveryIncident.scope == scope)
        .order_by(RecoveryIncident.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": r.id,
            "attempt_id": r.attempt_id,
            "revision": r.revision,
            "reason": r.reason,
            "status": r.status,
            "resolution": r.resolution,
        }
        for r in rows
    ]
