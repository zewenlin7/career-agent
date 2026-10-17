"""Governance fails deterministically before dispatch; no provider calls in rejection cases."""

from dataclasses import replace

import pytest
from input_fixtures import valid_inputs
from pydantic import BaseModel, ValidationError

from career_agent.config import Settings
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, ModelTier
from career_agent.models.fake import FakeProvider
from career_agent.models.gateway import ModelGateway
from career_agent.models.prompts import PromptRegistry, application_prompts
from career_agent.preparation.contracts import TaskType
from career_agent.preparation.providers import POLICY, registry
from career_agent.runtime.registry import REGISTRY

TASKS = [t.value for t in TaskType] + ["goal_planning", "goal_replanning"]


@pytest.mark.parametrize("task_type", TASKS)
def test_all_tasks_have_shared_prompt_and_trace_contract(task_type):
    prompts = application_prompts()
    spec = prompts.resolve(task_type)
    ctx = ModelRequestContext(
        task_type=task_type,
        output_schema=spec.output_schema,
        workflow="synthetic",
        workflow_version="synthetic-v1",
        **spec.metadata,
    )
    trace = prompts.trace_metadata(ctx, spec.task(valid_inputs(spec)))
    assert trace.model_dump(include=set(spec.metadata)) == spec.metadata
    assert trace.workflow_version == "synthetic-v1"
    assert spec.prompt_hash == prompts.resolve(task_type).prompt_hash
    assert len(spec.prompt_hash) == 64
    assert spec.task(valid_inputs(spec)).prompt_hash == spec.task(valid_inputs(spec)).prompt_hash


def test_shared_planning_prompt_hash_and_canonical_order():
    prompts = application_prompts()
    spec = prompts.resolve("goal_planning")
    assert spec.prompt_hash == prompts.resolve("goal_replanning").prompt_hash
    reordered = dict(reversed(list(spec.input_contract.items())))
    assert replace(spec, input_contract=reordered).prompt_hash == spec.prompt_hash
    assert replace(spec, instruction=spec.instruction + "changed").prompt_hash != spec.prompt_hash
    assert replace(spec, input_schema_version="changed-v2").prompt_hash != spec.prompt_hash
    assert replace(spec, input_contract={"changed": True}).prompt_hash != spec.prompt_hash
    assert replace(spec, output_schema_version="changed-v2").prompt_hash != spec.prompt_hash
    with pytest.raises(ValueError, match="conflicting_prompt_identity"):
        PromptRegistry([spec, replace(spec, task_type="another", instruction="changed")])
    with pytest.raises(ValueError, match="duplicate_prompt_task"):
        PromptRegistry([spec, spec])


@pytest.mark.parametrize("side", ["context", "task", "both"])
@pytest.mark.parametrize(
    "field",
    [
        "prompt_name",
        "prompt_version",
        "prompt_hash",
        "input_schema_version",
        "output_schema_version",
    ],
)
async def test_mismatched_prompt_metadata_never_dispatches(side, field):
    provider = FakeProvider({})
    gateway = ModelGateway(registry(Settings(_env_file=None), False), POLICY, {"fixture": provider})
    spec = gateway.prompts.resolve("goal_planning")
    context = ModelRequestContext(
        task_type=spec.task_type, output_schema=spec.output_schema, **spec.metadata
    )
    task = spec.task(valid_inputs(spec))
    value = "0" * 64 if field == "prompt_hash" else "wrong-v1"
    if side in {"context", "both"}:
        context = context.model_copy(update={field: value})
    if side in {"task", "both"}:
        task = task.model_copy(update={field: value})
    with pytest.raises(ModelGatewayError, match="prompt_contract_mismatch"):
        await gateway.generate(context, task)
    assert provider.calls == 0


@pytest.mark.parametrize("kind", ["unregistered", "instruction", "schema", "missing_metadata"])
async def test_unregistered_task_and_contract_substitution_blocked(kind):
    provider = FakeProvider({})
    gateway = ModelGateway(registry(Settings(_env_file=None), False), POLICY, {"fixture": provider})
    spec = gateway.prompts.resolve("goal_planning")
    ctx = ModelRequestContext(
        task_type=spec.task_type, output_schema=spec.output_schema, **spec.metadata
    )
    task = spec.task(valid_inputs(spec))
    if kind == "unregistered":
        ctx = ctx.model_copy(update={"task_type": "unknown"})
    elif kind == "instruction":
        task = task.model_copy(update={"instruction": "unregistered replacement"})
    elif kind == "schema":

        class Other(BaseModel):
            value: str

        ctx = ctx.model_copy(update={"output_schema": Other})
    else:
        ctx = ctx.model_copy(update={"prompt_version": None})
    with pytest.raises(
        ModelGatewayError,
        match=(
            "unregistered_prompt_task" if kind == "unregistered" else "prompt_contract_mismatch"
        ),
    ):
        await gateway.generate(ctx, task)
    assert provider.calls == 0


@pytest.mark.parametrize("task", ["goal_planning", "goal_replanning"])
def test_planner_explicit_policy_mapping(task):
    assert POLICY.task_tiers[task] == ModelTier.STRONG
    spec = application_prompts().resolve(task)
    ctx = ModelRequestContext(task_type=task, output_schema=spec.output_schema, **spec.metadata)
    assert POLICY.select(ctx, registry(Settings(_env_file=None), False)).tier == ModelTier.STRONG


def test_registry_requires_versioned_action_contracts():
    for spec in REGISTRY.values():
        assert spec.version and spec.args_schema_version and spec.result_schema_version
        assert (
            spec.result_schema.model_fields["schema_version"].default == spec.result_schema_version
        )
        with pytest.raises(ValidationError):
            replace(spec, args_schema_version="")


@pytest.mark.parametrize("version", [None, "business-action-v999"])
def test_plan_validator_rejects_unpinned_or_incompatible_action(version):
    from test_agent_runtime_contracts import context, proposal

    from career_agent.runtime.plans import validate_plan

    state = context()
    plan = proposal(state)
    plan.actions[0].action_version = version
    with pytest.raises(ModelGatewayError, match="action_version_mismatch"):
        validate_plan(plan, state, set())


def test_trace_metadata_does_not_consume_model_input_budget():
    from career_agent.preparation.budget import input_bound

    spec = application_prompts().resolve("goal_planning")
    ctx = ModelRequestContext(
        task_type=spec.task_type, output_schema=spec.output_schema, **spec.metadata
    )
    task = spec.task({**valid_inputs(spec), "goal": "合成目标"})
    # No version metadata is sent in either adapter system/user message.
    without_metadata = task.model_copy(update={key: None for key in spec.metadata})
    assert input_bound(ctx, task) == input_bound(ctx, without_metadata)
    assert input_bound(
        ctx, spec.task({**valid_inputs(spec), "goal": "更长的合成目标"})
    ) > input_bound(ctx, task)
