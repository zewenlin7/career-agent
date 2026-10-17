"""Stable hash sampling, independent of evaluation execution and user feedback truth."""

from decimal import Decimal

from career_agent.evaluation.contracts import (
    JudgeSamplingPolicy,
    SamplingDecision,
    SamplingReason,
    Subject,
)
from career_agent.evaluation.identity import digest


def decide(
    subject: Subject, policy: JudgeSamplingPolicy, trigger: SamplingReason | None = None
) -> SamplingDecision | None:
    if subject.origin == "evaluation":
        return None  # No judge-of-judge recursion, including forced requests.
    key = digest(
        {
            "subject": subject.model_dump(mode="json"),
            "policy_version": policy.version,
            "trigger": trigger,
        }
    )
    rate = policy.per_task.get(subject.task_type, policy.default_rate)
    forced = trigger is not None and trigger != "random_sample" and trigger in policy.force_rules
    bucket = Decimal(
        int(digest({"subject": str(subject.subject_id), "policy_version": policy.version}), 16)
    ) / Decimal(2**256)
    return SamplingDecision(
        subject=subject,
        policy_version=policy.version,
        effective_rate=rate,
        sampled=forced or bucket < rate,
        reason=trigger if forced else "random_sample",
        decision_key=key,
        population="targeted" if forced else "random",
    )
