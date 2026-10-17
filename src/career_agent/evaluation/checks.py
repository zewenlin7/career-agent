"""Deterministic expectations and trajectory checks; never a model judge."""

from typing import Any

from career_agent.evaluation.contracts import EvalCheckResult, Expectation


def lookup(value: Any, path: str) -> Any:
    for key in path.split(".") if path else []:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            raise KeyError(path)
    return value


def evaluate(expectations: list[Expectation], result: dict[str, Any]) -> list[EvalCheckResult]:
    checks = []
    for expectation in expectations:
        status, reason = "fail", "expectation_not_met"
        try:
            value = lookup(result, expectation.path)
            expected = expectation.value
            match expectation.operator:
                case "equals":
                    passed = value == expected
                case "contains":
                    passed = expected in value
                case "absent":
                    passed = expected not in value
                case "max":
                    passed = value <= expected
                case "min":
                    passed = value >= expected
                case "valid":
                    passed = value is True
            if passed:
                status, reason = "pass", "expectation_met"
        except (KeyError, TypeError, ValueError):
            status, reason = "error", "expectation_evidence_unavailable"
        checks.append(
            EvalCheckResult.model_validate(
                {
                    "check_id": expectation.check_id,
                    "category": expectation.category,
                    "status": status,
                    "reason_code": reason,
                    "tier": expectation.tier,
                    "material": expectation.material,
                    "evidence_refs": [expectation.path],
                }
            )
        )
    return checks


def trajectory(actions: list[dict[str, Any]]) -> dict[str, Any]:
    # State-sensitive identities are emitted by the production runtime. Action names alone
    # are not duplicates: new authorized context can legally repeat the same action.
    keys = [
        a["identity"] for a in actions if a.get("identity") and a.get("disposition") == "executed"
    ]
    duplicate = len(keys) != len(set(keys))
    cycle = any(keys[i] == keys[j] for i in range(len(keys)) for j in range(i + 2, len(keys)))
    return {
        "duplicate": duplicate,
        "cycle": cycle,
        "action_count": len(actions),
        "executed_count": sum(a.get("disposition") == "executed" for a in actions),
    }
