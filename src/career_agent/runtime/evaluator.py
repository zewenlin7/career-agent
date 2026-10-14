"""Operational stopping decisions only; no model scoring or LLM judge."""

from typing import Literal

from career_agent.runtime.agent_contracts import ActionObservation, AgentState

Decision = Literal["continue", "replan", "wait", "finish"]


def evaluate(state: AgentState, observation: ActionObservation) -> Decision:
    if observation.disposition in {"needs_input", "decision_required"}:
        return "wait"
    if observation.reason_code in {
        "budget_exhausted",
        "active_time_exhausted",
        "tool_budget_exhausted",
        "no_progress",
    }:
        return "finish"
    if all(
        t.status in {"completed", "failed", "blocked"}
        for t in state.progress.requested_targets.values()
    ):
        return "finish"
    pending = [a for a in state.progress.actions.values() if a.status == "pending"]
    if any(
        all(state.progress.actions[d].status == "completed" for d in a.action.dependencies)
        for a in pending
    ):
        return "continue"
    # Replan only a blocked dependency topology, never retry the failed business operation.
    if pending and state.replan_count < state.limits.max_replans:
        return "replan"
    return "finish"
