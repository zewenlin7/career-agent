import asyncio
import copy
from decimal import Decimal
from uuid import uuid4

import pytest

from career_agent.config import Settings
from career_agent.evaluation.calibration import calibration_report, statistics
from career_agent.evaluation.comparison import compare_case
from career_agent.evaluation.contracts import (
    ComparisonPolicy,
    Criterion,
    EvalCase,
    EvalCheckResult,
    EvalLimits,
    EvalRunRequest,
    FaultPlan,
    JudgeOutput,
    JudgeSamplingPolicy,
    JudgeSpec,
    Subject,
    TrialResult,
)
from career_agent.evaluation.execution import ScopedProvider, SharedEvalBudget
from career_agent.evaluation.faults import FaultController, FrozenResearch
from career_agent.evaluation.fixtures import initial_cases
from career_agent.evaluation.judge import validate_judge
from career_agent.evaluation.runner import EvalRunner
from career_agent.evaluation.sampling import decide
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext
from career_agent.models.prompts import application_prompts
from career_agent.preparation.contracts import RunLimits
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.preparation.research import SearchInput

CASES = initial_cases()


@pytest.mark.parametrize(
    "case",
    [
        c
        for c in CASES
        if c.entrypoint.kind == "component" and c.entrypoint.component_kind != "business_action"
    ],
    ids=lambda c: c.case_id,
)
async def test_component_regression_cases(case):
    request = EvalRunRequest(suite_id="unit", suite_version=1)
    before = copy.deepcopy(case.model_dump(mode="json"))
    result, ops = await EvalRunner(None, Settings()).run_case(
        case, request, SharedEvalBudget(request.limits)
    )
    assert result.status == "completed", (case.case_id, result.model_dump())
    assert case.model_dump(mode="json") == before
    if case.entrypoint.component_kind == "model_task":
        assert len(ops) == 1 and ops[0].input_hash
    if case.fault_plan.faults:
        assert (
            result.output["injected_faults"][0]["injected_fault"] == case.fault_plan.faults[0].kind
        )


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing", "prompt_input_blocks_invalid"),
        ("extra", "prompt_input_blocks_invalid"),
        ("type", "prompt_input_type_invalid"),
        ("trust", "prompt_input_trust_invalid"),
        ("pii", "prompt_input_privacy_invalid"),
        ("size", "prompt_input_too_large"),
    ],
)
def test_input_contract_rejects_before_provider(mutation, code):
    spec = application_prompts().resolve("job_requirement_extraction")
    inputs = copy.deepcopy(CASES[0].model_input)
    if mutation == "missing":
        inputs["context"].pop("job")
    if mutation == "extra":
        inputs["context"]["shell"] = "rm -rf"
    if mutation == "type":
        inputs["context"]["job"] = "wrong"
    if mutation == "trust":
        inputs["trust_boundary"] = "trusted"
    if mutation == "pii":
        inputs["context"]["job"]["jd_text"] = "synthetic@example.invalid"
    if mutation == "size":
        inputs["context"]["job"]["jd_text"] = "中" * 80000
    with pytest.raises(ModelGatewayError, match=code):
        spec.task(inputs)


def test_sampling_stable_forced_and_recursion():
    subject = Subject(subject_id=uuid4(), task_type="fit_analysis", accepted_model_call_id=uuid4())
    policy = JudgeSamplingPolicy(default_rate=Decimal(0), per_task={"fit_analysis": Decimal(1)})
    first = decide(subject, policy)
    assert first == decide(subject, policy) and first.sampled and first.population == "random"
    assert not decide(subject, JudgeSamplingPolicy(default_rate=Decimal(0))).sampled
    forced = decide(subject, JudgeSamplingPolicy(default_rate=Decimal(0)), "forced_user_feedback")
    assert forced.sampled and forced.population == "targeted"
    assert (
        decide(subject.model_copy(update={"origin": "evaluation"}), policy, "forced_manual") is None
    )


def trial(*checks):
    return TrialResult(
        status="completed",
        checks=[
            EvalCheckResult(
                check_id=id,
                category="quality" if tier else "correctness",
                tier=tier,
                status="pass" if ok else "fail",
                reason_code="checked",
                material=material,
            )
            for id, tier, ok, material in checks
        ],
    )


@pytest.mark.parametrize(
    "old,new,headline,gate",
    [
        (
            [("grounding", 0, True, True), ("style", 2, False, True)],
            [("grounding", 0, False, True), ("style", 2, True, True)],
            "REGRESSED",
            "BLOCKED",
        ),
        (
            [("core", 1, True, True), ("style", 2, False, True)],
            [("core", 1, False, True), ("style", 2, True, True)],
            "REGRESSED",
            "REVIEW_REQUIRED",
        ),
        (
            [("core", 1, False, True), ("style", 2, True, False)],
            [("core", 1, True, True), ("style", 2, False, False)],
            "IMPROVED",
            "PASS",
        ),
        (
            [("a", 1, True, True), ("b", 1, False, True)],
            [("a", 1, False, True), ("b", 1, True, True)],
            "TRADEOFF",
            "REVIEW_REQUIRED",
        ),
    ],
)
def test_comparison_priority(old, new, headline, gate):
    result = compare_case([trial(*old)], [trial(*new)], ComparisonPolicy())
    assert (result["headline"], result["gate"]) == (headline, gate)
    assert len(result["deltas"]) == 2


def test_multiple_trials_insufficient_and_distribution():
    a = trial(("core", 1, True, True))
    b = trial(("core", 1, False, True))
    value = compare_case([a, a], [a, b], ComparisonPolicy(minimum_trials=3))
    assert value["headline"] == "INCONCLUSIVE"
    assert value["candidate_distribution"]["sample_count"] == 2
    assert value["candidate_distribution"]["pass_rate"] == 0.5


def test_calibration_population_confidence_and_kappa():
    rows = [
        {
            "subject_id": str(i),
            "human": rating,
            "judge": rating,
            "confidence": "high",
            "population": "random",
            "task_type": "fit_analysis",
            "judge_spec_version": "v1",
            "judge_model": "fixture",
            "criterion": "clarity",
        }
        for i, rating in enumerate(["pass", "minor_issue", "major_issue"])
    ]
    stats = statistics(rows)
    assert stats["weighted_cohens_kappa"] == 1 and stats["macro_f1"] == 1
    targeted = {**rows[0], "judge": "major_issue", "population": "targeted"}
    report = calibration_report(rows + [targeted])
    assert report["population:random"]["raw_agreement"] == 1
    assert report["population:targeted"]["raw_agreement"] == 0
    assert report["population:targeted"]["high_confidence_disagreements"] == ["0"]
    assert statistics([])["weighted_cohens_kappa"] is None


async def test_concurrent_reservation_shared_not_double_counted():
    case = CASES[0]
    spec = application_prompts().resolve(case.entrypoint.name)
    context = ModelRequestContext(
        task_type=case.entrypoint.name, output_schema=spec.output_schema, **spec.metadata
    )
    candidate = POLICY.select(context, registry(Settings(), False))
    shared = SharedEvalBudget(EvalLimits(max_model_calls=1))
    provider = ScopedProvider(
        FixtureTaskProvider(), shared, RunLimits(), [], FaultController(FaultPlan())
    )
    results = await asyncio.gather(
        *(provider.generate(candidate, context, spec.task(case.model_input)) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ModelGatewayError) for r in results) == 1
    assert shared.usage.model_calls == 1 and shared.usage.input_tokens == 100
    assert shared.usage.budget_reserved_usd == 0


async def test_frozen_search_missing_and_injected_failure():
    adapter = FrozenResearch(
        {},
        FaultController(
            FaultPlan(
                faults=[{"operation": "research_search", "attempt": 1, "kind": "tool_failure"}]
            )
        ),
    )
    with pytest.raises(ModelGatewayError, match="research_search_failed"):
        await adapter.search(SearchInput(query="synthetic"))
    with pytest.raises(ModelGatewayError, match="frozen_observation_missing"):
        await adapter.search(SearchInput(query="synthetic"))


def test_judge_insufficient_evidence_and_refs():
    spec = JudgeSpec(
        target="fit_analysis", prompt_version="v1", prompt_hash="a" * 64, model_policy_version="v1"
    )
    output = JudgeOutput(
        criteria=[
            Criterion(
                criterion=c,
                rating="insufficient_evidence",
                confidence="low",
                uncertainty_reasons=["missing_context"],
                reason="资料不足",
                evidence_refs=[],
            )
            for c in spec.criteria
        ]
    )
    validate_judge(output, spec, set())
    output.criteria[0].evidence_refs = ["invented"]
    with pytest.raises(ModelGatewayError, match="judge_evidence_invalid"):
        validate_judge(output, spec, set())


def test_structural_uuid_not_mistaken_for_contact():
    from career_agent.security.model_view import minimize, model_view

    reference = "00000000-0000-0000-0000-13800138000a"
    assert minimize(reference) == reference
    assert model_view({"fact_refs": [reference]}) == {"fact_refs": [reference]}
    assert minimize("电话 13800138000") == "电话 [PHONE]"


def test_suite_file_matches_code_managed_cases():
    import json
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/evaluation/foundation.json").read_text()
    )
    assert [EvalCase.model_validate(case).model_dump(mode="json") for case in fixture["cases"]] == [
        case.model_dump(mode="json") for case in initial_cases()
    ]


async def test_root_search_and_trial_share_ledger_without_double_counting():
    from career_agent.evaluation.execution import ScopedResearch

    root = SharedEvalBudget(EvalLimits(max_web_search_calls=1))
    faults = FaultController(FaultPlan())
    scope = ScopedProvider(FixtureTaskProvider(), root, RunLimits(), [], faults)
    adapter = ScopedResearch(
        FrozenResearch({"example": {"evidence": []}}, faults), scope, Decimal("0.008")
    )
    await adapter.search(SearchInput(query="example"))
    assert root.usage.search_calls == scope.usage.search_calls == 1
    assert root.usage.estimated_cost == scope.usage.estimated_cost == Decimal("0.008")
    assert root.usage.budget_reserved_usd == 0
    assert scope.operations[0].name == "company_search"
    assert scope.operations[0].output == {"evidence": []}
    assert scope.operations[0].provenance["input_schema_version"] == "search-input-v1"
    with pytest.raises(ModelGatewayError, match="eval_global_budget_exhausted"):
        await adapter.search(SearchInput(query="example"))
    assert root.usage.search_calls == scope.usage.search_calls == 1


@pytest.mark.parametrize(
    "task",
    ["mock_interview_turn_generation", "interview_group_debrief", "interview_overall_debrief"],
)
async def test_captured_interview_source_shape_replays_without_guessing(task):
    from career_agent.evaluation.components import validate_task

    case = next(c for c in initial_cases() if c.case_id == task + ".normal")
    request = EvalRunRequest(suite_id="test", suite_version=1)
    result, _ = await EvalRunner(None, Settings()).run_case(
        case, request, SharedEvalBudget(request.limits)
    )
    assert result.status == "completed"
    raw = case.source_snapshot["context" if task == "mock_interview_turn_generation" else "source"]
    validate_task(task, result.output["output"], case.model_input, raw)


def test_fault_trace_metadata_cannot_carry_private_text():
    from pydantic import ValidationError

    from career_agent.runtime.contracts import VersionMetadata

    with pytest.raises(ValidationError):
        VersionMetadata(injected_fault="/private/synthetic/context.txt")
    with pytest.raises(ValidationError):
        VersionMetadata(execution_origin="synthetic@example.invalid")
    assert VersionMetadata(injected_fault="timeout", execution_origin="evaluation")


async def test_old_case_missing_required_input_is_incompatible_without_provider_call():
    case = initial_cases()[0].model_copy(update={"model_input": {}})
    request = EvalRunRequest(suite_id="test", suite_version=1)
    result, operations = await EvalRunner(None, Settings()).run_case(
        case, request, SharedEvalBudget(request.limits)
    )
    assert result.status == "case_incompatible"
    assert operations == []


def test_tier_zero_minor_flag_cannot_disable_blocking():
    result = compare_case(
        [trial(("correctness", 0, True, False))],
        [trial(("correctness", 0, False, False))],
        ComparisonPolicy(),
    )
    assert result["gate"] == "BLOCKED"


def test_ordinal_quality_minor_to_major_regresses():
    before = trial(("quality", 1, False, False))
    after = trial(("quality", 1, False, True))
    before.checks[0].metadata = {"ratings": ["minor_issue"]}
    after.checks[0].metadata = {"ratings": ["major_issue"]}
    result = compare_case([before], [after], ComparisonPolicy())
    assert result["headline"] == "REGRESSED"


@pytest.mark.parametrize("status", ["pending", "running", "failed", "cancelled"])
def test_unavailable_judge_does_not_silently_pass(status):
    value = trial(("correctness", 0, True, True))
    value.output["judge_coverage"] = [{"sampled": True, "available": False, "statuses": [status]}]
    result = compare_case([value], [value], ComparisonPolicy())
    assert result["headline"] == "INCONCLUSIVE"
    assert result["correctness_passed"] is True
    assert result["candidate_distribution"]["pass_rate"] is None
    assert result["candidate_distribution"]["unavailable_trial_count"] == 1


def test_not_sampled_is_not_failed_judge():
    value = trial(("correctness", 0, True, True))
    value.output["judge_coverage"] = [{"sampled": False, "available": True, "statuses": []}]
    assert compare_case([value], [value], ComparisonPolicy())["gate"] == "PASS"


async def test_deadline_cancels_inflight_and_retry_keeps_unknown_reservation():
    class Slow:
        async def generate(self, candidate, context, task):
            await asyncio.sleep(10)

    case = CASES[0]
    spec = application_prompts().resolve(case.entrypoint.name)
    context = ModelRequestContext(
        task_type=case.entrypoint.name, output_schema=spec.output_schema, **spec.metadata
    )
    candidate = POLICY.select(context, registry(Settings(), False))
    shared = SharedEvalBudget(EvalLimits(), max_seconds=0.02)
    scope = ScopedProvider(Slow(), shared, RunLimits(), [], FaultController(FaultPlan()))
    with pytest.raises(ModelGatewayError, match="eval_deadline_exceeded"):
        await scope.generate(candidate, context, spec.task(case.model_input))
    assert shared.usage.model_calls == 1
    assert shared.usage.unknown_usage_attempts == 1
    assert scope.usage.model_dump() == shared.usage.model_dump()
    before = shared.usage.model_dump()
    with pytest.raises(ModelGatewayError, match="eval_global_budget_exhausted"):
        await scope.generate(candidate, context, spec.task(case.model_input))
    assert shared.usage.model_dump() == before


async def test_search_deadline_admission_and_inflight_settlement():
    from career_agent.evaluation.execution import ScopedResearch

    class SlowSearch:
        async def search(self, query):
            await asyncio.sleep(10)

    shared = SharedEvalBudget(EvalLimits(), max_seconds=0.02)
    scope = ScopedProvider(
        FixtureTaskProvider(), shared, RunLimits(), [], FaultController(FaultPlan())
    )
    adapter = ScopedResearch(SlowSearch(), scope, Decimal("0.008"))
    with pytest.raises(ModelGatewayError, match="eval_deadline_exceeded"):
        await adapter.search(SearchInput(query="synthetic"))
    assert shared.usage.search_calls == 1
    assert shared.usage.budget_reserved_usd == Decimal("0.008")
    with pytest.raises(ModelGatewayError, match="eval_global_budget_exhausted"):
        await adapter.search(SearchInput(query="synthetic"))
    assert shared.usage.search_calls == 1


async def test_origin_reexecution_pins_available_noncurrent_model():
    case = CASES[0].model_copy(deep=True)
    spec = application_prompts().resolve(case.entrypoint.name)
    settings = Settings(live_enabled=False)
    candidates = registry(settings, False)
    from career_agent.models.contracts import ModelTier

    original = next(c for c in candidates if c.tier == ModelTier.STRONG)
    case.origin_provenance = {
        **spec.metadata,
        "provider": original.provider,
        "model": original.model,
        "model_policy_version": POLICY.version,
        "generation_parameters": {"max_output_tokens": 1234},
    }
    from career_agent.models.gateway import ModelGateway, ModelPolicy

    origin_gateway = ModelGateway(
        [original],
        ModelPolicy(POLICY.version, {case.entrypoint.name: original.tier}),
        {original.provider: FixtureTaskProvider()},
    )
    origin_context = ModelRequestContext(
        task_type=case.entrypoint.name,
        output_schema=spec.output_schema,
        max_output_tokens=1234,
        **spec.metadata,
    )
    prepared = await origin_gateway.prepare(origin_context, spec.task(case.model_input))
    case.origin_provenance["control_contract"] = prepared.control_snapshot
    origin_gateway.cancel_prepared(prepared)
    runner = EvalRunner(None, settings)
    result, operations = await runner.run_case(
        case,
        EvalRunRequest(
            suite_id="test", suite_version=1, mode="origin_reexecution", explicit_diagnostic=True
        ),
        SharedEvalBudget(EvalLimits()),
    )
    assert result.status == "completed"
    assert operations[0].provenance["model"] == original.model
    assert operations[0].provenance["generation_parameters"] == {"max_output_tokens": 1234}


def test_calibration_repeated_pairs_do_not_reweight_subject():
    base = dict(
        subject_id="a",
        human="pass",
        judge="pass",
        confidence="high",
        population="random",
        task_type="fit",
        judge_spec_version="v1",
        judge_model="fixture",
        criterion="grounding",
    )
    pairs = [
        {**base, "annotation_id": str(a), "judge_id": str(j)} for a in range(3) for j in range(4)
    ]
    pairs.append({**base, "subject_id": "b", "human": "major_issue"})
    report = calibration_report(pairs)
    assert len(report["pair_details"]) == 13
    assert report["unique_subject_count"] == 2
    assert report["population:random"]["sample_count"] == 2
    assert report["population:random"]["raw_agreement"] == 0.5


@pytest.mark.parametrize("status", ["pending", "running", "failed", "cancelled", "not_sampled"])
async def test_persisted_judge_coverage_enters_comparison(status):
    from types import SimpleNamespace

    from career_agent.evaluation.reports import trial_with_quality

    call_id = uuid4()
    sampled = status != "not_sampled"
    responses = iter(
        [
            [call_id],
            [
                SimpleNamespace(
                    id=uuid4(),
                    data={
                        "subject": {
                            "accepted_model_call_id": str(call_id),
                            "task_type": "fit_analysis",
                        },
                        "sampled": sampled,
                        "population": "random",
                    },
                )
            ],
            [SimpleNamespace(status=status, result=None)] if sampled else [],
        ]
    )

    class Session:
        async def scalars(self, query):
            return next(responses)

    value = trial(("grounding", 0, True, True))
    result = await trial_with_quality(
        Session(), SimpleNamespace(id=uuid4(), result=value.model_dump(mode="json"))
    )
    report = compare_case([result], [result], ComparisonPolicy())
    assert report["headline"] == ("INCONCLUSIVE" if sampled else "UNCHANGED")
    assert report["correctness_passed"] is True


def test_missing_judge_does_not_hide_blocking_correctness():
    before = trial(("grounding", 0, True, False))
    after = trial(("grounding", 0, False, False))
    after.output["judge_coverage"] = [{"available": False}]
    assert compare_case([before], [after], ComparisonPolicy())["gate"] == "BLOCKED"


async def test_cancelled_call_retains_unknown_usage_once():
    entered = asyncio.Event()

    class Cancellable:
        async def generate(self, candidate, context, task):
            entered.set()
            await asyncio.Event().wait()

    case = CASES[0]
    spec = application_prompts().resolve(case.entrypoint.name)
    context = ModelRequestContext(
        task_type=case.entrypoint.name, output_schema=spec.output_schema, **spec.metadata
    )
    candidate = POLICY.select(context, registry(Settings(), False))
    shared = SharedEvalBudget(EvalLimits())
    scope = ScopedProvider(Cancellable(), shared, RunLimits(), [], FaultController(FaultPlan()))
    pending = asyncio.create_task(scope.generate(candidate, context, spec.task(case.model_input)))
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert shared.usage.model_calls == 1
    assert shared.usage.unknown_usage_attempts == 1
    assert shared.usage.model_dump() == scope.usage.model_dump()


@pytest.mark.parametrize(
    "source",
    [
        {},
        {
            "captured_source_version": "captured-source-v1",
            "replay": {"version": "captured-replay-v1"},
        },
        {
            "captured_source_version": "captured-source-v1",
            "replay": {
                "version": "captured-replay-v1",
                "closure_complete": True,
                "rows": [],
                "request": {"goal": "合成目标"},
                "evaluation_clock": "2026-01-01T00:00:00Z",
                "agent_goal_compatible": False,
            },
        },
    ],
)
def test_incomplete_capture_never_guesses_replay_inputs(source):
    from career_agent.evaluation.captured import replay_source

    with pytest.raises(ModelGatewayError, match="case_incompatible"):
        replay_source(source)


def test_paid_replay_requires_explicit_injection_and_manifest_tracks_gateway():
    from career_agent.evaluation.identity import candidate_config
    from career_agent.models.gateway import ModelGateway

    settings = Settings(live_enabled=True)
    gateway = ModelGateway(registry(settings, True), POLICY, {"openai": FixtureTaskProvider()})
    with pytest.raises(ModelGatewayError, match="eval_live_mode_forbidden"):
        EvalRunner(None, settings, gateway)
    with pytest.raises(ModelGatewayError, match="eval_live_mode_forbidden"):
        EvalRunner(
            None,
            settings.model_copy(update={"live_enabled": False}),
            gateway,
            allow_paid_models=True,
        )
    runner = EvalRunner(None, settings, gateway, allow_paid_models=True)
    manifest = candidate_config(settings, runner.gateway)
    assert all(c["provider"] == "openai" for c in manifest.model_policy["candidates"])
    assert manifest.config_hash != candidate_config(settings).config_hash
    default = EvalRunner(None, settings)
    assert all(c.provider == "fixture" for c in default.gateway.registry)


async def test_trial_automatic_policy_matches_candidate_manifest(monkeypatch):
    from career_agent.evaluation.identity import candidate_config
    from career_agent.models.control import scenario
    from career_agent.models.control.recovery_contracts import AutomaticPolicy

    settings = Settings(_env_file=None, automatic_control=AutomaticPolicy(cooldown_seconds=99))
    runner = EvalRunner(None, settings)
    manifest = candidate_config(settings, runner.gateway)
    actual = []
    original = scenario.isolated_controller

    def observe(policy, fixture, automatic_policy=None):
        controller = original(policy, fixture, automatic_policy)
        actual.append(controller.automatic_policy.model_dump(mode="json"))
        return controller

    monkeypatch.setattr(scenario, "isolated_controller", observe)
    case = next(c for c in CASES if c.entrypoint.component_kind == "model_task").model_copy(
        deep=True
    )
    request = EvalRunRequest(suite_id="unit", suite_version=1)
    result, _ = await runner.run_case(case, request, SharedEvalBudget(request.limits))
    assert result.status == "completed"
    assert actual == [manifest.model_policy["automatic_control"]]
    case.control_scenario.automatic_policy = AutomaticPolicy()
    result, operations = await runner.run_case(case, request, SharedEvalBudget(request.limits))
    assert result.status == "case_incompatible" and operations == []
