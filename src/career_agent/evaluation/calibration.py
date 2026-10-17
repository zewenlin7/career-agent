"""Descriptive agreement, not proof that a judge or individual annotator is ground truth."""

from collections import defaultdict
from typing import Any

ORDINAL = ["pass", "minor_issue", "major_issue"]


def statistics(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [*ORDINAL, "insufficient_evidence"]
    matrix = {human: {judge: 0 for judge in labels} for human in labels}
    confidence: dict[str, dict[str, int]] = {
        level: {"count": 0, "agree": 0} for level in ["low", "medium", "high"]
    }
    high_disagreements = []
    for row in pairs:
        human, judge = row["human"], row["judge"]
        matrix[human][judge] += 1
        bucket = confidence[row["confidence"]]
        bucket["count"] += 1
        bucket["agree"] += human == judge
        if row["confidence"] == "high" and human != judge:
            high_disagreements.append(row["subject_id"])
    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        predicted = sum(matrix[h][label] for h in labels)
        actual = sum(matrix[label].values())
        precision, recall = tp / predicted if predicted else 0.0, tp / actual if actual else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "support": actual,
            "predictions": predicted,
        }
    n = sum(matrix[h][j] for h in ORDINAL for j in ORDINAL)
    kappa = None
    if n:
        observed = sum(
            ((ORDINAL.index(h) - ORDINAL.index(j)) / 2) ** 2 * matrix[h][j] / n
            for h in ORDINAL
            for j in ORDINAL
        )
        expected = sum(
            ((ORDINAL.index(h) - ORDINAL.index(j)) / 2) ** 2
            * sum(matrix[h][x] for x in ORDINAL)
            * sum(matrix[x][j] for x in ORDINAL)
            / (n * n)
            for h in ORDINAL
            for j in ORDINAL
        )
        if expected:
            kappa = 1 - observed / expected
    return {
        "sample_count": len(pairs),
        "unique_subject_count": len({row["subject_id"] for row in pairs}),
        "raw_agreement": sum(matrix[x][x] for x in labels) / len(pairs) if pairs else None,
        "weighted_cohens_kappa": kappa,
        "kappa_weighting": "quadratic",
        "ordinal_pair_count": n,
        "confusion_matrix": matrix,
        "per_class": per_class,
        "macro_f1": sum(per_class[x]["f1"] for x in ORDINAL) / 3 if pairs else None,
        "major_issue_recall": per_class["major_issue"]["recall"]
        if per_class["major_issue"]["support"]
        else None,
        "confidence_calibration": {
            k: {**v, "agreement": v["agree"] / v["count"] if v["count"] else None}
            for k, v in confidence.items()
        },
        "high_confidence_disagreements": high_disagreements,
    }


def calibration_report(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    # One latest annotation/judgment pair per subject and comparable criterion stratum.
    # This is selection, not adjudication or a vote over repeated annotations.
    selected: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in sorted(
        pairs,
        key=lambda r: (
            r.get("annotation_created_at", ""),
            r.get("annotation_id", ""),
            r.get("judge_created_at", ""),
            r.get("judge_id", ""),
        ),
    ):
        key = tuple(
            str(row[k])
            for k in (
                "subject_id",
                "population",
                "task_type",
                "judge_spec_version",
                "judge_model",
                "criterion",
            )
        )
        selected[key] = row
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected.values():
        # Never mix unbiased calibration with targeted diagnostic sampling.
        population = row["population"]
        groups[f"population:{population}"].append(row)
        for dimension in ["task_type", "judge_spec_version", "judge_model", "criterion"]:
            groups[f"{population}/{dimension}:{row[dimension]}"].append(row)
    return {
        **{key: statistics(rows) for key, rows in sorted(groups.items())},
        "selection_policy": "latest-pair-per-subject-stratum-v1",
        "statistical_unit": "subject-population-task-judge-spec-model-criterion",
        "unique_subject_count": len({row["subject_id"] for row in pairs}),
        "pair_details": pairs,
        "selected_pair_count": len(selected),
    }
