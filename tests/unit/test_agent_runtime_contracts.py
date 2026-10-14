from uuid import uuid4

import pytest
from pydantic import ValidationError

from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import TargetOutcome
from career_agent.runtime.agent_contracts import (
    ActionArgs,
    ActionObservation,
    ActionProgress,
    AgentState,
    AuthorizedScope,
    Bindings,
    PlanAction,
    PlanProposal,
)
from career_agent.runtime.budget import RuntimeBudget
from career_agent.runtime.evaluator import evaluate
from career_agent.runtime.plans import fingerprint, validate_plan


def context():
    scope = AuthorizedScope(
        targets=["fit_analysis", "resume_tailoring", "greeting_generation", "interview_preparation"]
    )
    return AgentState(
        run_id=uuid4(),
        goal_id=uuid4(),
        bindings=Bindings(profile_id=uuid4(), job_revision_id=uuid4(), resume_revision_id=uuid4()),
        scope=scope,
        original_scope=scope,
    )


def proposal(state):
    return PlanProposal(
        requested_targets=["fit_analysis"],
        bindings=state.bindings,
        policies=state.scope,
        actions=[
            PlanAction(
                action_id=uuid4(),
                name="prepare_application",
                args=ActionArgs(targets=["fit_analysis"]),
            )
        ],
    )


@pytest.mark.parametrize("kind", ["cycle", "unknown_dependency", "repeat", "evidence", "output_of"])
def test_validator_rejects_unauthorized_or_no_progress(kind):
    state = context()
    plan = proposal(state)
    if kind == "cycle":
        plan.actions[0].dependencies = [plan.actions[0].action_id]
    if kind == "unknown_dependency":
        plan.actions[0].dependencies = [uuid4()]
    if kind == "repeat":
        state.attempted_fingerprints = [fingerprint(plan.actions[0])]
    if kind == "evidence":
        plan.evidence_refs = [uuid4()]
    if kind == "output_of":
        plan.requested_targets = ["resume_tailoring", "greeting_generation"]
        plan.actions[0].args = ActionArgs(
            targets=plan.requested_targets,
            bindings={"greeting_generation": {"output_of": "resume_tailoring"}},
        )
    with pytest.raises(ModelGatewayError):
        validate_plan(plan, state, set())


def test_four_actions_and_dependency_depth():
    state = context()
    plan = proposal(state)
    actions = []
    for target in state.scope.targets:
        actions.append(
            PlanAction(
                action_id=uuid4(),
                name="prepare_application"
                if target != "interview_preparation"
                else "prepare_interview",
                args=ActionArgs(targets=[target] if target != "interview_preparation" else []),
                dependencies=[actions[-1].action_id] if actions else [],
            )
        )
    plan.actions = actions
    plan.requested_targets = state.scope.targets
    with pytest.raises(ModelGatewayError, match="plan_depth_exceeded"):
        validate_plan(plan, state, set())
    with pytest.raises(ValidationError):
        PlanProposal.model_validate({**plan.model_dump(), "actions": actions + [actions[0]]})


def test_evaluator_wait_continue_replan_finish():
    state = context()
    plan = proposal(state)
    a = plan.actions[0]
    obs = ActionObservation(action_id=a.action_id, disposition="needs_input")
    assert evaluate(state, obs) == "wait"
    state.progress.requested_targets = {"fit_analysis": TargetOutcome()}
    state.progress.actions[a.action_id] = ActionProgress(action=a)
    obs.disposition = "executed"
    assert evaluate(state, obs) == "continue"
    dep = uuid4()
    a.dependencies = [dep]
    state.progress.actions[dep] = ActionProgress(
        action=a.model_copy(update={"action_id": dep}), status="failed"
    )
    assert evaluate(state, obs) == "replan"
    state.replan_count = 2
    assert evaluate(state, obs) == "finish"
    obs.reason_code = "budget_exhausted"
    assert evaluate(state, obs) == "finish"


def test_time_and_tool_limits():
    state = context()
    budget = RuntimeBudget(state, lambda: 0)
    with pytest.raises(ModelGatewayError, match="active_time_exhausted"):
        budget.check_time()
    budget = RuntimeBudget(state, lambda: 1)
    state.limits.max_tool_calls = 1
    budget.tool()
    with pytest.raises(ModelGatewayError, match="tool_budget_exhausted"):
        budget.tool()
    assert state.usage.tool_calls == 1


def test_dangling_dependency_in_later_node_is_structured_failure():
    state = context()
    plan = proposal(state)
    second = PlanAction(
        action_id=uuid4(),
        name="prepare_application",
        args=ActionArgs(targets=["greeting_generation"]),
        dependencies=[uuid4()],
    )
    plan.actions[0].dependencies = [second.action_id]
    plan.actions.append(second)
    plan.requested_targets.append("greeting_generation")
    with pytest.raises(ModelGatewayError, match="invalid_plan_reference"):
        validate_plan(plan, state, set())


def test_shared_unknown_reservation_cannot_reset_in_child():
    from decimal import Decimal

    from career_agent.models.contracts import ModelCandidate
    from career_agent.preparation.contracts import Accounting
    from career_agent.runtime.budget import run_limits

    state = context()
    state.limits.max_model_calls = 1
    candidate = ModelCandidate(
        provider="fixture",
        model="fixture",
        tier="strong",
        capabilities={"structured_output"},
        allowed_privacy={"synthetic"},
        input_cost_per_million=Decimal("1"),
        output_cost_per_million=Decimal("2"),
    )
    budget = RuntimeBudget(state, lambda: 10)
    child = Accounting()
    ledger = budget.ledger(run_limits(state, remaining=True), child)
    reserved = ledger.reserve_model(candidate, 100, 100)
    usage = ledger.settle(reserved, None)
    assert usage.estimated_cost is None
    assert state.usage.budget_reserved_usd == child.budget_reserved_usd == Decimal("0.0003")
    assert state.usage.model_calls == 1
    # A fresh child object still cannot acquire fresh root credit.
    next_child = budget.ledger(run_limits(state), Accounting())
    with pytest.raises(ModelGatewayError, match="budget_exhausted"):
        next_child.reserve_model(candidate, 100, 100)
    assert state.usage.model_calls == 1


def test_shared_search_tool_limits_and_unknown_cash_cost():
    from decimal import Decimal

    from career_agent.preparation.contracts import Accounting
    from career_agent.runtime.budget import run_limits

    state = context()
    state.limits.max_web_search_calls = 1
    root = RuntimeBudget(state, lambda: 10)
    child = root.ledger(run_limits(state), Accounting())
    reserved = child.reserve_search(Decimal("0.008"))
    usage = child.settle_search(reserved, succeeded=True)
    assert state.usage.search_calls == 1
    assert state.usage.tool_calls == 1
    assert usage.actual_billed_cost_usd is None
    assert usage.billing_tier == "unknown"
    with pytest.raises(ModelGatewayError, match="budget_exhausted"):
        root.ledger(run_limits(state), Accounting()).reserve_search(Decimal("0.008"))


async def test_active_time_bounds_provider_await():
    import asyncio

    budget = RuntimeBudget(context(), lambda: 0.001)

    class Slow:
        async def generate(self, *args):
            await asyncio.sleep(1)
            raise AssertionError("must not finish")

    with pytest.raises(ModelGatewayError, match="active_time_exhausted"):
        await budget.generate(Slow(), None, None)
