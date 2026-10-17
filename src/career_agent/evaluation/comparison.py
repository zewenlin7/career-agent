"""Priority-tier comparison; no single score that can conceal a correctness regression."""

from collections import defaultdict
from typing import Any

from career_agent.evaluation.contracts import ComparisonPolicy, EvalCase, TrialResult


def distribution(trials: list[TrialResult]) -> dict[str, Any]:
    costs = [float(t.usage.estimated_cost) for t in trials if t.usage.estimated_cost is not None]
    eligible = [
        t
        for t in trials
        if t.status not in {"case_incompatible", "cancelled"}
        and t.checks
        and all(c.status in {"pass", "fail"} for c in t.checks)
        and all(c["available"] for c in t.output.get("judge_coverage", []))
    ]
    return {
        "sample_count": len(trials),
        "eligible_trial_count": len(eligible),
        "unavailable_trial_count": len(trials) - len(eligible),
        "success_rate": sum(t.status == "completed" for t in trials) / len(trials)
        if trials
        else None,
        "pass_rate": sum(all(c.status == "pass" for c in t.checks) for t in eligible)
        / len(eligible)
        if eligible
        else None,
        "latency_ms": [t.latency_ms for t in trials],
        "estimated_cost_usd": costs,
        "unknown_cost_count": len(trials) - len(costs),
        "failure_rate": sum(t.status == "failed" for t in trials) / len(trials) if trials else None,
        "retry_counts": [t.output.get("retry_count") for t in trials],
        "judge_categories": [t.output.get("judge_categories", {}) for t in trials],
    }


def compare_case(
    baseline: list[TrialResult], candidate: list[TrialResult], policy: ComparisonPolicy
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "headline": "INCONCLUSIVE",
        "gate": "REVIEW_REQUIRED",
        "deltas": [],
        "baseline_distribution": distribution(baseline),
        "candidate_distribution": distribution(candidate),
    }
    if min(len(baseline), len(candidate)) < policy.minimum_trials or any(
        t.status in {"case_incompatible", "cancelled"} for t in baseline + candidate
    ):
        out["reason_code"] = "insufficient_or_incompatible_evidence"
        return out
    old_ids = {c.check_id for t in baseline for c in t.checks}
    new_ids = {c.check_id for t in candidate for c in t.checks}
    ids = old_ids | new_ids
    evidence_error = "incompatible_checks" if old_ids != new_ids or not ids else None
    ordinal = {"pass": 0, "minor_issue": 1, "major_issue": 2}
    for id in sorted(ids):
        old = [c for t in baseline for c in t.checks if c.check_id == id]
        new = [c for t in candidate for c in t.checks if c.check_id == id]
        if (
            len(old) != len(baseline)
            or len(new) != len(candidate)
            or any(c.status in {"error", "skipped"} for c in old + new)
        ):
            evidence_error = "insufficient_check_evidence"
            continue
        if any(
            (c.check_version, c.tier, c.category)
            != (old[0].check_version, old[0].tier, old[0].category)
            for c in old + new
        ):
            evidence_error = "incompatible_check_versions"
            continue
        delta = sum(c.status == "pass" for c in new) / len(new) - sum(
            c.status == "pass" for c in old
        ) / len(old)
        pass_rate_delta = delta
        ordinal_delta = None
        # Ordinal evidence retains severity; binary validity remains independently visible.
        if all(c.metadata.get("ratings") for c in old + new):

            def severity(checks: list[Any]) -> float:
                ratings = [r for c in checks for r in c.metadata["ratings"]]
                return sum(ordinal[r] for r in ratings) / len(ratings)

            ordinal_delta = severity(old) - severity(new)
            delta = ordinal_delta
        out["deltas"].append(
            {
                "check_id": id,
                "dimension": new[0].category,
                "tier": new[0].tier,
                "delta": "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged",
                "magnitude": "material" if any(c.material for c in old + new) else "minor",
                "pass_rate_delta": pass_rate_delta,
                "ordinal_severity_delta": ordinal_delta,
            }
        )
    material = [
        d for d in out["deltas"] if d["magnitude"] == "material" and d["delta"] != "unchanged"
    ]
    if any(d["tier"] == 0 and d["delta"] == "regressed" for d in out["deltas"]):
        out.update(headline="REGRESSED", gate="BLOCKED")
    elif material:
        top = min(d["tier"] for d in material)
        directions = {d["delta"] for d in material if d["tier"] == top}
        conflict = top == 1 and directions == {"improved", "regressed"}
        out.update(
            headline="TRADEOFF"
            if conflict
            else "REGRESSED"
            if "regressed" in directions
            else "IMPROVED",
            gate="REVIEW_REQUIRED" if conflict or "regressed" in directions else "PASS",
        )
    else:
        out.update(headline="UNCHANGED", gate="PASS")
    unavailable = any(
        not coverage["available"]
        for trial in baseline + candidate
        for coverage in trial.output.get("judge_coverage", [])
    )
    correctness = [c for t in candidate for c in t.checks if c.category == "correctness"]
    out["correctness_passed"] = (
        all(c.status == "pass" for c in correctness) if correctness else None
    )
    if (unavailable or evidence_error) and out["gate"] != "BLOCKED":
        out.update(
            headline="INCONCLUSIVE",
            gate="REVIEW_REQUIRED",
            reason_code="judge_evidence_unavailable" if unavailable else evidence_error,
        )
    if policy.efficiency_threshold is not None:
        costs = out["candidate_distribution"]["estimated_cost_usd"]
        if costs and max(costs) > float(policy.efficiency_threshold):
            out["deltas"].append(
                {
                    "check_id": "efficiency_threshold",
                    "dimension": "efficiency",
                    "tier": 3,
                    "delta": "regressed",
                    "magnitude": "material",
                }
            )
            if policy.efficiency_blocking:
                out.update(headline="REGRESSED", gate="BLOCKED")
    return out


def aggregate(cases: list[tuple[EvalCase, dict[str, Any]]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for case, result in cases:
        dimensions = [
            "overall",
            f"component:{case.entrypoint.name}",
            f"source_type:{case.source_type}",
            *[f"tag:{tag}" for tag in case.tags],
        ]
        if case.entrypoint.component_kind == "model_task":
            dimensions.append(f"task_type:{case.entrypoint.name}")
        if case.entrypoint.kind == "business_workflow":
            dimensions.append(f"workflow:{case.entrypoint.name}")
        for dimension in dimensions:
            buckets[dimension][result["headline"]] += 1
        for delta in result.get("deltas", []):
            buckets[f"check_id:{delta['check_id']}"][delta["delta"]] += 1
            if delta["dimension"] == "quality":
                buckets[f"judge_criterion:{delta['check_id']}"][delta["delta"]] += 1
    return {key: dict(value) for key, value in buckets.items()}
