"""Historical reconstruction and regression reports are read-only, zero-model operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.evaluation import entities as q
from career_agent.evaluation.calibration import calibration_report
from career_agent.evaluation.comparison import aggregate, compare_case
from career_agent.evaluation.contracts import (
    ComparisonPolicy,
    EvalCase,
    EvalCheckResult,
    TrialResult,
)
from career_agent.evaluation.identity import digest
from career_agent.infrastructure import entities as e


def config_diff(
    before: dict[str, Any], after: dict[str, Any], prefix: str = ""
) -> list[dict[str, Any]]:
    diff = []
    for key in sorted(before.keys() | after.keys()):
        path = prefix + key
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if isinstance(old, dict) and isinstance(new, dict):
            diff += config_diff(old, new, path + ".")
        else:
            diff.append({"path": path, "baseline": old, "candidate": new})
    return diff


async def trial_with_quality(session: AsyncSession, trial: q.EvalTrialRow) -> TrialResult:
    result = TrialResult.model_validate(trial.result)
    calls = list(
        await session.scalars(
            select(q.InvocationRow.model_call_id).where(q.InvocationRow.trial_id == trial.id)
        )
    )
    decisions = list(await session.scalars(select(q.SamplingRow)))
    buckets: dict[str, list[dict[str, Any]]] = {}
    categories: dict[str, list[str]] = {}
    coverage: list[dict[str, Any]] = []
    for decision in decisions:
        subject = decision.data["subject"]
        if subject["accepted_model_call_id"] not in {str(call) for call in calls if call}:
            continue
        judges = list(
            await session.scalars(select(q.JudgeRow).where(q.JudgeRow.sampling_id == decision.id))
        )
        coverage.append(
            {
                "sampled": decision.data["sampled"],
                "population": decision.data["population"],
                "statuses": [j.status for j in judges],
                "available": not decision.data["sampled"]
                or bool(judges)
                and all(j.status == "completed" and bool(j.result) for j in judges),
            }
        )
        for judge in judges:
            if judge.status != "completed" or not judge.result:
                continue
            for criterion in judge.result["criteria"]:
                key = subject["task_type"] + ":" + criterion["criterion"]
                categories.setdefault(key, []).append(criterion["rating"])
                buckets.setdefault(key, []).append({"judge": judge, "criterion": criterion})
    for key, items in buckets.items():
        ratings = [item["criterion"]["rating"] for item in items]
        versions = {digest(item["judge"].spec) for item in items}
        result.checks.append(
            EvalCheckResult(
                check_id="judge:" + key,
                check_version="judge-check-v2:" + digest(sorted(versions)),
                category="quality",
                tier=1,
                status="error"
                if "insufficient_evidence" in ratings or len(versions) != 1
                else "fail"
                if any(r != "pass" for r in ratings)
                else "pass",
                reason_code="quality_evidence",
                material="major_issue" in ratings,
                metadata={"ratings": ratings},
                evidence_refs=[str(item["judge"].id) for item in items],
            )
        )
    result.output = {**result.output, "judge_categories": categories, "judge_coverage": coverage}
    return result


async def comparison(
    session: AsyncSession, baseline_id: UUID, candidate_id: UUID, policy: ComparisonPolicy
) -> q.ComparisonRow:
    baseline = await require(session, q.EvalRunRow, baseline_id)
    candidate = await require(session, q.EvalRunRow, candidate_id)
    before = list(
        await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == baseline_id))
    )
    after = list(
        await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == candidate_id))
    )
    results = []
    rows = []
    for id in sorted({t.case_id for t in before + after}, key=str):
        case = EvalCase.model_validate((await require(session, q.EvalCaseRow, id)).data)
        old = [await trial_with_quality(session, t) for t in before if t.case_id == id and t.result]
        new = [await trial_with_quality(session, t) for t in after if t.case_id == id and t.result]
        value = compare_case(old, new, policy)
        rows.append((case, value))
        results.append({"case_id": case.case_id, "case_version": case.case_version, **value})
    data = {
        "policy": policy.model_dump(mode="json"),
        "configuration_diff": config_diff(baseline.candidate, candidate.candidate),
        "cases": results,
        "aggregate": aggregate(rows),
        "gate": "BLOCKED"
        if any(r["gate"] == "BLOCKED" for r in results)
        else "REVIEW_REQUIRED"
        if any(r["gate"] == "REVIEW_REQUIRED" for r in results)
        else "PASS",
        "operation_deltas_are_attribution_not_causation": True,
    }
    row = q.ComparisonRow(
        baseline_id=baseline_id, candidate_id=candidate_id, policy_version=policy.version, data=data
    )
    session.add(row)
    await session.flush()
    return row


async def calibration(session: AsyncSession) -> dict[str, Any]:
    pairs = []
    annotations = list(await session.scalars(select(q.AnnotationRow)))
    for judge in await session.scalars(select(q.JudgeRow).where(q.JudgeRow.status == "completed")):
        sampling = await require(session, q.SamplingRow, judge.sampling_id)
        call = await session.get(e.ModelCall, judge.model_call_id) if judge.model_call_id else None
        for annotation in annotations:
            if (
                annotation.subject_id != sampling.subject_id
                or annotation.data["rubric_version"] != judge.spec["rubric_version"]
            ):
                continue
            if annotation.data["population"] != sampling.data["population"]:
                continue
            for criterion in (judge.result or {}).get("criteria", []):
                human = next(
                    (
                        c
                        for c in annotation.data["criteria"]
                        if c["criterion"] == criterion["criterion"]
                    ),
                    None,
                )
                if human is None:
                    continue
                pairs.append(
                    {
                        "subject_id": str(sampling.subject_id),
                        "population": sampling.data["population"],
                        "task_type": sampling.data["subject"]["task_type"],
                        "judge_spec_version": judge.spec["version"],
                        "judge_model": call.model if call else "unknown",
                        "criterion": criterion["criterion"],
                        "human": human["rating"],
                        "judge": criterion["rating"],
                        "confidence": criterion["confidence"],
                        "annotation_id": str(annotation.id),
                        "annotation_created_at": annotation.created_at.isoformat(),
                        "judge_id": str(judge.id),
                        "judge_created_at": judge.created_at.isoformat(),
                    }
                )
    return calibration_report(pairs)
