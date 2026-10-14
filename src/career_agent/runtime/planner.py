"""Canonical structured planner prompt and deterministic fixture provider behavior."""

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from career_agent.runtime.agent_contracts import ActionArgs, Bindings, PlanAction, PlanProposal
from career_agent.runtime.registry import REGISTRY


def fixture_plan(context: dict[str, Any]) -> dict[str, Any]:
    """Offline fixture router, not a claim of natural-language understanding quality."""
    bindings = Bindings.model_validate(context["bindings"])
    scope = context["authorized_scope"]
    requested = context["progress"].get("requested_targets") or {}
    if requested:
        targets = list(requested)
    else:
        aliases = {
            "fit_analysis": ("匹配", "分析", "fit"),
            "resume_tailoring": ("简历", "tailor", "resume"),
            "greeting_generation": ("招呼", "问候", "greeting"),
            "interview_preparation": ("面试", "interview"),
        }
        goal = context["goal"].lower()
        targets = [t for t in scope["targets"] if any(word in goal for word in aliases[t])]
        if not targets:
            targets = list(scope["targets"])
            return PlanProposal(
                requested_targets=targets,
                actions=[],
                bindings=bindings,
                policies=scope,
                missing_inputs=["goal_clarification_required"],
                reason_code="input_required",
            ).model_dump(mode="json")
    pending = [
        t
        for t in targets
        if requested.get(t, {}).get("status", "pending") in {"pending", "blocked"}
    ]
    missing = []
    if (
        any(t in pending for t in ("resume_tailoring", "greeting_generation"))
        and not bindings.resume_revision_id
    ):
        missing.append("resume_selection_required")
    apps = [t for t in pending if t != "interview_preparation"]
    actions = []
    groups = (
        [[t] for t in apps]
        if "分别" in context["goal"] and not scope["allow_tailored_greeting"]
        else [apps]
    )
    for group in groups:
        if not group:
            continue
        args = ActionArgs(targets=group, resume_revision_id=bindings.resume_revision_id)
        if scope["allow_tailored_greeting"] and {"resume_tailoring", "greeting_generation"} <= set(
            group
        ):
            from career_agent.preparation.contracts import ResumeBinding

            args.bindings = {"greeting_generation": ResumeBinding(output_of="resume_tailoring")}
        id = uuid5(NAMESPACE_URL, "prepare_application" + args.model_dump_json())
        actions.append(
            PlanAction(
                action_id=id,
                name="prepare_application",
                action_version=REGISTRY["prepare_application"].version,
                args=args,
            )
        )
    if "interview_preparation" in pending:
        package = bindings.application_package_id
        source = next((a.action_id for a in actions if "resume_tailoring" in a.args.targets), None)
        if not package and not source:
            missing.append("application_package_required")
        args = ActionArgs(
            application_package_id=package, package_from_action=None if package else source
        )
        id = uuid5(NAMESPACE_URL, "prepare_interview" + args.model_dump_json())
        actions.append(
            PlanAction(
                action_id=id,
                name="prepare_interview",
                action_version=REGISTRY["prepare_interview"].version,
                args=args,
                dependencies=[source] if source and not package else [],
            )
        )
    return PlanProposal(
        requested_targets=targets,
        actions=actions,
        bindings=bindings,
        policies=scope,
        missing_inputs=missing,
        reason_code="input_required" if missing else "goal_routed",
        evidence_refs=[UUID(x["id"]) for x in context.get("artifacts", [])][:12],
    ).model_dump(mode="json")
