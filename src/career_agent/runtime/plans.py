"""Proposals never confer authorization; validate before storing an executable plan."""

import hashlib
import json
from dataclasses import dataclass

from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import Target, WorkflowRequest
from career_agent.runtime.agent_contracts import AgentState, PlanAction, PlanProposal
from career_agent.runtime.registry import REGISTRY, validate_action_version


@dataclass(frozen=True)
class ExecutablePlan:
    """Only the deterministic validator creates this execution authorization wrapper."""

    proposal: PlanProposal


def fingerprint(action: PlanAction) -> str:
    # IDs/dependencies are not a license to repeat the same operation under a new label.
    return hashlib.sha256(
        json.dumps(
            action.model_dump(mode="json", exclude={"action_id", "dependencies"}), sort_keys=True
        ).encode()
    ).hexdigest()


def action_targets(action: PlanAction) -> list[Target]:
    return (
        ["interview_preparation"]
        if action.name == "prepare_interview"
        else list(action.args.targets)
    )


def validate_plan(plan: PlanProposal, state: AgentState, evidence: set[str]) -> ExecutablePlan:
    def reject(code: str = "invalid_plan") -> None:
        raise ModelGatewayError(code)

    if plan.plan_version != "agent-plan-v2":
        reject("plan_version_mismatch")
    if plan.bindings != state.bindings or plan.policies != state.scope:
        reject("plan_authority_violation")
    if not set(plan.requested_targets) <= set(state.scope.targets):
        reject("plan_scope_expansion")
    if len(set(plan.requested_targets)) != len(plan.requested_targets):
        reject()
    if state.progress.requested_targets and set(plan.requested_targets) != set(
        state.progress.requested_targets
    ):
        reject("plan_targets_changed")
    if not {str(x) for x in plan.evidence_refs} <= evidence:
        reject("invalid_plan_reference")
    ids = {a.action_id for a in plan.actions}
    if len(ids) != len(plan.actions):
        reject()
    if any(not set(a.dependencies) <= ids for a in plan.actions):
        reject("invalid_plan_reference")
    by_id = {a.action_id: a for a in plan.actions}
    depths: dict[object, int] = {}

    def depth(id: object, visiting: set[object]) -> int:
        if id in visiting:
            reject("plan_cycle")
        if id in depths:
            return depths[id]
        action = next(a for a in plan.actions if a.action_id == id)
        result = 1 + max((depth(d, visiting | {id}) for d in action.dependencies), default=0)
        if result > 3:
            reject("plan_depth_exceeded")
        depths[id] = result
        return result

    seen_targets: set[Target] = set()
    for action in plan.actions:
        if action.name not in REGISTRY or not set(action.dependencies) <= ids:
            reject("unregistered_action")
        validate_action_version(action)
        if len(action.dependencies) != len(set(action.dependencies)):
            reject()
        depth(action.action_id, set())
        old_action = state.progress.actions.get(action.action_id)
        if old_action and fingerprint(old_action.action) != fingerprint(action):
            reject("unstable_action_id")
        targets = action_targets(action)
        if not targets or not set(targets) <= set(plan.requested_targets):
            reject("plan_scope_expansion")
        if seen_targets & set(targets):
            reject("duplicate_target_action")
        seen_targets.update(targets)
        if action.args.resume_revision_id != state.bindings.resume_revision_id:
            if action.args.resume_revision_id is not None:
                reject("invalid_plan_reference")
        if (
            action.args.application_package_id is not None
            and action.args.application_package_id != state.bindings.application_package_id
        ):
            reject("invalid_plan_reference")
        if action.name == "prepare_application":
            if action.args.application_package_id or action.args.package_from_action:
                reject()
            try:
                WorkflowRequest(
                    profile_id=state.bindings.profile_id,
                    job_revision_id=state.bindings.job_revision_id,
                    targets=action.args.targets,
                    bindings=action.args.bindings,
                )
            except ValueError:
                reject()
            for binding in action.args.bindings.values():
                if (
                    binding.resume_revision_id
                    and binding.resume_revision_id != state.bindings.resume_revision_id
                ):
                    reject("invalid_plan_reference")
                if binding.output_of and not state.scope.allow_tailored_greeting:
                    reject("plan_authority_violation")
        else:
            if action.args.targets or action.args.bindings:
                reject()
            source = action.args.package_from_action
            if source:
                if (
                    source not in action.dependencies
                    or by_id[source].name != "prepare_application"
                    or "resume_tailoring" not in by_id[source].args.targets
                ):
                    reject("invalid_plan_reference")
                if action.args.application_package_id:
                    reject()
        # A replan cannot retry a terminal target, even with changed action args.
        for t in targets:
            old = state.progress.requested_targets.get(t)
            if old and old.status in {"completed", "failed"}:
                reject("no_progress")
        if fingerprint(action) in state.attempted_fingerprints:
            reject("no_progress")
    pending = {
        t
        for t in plan.requested_targets
        if t not in state.progress.requested_targets
        or state.progress.requested_targets[t].status in {"pending", "blocked"}
    }
    if not plan.missing_inputs and seen_targets != pending:
        reject("incomplete_plan")
    return ExecutablePlan(plan.model_copy(deep=True))
