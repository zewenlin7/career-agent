"""Offline-default replay; paid models require explicit injected gateway authorization."""

import asyncio
import time
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import require
from career_agent.config import Settings
from career_agent.domain.rules import DomainError
from career_agent.evaluation import entities as q
from career_agent.evaluation.checks import evaluate, trajectory
from career_agent.evaluation.components import VERSIONS, deterministic, validate_task
from career_agent.evaluation.contracts import (
    CandidateConfig,
    EvalCase,
    EvalRunRequest,
    EvalSuite,
    OperationSnapshot,
    TrialResult,
)
from career_agent.evaluation.execution import (
    FROZEN_CLOCK,
    ScopedProvider,
    ScopedResearch,
    SharedEvalBudget,
)
from career_agent.evaluation.faults import FaultController, FaultProvider, FrozenResearch
from career_agent.evaluation.identity import candidate_config, digest
from career_agent.evaluation.recording import EVALUATION_ORIGIN
from career_agent.evaluation.sandbox import bootstrap, replace_refs, sandbox
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, PrivacyClass
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.observation_store import IDENTITY_VERSION, ReuseDecision
from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
from career_agent.runtime.contracts import Budget, Usage


class EvalRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        gateway: ModelGateway | None = None,
        *,
        allow_paid_models: bool = False,
    ) -> None:
        self.sessions, self.settings = sessions, settings.model_copy(deep=True)
        self.gateway = gateway or ModelGateway(
            registry(settings, False), POLICY, {"fixture": FixtureTaskProvider()}
        )
        if gateway is None:
            self.gateway.controller.automatic_policy = settings.automatic_control.model_copy(
                deep=True
            )
        self.allow_paid_models = allow_paid_models
        if any(c.provider != "fixture" for c in self.gateway.registry) and not (
            allow_paid_models
            and settings.live_enabled
            and all(c.provider == "openai" for c in self.gateway.registry)
        ):
            raise ModelGatewayError("eval_live_mode_forbidden")

    async def create(self, request: EvalRunRequest) -> UUID:
        if request.mode == "origin_reexecution" and not request.explicit_diagnostic:
            raise DomainError("explicit_origin_reexecution_required")
        async with self.sessions.begin() as session:
            suite = await session.scalar(
                select(q.EvalSuiteRow).where(
                    q.EvalSuiteRow.suite_key == request.suite_id,
                    q.EvalSuiteRow.version == request.suite_version,
                )
            )
            if suite is None:
                raise DomainError("suite_not_found", 404)
            row = q.EvalRunRow(
                suite_id=suite.id,
                request=request.model_dump(mode="json"),
                candidate=candidate_config(self.settings, self.gateway).model_dump(mode="json"),
            )
            session.add(row)
            await session.flush()
            for member in EvalSuite.model_validate(suite.data).members:
                case = await session.scalar(
                    select(q.EvalCaseRow).where(
                        q.EvalCaseRow.case_key == member.case_id,
                        q.EvalCaseRow.version == member.case_version,
                    )
                )
                if case is None:
                    raise DomainError("suite_member_missing")
                for index in range(request.trials):
                    session.add(
                        q.EvalTrialRow(run_id=row.id, case_id=case.id, trial_index=index + 1)
                    )
            return row.id

    async def execute(self, id: UUID) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            row = await require(session, q.EvalRunRow, id, lock=True)
            if row.status != "pending":
                raise DomainError("eval_run_already_started")
            config = CandidateConfig.model_validate(row.candidate)
            request = EvalRunRequest.model_validate(row.request)
            row.status = "running"
            row.started_at = e.utcnow()
            trials = list(
                await session.scalars(
                    select(q.EvalTrialRow.id)
                    .where(q.EvalTrialRow.run_id == id)
                    .order_by(q.EvalTrialRow.created_at, q.EvalTrialRow.id)
                )
            )
        budget = SharedEvalBudget(request.limits, request.limits.max_active_seconds)
        semaphore = asyncio.Semaphore(request.max_concurrent_trials)
        abort: str | None = None

        async def trial(trial_id: UUID) -> None:
            nonlocal abort
            async with semaphore:
                async with self.sessions() as session:
                    run = await require(session, q.EvalRunRow, id)
                    if run.status == "cancelled":
                        abort = "explicit_cancellation"
                if candidate_config(self.settings, self.gateway).config_hash != config.config_hash:
                    abort = "candidate_config_drift"
                if budget.exhausted:
                    abort = "global_budget_exhausted"
                if abort:
                    result = TrialResult(status="cancelled", reason_code=abort)
                    operations: list[OperationSnapshot] = []
                else:
                    async with self.sessions.begin() as session:
                        stored = await require(session, q.EvalTrialRow, trial_id)
                        stored.status = "running"
                        case_row = await require(session, q.EvalCaseRow, stored.case_id)
                        case = EvalCase.model_validate(case_row.data)
                        if (
                            digest(
                                {
                                    key: value
                                    for key, value in case_row.data.items()
                                    if key != "content_hash"
                                }
                            )
                            != case_row.content_hash
                        ):
                            abort = "corrupt_case_hash"
                    if abort:
                        result = TrialResult(status="case_incompatible", reason_code=abort)
                        operations = []
                    else:
                        try:
                            result, operations = await self.run_case(
                                case, request, budget, budget_owner_refs=(id, trial_id)
                            )
                        except Exception:
                            abort = "eval_infrastructure_error"
                            result = TrialResult(status="failed", reason_code=abort)
                            operations = []
                    if (
                        candidate_config(self.settings, self.gateway).config_hash
                        != config.config_hash
                    ):
                        abort = "candidate_config_drift"
                        result = TrialResult(status="failed", reason_code=abort)
                async with self.sessions.begin() as session:
                    stored = await require(session, q.EvalTrialRow, trial_id, lock=True)
                    stored.status = result.status
                    stored.result = result.model_dump(mode="json")
                    for op in operations:
                        from career_agent.evaluation.trace import persist_operation

                        control = op.provenance.get("control_metadata", {})
                        if self.gateway.durable and control.get("attempt_id"):
                            self.gateway.durable.watch(session, UUID(control["attempt_id"]))
                        call_id = await persist_operation(session, op)
                        if op.accepted_model_call_id and op.output_ref is None:
                            op.output_ref = op.operation_id
                        session.add(
                            q.InvocationRow(
                                id=op.operation_id,
                                trial_id=trial_id,
                                model_call_id=call_id,
                                data=op.model_dump(mode="json"),
                            )
                        )

        # At most configured active trials, not unbounded provider calls.
        queue = asyncio.Queue[UUID]()
        for trial_id in trials:
            queue.put_nowait(trial_id)

        async def worker() -> None:
            while not queue.empty():
                await trial(queue.get_nowait())

        try:
            await asyncio.gather(
                *(worker() for _ in range(min(request.max_concurrent_trials, len(trials))))
            )
        except asyncio.CancelledError:
            abort = "explicit_cancellation"
            raise
        finally:
            async with self.sessions.begin() as session:
                run = await require(session, q.EvalRunRow, id, lock=True)
                if budget.exhausted:
                    abort = "global_budget_exhausted"
                run.status = (
                    "cancelled"
                    if abort == "explicit_cancellation"
                    else "failed"
                    if abort
                    else "completed"
                )
                run.reason_code = abort
                run.finished_at = e.utcnow()
                completed_trials = list(
                    await session.scalars(select(q.EvalTrialRow).where(q.EvalTrialRow.run_id == id))
                )
                run.summary = {
                    "statuses": {
                        status: sum(t.status == status for t in completed_trials)
                        for status in {t.status for t in completed_trials}
                    },
                    "usage": budget.usage.model_dump(mode="json"),
                    "trial_count": len(trials),
                    "execution_seconds": time.monotonic() - budget.started,
                }
        return await self.view(id)

    async def run_case(
        self,
        case: EvalCase,
        request: EvalRunRequest,
        budget: SharedEvalBudget,
        *,
        budget_owner_refs: tuple[UUID, ...] = (),
    ) -> tuple[TrialResult, list[OperationSnapshot]]:
        operations: list[OperationSnapshot] = []
        faults = FaultController(case.fault_plan)
        from career_agent.models.control.scenario import ControlScenario, isolated_controller

        scopes = {
            name: ScopedProvider(
                FaultProvider(adapter, faults), budget, request.per_trial_limits, operations, faults
            )
            for name, adapter in self.gateway.adapters.items()
        }
        scoped = next(iter(scopes.values()))
        # Every provider projects into the same trial ledger, never independent full budgets.
        for scope in scopes.values():
            scope.usage = scoped.usage
            scope.ledger = scoped.ledger
        try:
            trial_controller = (
                self.gateway.controller
                if self.allow_paid_models
                else isolated_controller(
                    self.gateway.controller.policy,
                    case.control_scenario,
                    self.gateway.controller.automatic_policy,
                )
            )
        except ModelGatewayError as exc:
            return TrialResult(status="case_incompatible", reason_code=exc.code), operations
        gateway = ModelGateway(
            self.gateway.registry,
            self.gateway.policy,
            {name: scope for name, scope in scopes.items()},
            self.gateway.prompts,
            controller=trial_controller,
            durable=self.gateway.durable if self.allow_paid_models else None,
            budget_owner_refs=budget_owner_refs,
            traffic_class="evaluation",
        )
        start = time.monotonic()
        token = FROZEN_CLOCK.set(case.evaluation_clock)
        origin = EVALUATION_ORIGIN.set(True)
        result: dict[str, Any] = {}
        reason = None
        incompatible = False
        origin_output_limit = 6000
        try:
            if self.allow_paid_models and (
                case.fault_plan.faults or case.control_scenario != ControlScenario()
            ):
                # Artificial feedback/failures may exercise isolated offline controllers,
                # never poison a real quota controller shared with user traffic.
                raise ModelGatewayError("eval_live_control_scenario_forbidden")
            if request.mode == "origin_reexecution":
                original = case.origin_provenance
                if (original.get("provider"), original.get("model")) not in {
                    (c.provider, c.model) for c in gateway.registry
                }:
                    raise ModelGatewayError("origin_model_unavailable")
                if case.entrypoint.component_kind != "model_task":
                    raise ModelGatewayError("origin_config_unavailable")
                spec = gateway.prompts.resolve(case.entrypoint.name)
                parameters = original.get("generation_parameters", {})
                if (
                    any(original.get(key) != value for key, value in spec.metadata.items())
                    or original.get("model_policy_version") != POLICY.version
                    or set(parameters) != {"max_output_tokens"}
                    or type(parameters.get("max_output_tokens")) is not int
                    or not 1 <= parameters["max_output_tokens"] <= 32768
                ):
                    raise ModelGatewayError("origin_config_unavailable")
                from career_agent.models.contracts import ModelCandidate
                from career_agent.models.control.contracts import (
                    AttemptSelection,
                    ControlPolicy,
                    TaskControlPolicy,
                )
                from career_agent.models.control.controller import Controller
                from career_agent.models.gateway import ModelPolicy

                contract = original.get("control_contract")
                if (
                    not isinstance(contract, dict)
                    or contract.get("schema_version") != "attempt-control-snapshot-v1"
                ):
                    raise ModelGatewayError("origin_config_unavailable")
                try:
                    origin_policy = TaskControlPolicy.model_validate(contract["task_policy"])
                    origin_controller = ControlPolicy.model_validate(contract["controller_policy"])
                    selected = ModelCandidate.model_validate(contract["candidate"])
                    origin_selection = AttemptSelection.model_validate(contract["selection"])
                    approved = sorted(
                        origin_policy.candidates, key=lambda item: (item.priority, item.route)
                    )
                    effective = contract.get("effective_state")
                    if effective and (
                        effective.get("automatic")
                        or effective.get("overrides")
                        or effective.get("kill")
                        or effective.get("global_kill")
                    ):
                        raise ModelGatewayError("origin_config_unavailable")
                    if (
                        origin_controller.implementation_version
                        != gateway.controller.policy.implementation_version
                        or origin_selection.routing_role != "primary"
                        or origin_selection.attempt_index != 1
                        or origin_selection.circuit_disposition != "closed"
                        or origin_selection.task_type != case.entrypoint.name
                        or origin_selection.provider != selected.provider
                        or origin_selection.model != selected.model
                        or origin_selection.route != f"{selected.provider}:{selected.model}"
                        or origin_selection.model_policy_version != original["model_policy_version"]
                        or origin_selection.control_policy_version != origin_controller.version
                        or origin_selection.output_policy_version != origin_policy.output.version
                        or origin_selection.qualification_ref != approved[0].qualification_ref
                        or selected.provider != original["provider"]
                        or selected.model != original["model"]
                        or approved[0].route != f"{selected.provider}:{selected.model}"
                        or origin_selection.task_policy_version != origin_policy.version
                        or parameters["max_output_tokens"] != origin_selection.hard_output_tokens
                    ):
                        raise ModelGatewayError("origin_config_unavailable")
                except (KeyError, TypeError, ValidationError):
                    raise ModelGatewayError("origin_config_unavailable") from None
                # Reconstruct the exact original route/config. Historical overflow/probe state
                # cannot be inferred: those origins fail closed above, never use current routing.
                if self.allow_paid_models and (
                    origin_controller != gateway.controller.policy
                    or origin_selection.traffic_class != "evaluation"
                ):
                    raise ModelGatewayError("origin_config_unavailable")
                gateway = ModelGateway(
                    [selected],
                    ModelPolicy(
                        original["model_policy_version"], {}, {case.entrypoint.name: origin_policy}
                    ),
                    gateway.adapters,
                    gateway.prompts,
                    controller=gateway.controller
                    if self.allow_paid_models
                    else Controller(origin_controller, gateway.controller.clock),
                    durable=gateway.durable if self.allow_paid_models else None,
                    budget_owner_refs=budget_owner_refs,
                    traffic_class=origin_selection.traffic_class,
                )
                origin_output_limit = parameters["max_output_tokens"]
            entry = case.entrypoint
            if entry.kind == "component" and entry.component_kind == "model_task":
                if case.model_input is None:
                    raise ModelGatewayError("case_incompatible")
                spec = gateway.prompts.resolve(entry.name)
                if entry.name in {"interview_group_debrief", "interview_overall_debrief"}:
                    block = case.model_input.get("group", case.model_input.get("source", {}))
                    if not isinstance(block, dict) or any(
                        "number" not in item for item in block.get("entries", [])
                    ):
                        raise ModelGatewayError("case_incompatible")
                ctx = ModelRequestContext(
                    task_type=entry.name,
                    workflow="evaluation",
                    workflow_version="eval-v1",
                    output_schema=spec.output_schema,
                    privacy_class=PrivacyClass.SYNTHETIC,
                    max_output_tokens=origin_output_limit,
                    budget_remaining=Budget(cost_limit=request.per_trial_limits.max_estimated_cost),
                    **spec.metadata,
                )
                answer = await gateway.generate(ctx, spec.task(case.model_input))
                output = answer.validated_output.model_dump(mode="json")
                validate_task(entry.name, output, case.model_input, case.source_snapshot)
                result = {"status": "completed", "valid": True, "output": output}
            elif entry.kind == "component" and entry.component_kind == "deterministic_operation":
                fault = faults.next(entry.name) if entry.name != "research_search" else None
                if fault:
                    raise ModelGatewayError(
                        "revision_conflict" if fault.kind == "cas_conflict" else "budget_exhausted"
                    )
                if entry.name == "research_search":
                    from career_agent.preparation.research import SearchInput

                    adapter = ScopedResearch(
                        FrozenResearch(case.frozen_external_observations, faults),
                        scoped,
                        self.settings.search_cost_per_call,
                    )
                    await adapter.search(SearchInput.model_validate(case.source_snapshot))
                    result = {"status": "completed", "valid": True}
                else:
                    result = deterministic(entry.name, case.source_snapshot)
                operations.append(
                    OperationSnapshot(
                        kind="deterministic_operation",
                        name=entry.name,
                        version=VERSIONS[entry.name],
                        input_snapshot=case.source_snapshot,
                        input_hash=digest(case.source_snapshot),
                        output=result,
                    )
                )
            else:
                if (
                    not {"bootstrap", "captured"} & case.source_snapshot.keys()
                    or "request" not in case.source_snapshot
                ):
                    raise ModelGatewayError("case_incompatible")
                async with sandbox(
                    self.settings,
                    gateway,
                    ScopedResearch(
                        FrozenResearch(case.frozen_external_observations, faults),
                        scoped,
                        self.settings.search_cost_per_call,
                    ),
                    allow_paid_models=self.allow_paid_models,
                ) as (client, sessions):
                    if "captured" in case.source_snapshot:
                        from datetime import datetime

                        from career_agent.evaluation.captured import restore_inputs

                        if entry.kind == "agent_goal" and not case.source_snapshot["captured"].get(
                            "agent_goal_compatible"
                        ):
                            raise ModelGatewayError("case_incompatible")
                        frozen_clock = case.source_snapshot["captured"].get("evaluation_clock")
                        if (
                            frozen_clock is None
                            or datetime.fromisoformat(frozen_clock) != case.evaluation_clock
                        ):
                            raise ModelGatewayError("case_incompatible")

                        async with sessions.begin() as session:
                            await restore_inputs(
                                session,
                                case.source_snapshot["captured"],
                                session.info["evaluation_data_dir"],
                            )
                        refs = {}
                    else:
                        refs = await bootstrap(client, case.source_snapshot["bootstrap"])
                    payload = replace_refs(case.source_snapshot["request"], refs)
                    if (
                        "captured" not in case.source_snapshot
                        and payload.get("mode", "fixture") != "fixture"
                    ):
                        raise ModelGatewayError("eval_live_mode_forbidden")
                    if entry.name == "actual_intake_cas":
                        from career_agent.evaluation.sandbox import actual_cas_recovery

                        result = await actual_cas_recovery(client, refs["$application"])
                        operations.append(
                            OperationSnapshot(
                                kind="deterministic_operation",
                                name="actual_intake_cas",
                                version="actual-intake-cas-v1",
                                input_snapshot=case.source_snapshot,
                                input_hash=digest(case.source_snapshot),
                                output=result,
                            )
                        )
                    else:
                        path = (
                            "/api/v1/agent-runs"
                            if entry.kind == "agent_goal"
                            else "/api/v1/workflows/" + entry.name
                        )
                        if entry.kind != "agent_goal" and entry.name not in {
                            "prepare_application",
                            "prepare_interview",
                        }:
                            raise ModelGatewayError("case_incompatible")
                        response = await client.post(path, json=payload)
                        if response.status_code not in {200, 201}:
                            result = {
                                "status": "failed",
                                "reason_code": response.json()
                                .get("error", {})
                                .get("code", "execution_failed"),
                            }
                        else:
                            body = response.json()
                            state = body["state"]
                            result = {
                                "status": state.get("status", state.get("phase")),
                                "state": state,
                                "outcome": body.get("outcome"),
                                "valid": True,
                            }
                    async with sessions() as session:
                        for decision in await session.scalars(
                            select(ReuseDecision).order_by(ReuseDecision.created_at)
                        ):
                            metadata = {
                                "category": decision.category,
                                "operation": decision.operation,
                                "disposition": decision.disposition,
                                "identity_hash": decision.identity_hash,
                            }
                            operations.append(
                                OperationSnapshot(
                                    kind="deterministic_operation",
                                    name="reuse_decision",
                                    version=IDENTITY_VERSION,
                                    input_snapshot=metadata,
                                    input_hash=digest(metadata),
                                    output={"disposition": decision.disposition},
                                    output_ref=decision.observation_id,
                                    parent_run_id=decision.run_id,
                                )
                            )
                        private = list(await session.scalars(select(q.InvocationRow)))
                        # Prefer committed exact ModelCall provenance over adapter observations.
                        if private:
                            operations[:] = [op for op in operations if op.kind != "model_task"] + [
                                OperationSnapshot.model_validate(r.data) for r in private
                            ]
                            for op in operations:
                                matching = [
                                    event
                                    for event in faults.events
                                    if event["operation"] == op.name
                                    and event["attempt"] == op.provenance.get("attempt", 1)
                                ]
                                if matching:
                                    op.injected_fault = matching[-1]["injected_fault"]
                        # Preserve deterministic compiler evidence before the sandbox is dropped.
                        seeded_renders = {
                            row["values"]["id"]
                            for row in case.source_snapshot.get("captured", {}).get("rows", [])
                            if row["table"] == "render_artifacts"
                        }
                        for artifact in await session.scalars(select(e.RenderArtifact)):
                            if str(artifact.id) in seeded_renders:
                                continue
                            revision = await session.scalar(
                                select(e.ResumeVariantRevision).where(
                                    e.ResumeVariantRevision.resume_variant_id
                                    == artifact.resume_variant_id,
                                    e.ResumeVariantRevision.revision
                                    == artifact.resume_variant_revision,
                                )
                            )
                            if revision is None:
                                raise ModelGatewayError("case_incompatible")
                            report = artifact.report
                            versions = report["versions"]
                            operations.append(
                                OperationSnapshot(
                                    kind="deterministic_operation",
                                    name="resume_compile",
                                    version=versions.get("render_wrapper_version") or "unknown",
                                    input_snapshot={
                                        "variant": revision.document,
                                        "input_snapshot": revision.input_snapshot,
                                    },
                                    input_hash=digest(
                                        {
                                            "variant": revision.document,
                                            "input_snapshot": revision.input_snapshot,
                                        }
                                    ),
                                    output=report,
                                    output_ref=artifact.id,
                                    provenance={
                                        "versions": versions,
                                        "file_hash": artifact.file_hash,
                                        "resume_revision_id": str(revision.id),
                                    },
                                    reason_codes=[report["error_code"]]
                                    if report.get("error_code")
                                    else [],
                                )
                            )
                        obs = list(
                            await session.scalars(
                                select(e.Observation)
                                .join(e.AgentStep, e.Observation.action_step_id == e.AgentStep.id)
                                .where(e.Observation.action_data.is_not(None))
                                .order_by(e.AgentStep.sequence)
                            )
                        )
                        from career_agent.runtime.agent_contracts import AgentState

                        checkpoints = list(await session.scalars(select(e.AgentCheckpoint)))
                        identities = {}
                        action_inputs = {}
                        for checkpoint in checkpoints:
                            persisted = AgentState.model_validate(checkpoint.state)
                            for action_id, progress in persisted.progress.actions.items():
                                identities[str(action_id)] = progress.fingerprint
                                action_inputs[str(action_id)] = progress.action.model_dump(
                                    mode="json"
                                )
                        actions = [dict(r.action_data or {}) for r in obs]
                        for action in actions:
                            action["identity"] = identities.get(str(action.get("action_id")))
                        result["trajectory"] = trajectory(actions)
                        result["actions"] = [a.get("disposition") for a in actions]
                        calls = list(await session.scalars(select(e.ModelCall)))
                        result["model_calls"] = len(calls)
                        result["replan_count"] = sum(
                            c.task_type == "goal_replanning" for c in calls
                        )
                        result["action_names"] = [value["name"] for value in action_inputs.values()]
                        result["permissions_valid"] = all(
                            value["name"] in {"prepare_application", "prepare_interview"}
                            for value in action_inputs.values()
                        )
                        result["retry_count"] = sum(c.attempts > 1 for c in calls)
                        result["trace_private"] = all(
                            "context" not in c.versions and "prompt" not in c.versions
                            for c in calls
                        )
                        for step in await session.scalars(
                            select(e.AgentStep).where(
                                e.AgentStep.versions["action_name"].astext.is_not(None)
                            )
                        ):
                            operations.append(
                                OperationSnapshot(
                                    kind="business_action",
                                    name=step.versions.get("action_name") or "unknown",
                                    version=step.versions.get("action_version") or "unknown",
                                    input_snapshot=action_inputs.get(str(step.action_id), {}),
                                    input_hash=digest(action_inputs.get(str(step.action_id), {})),
                                    output=next(
                                        (
                                            a
                                            for a in actions
                                            if a.get("action_id") == str(step.action_id)
                                        ),
                                        None,
                                    ),
                                    provenance=step.versions,
                                    parent_step_id=step.id,
                                    parent_run_id=step.run_id,
                                    reason_codes=[step.reason_code] if step.reason_code else [],
                                )
                            )
            result["injected_faults"] = faults.events
        except (ModelGatewayError, DomainError) as exc:
            reason = exc.code
            if operations and operations[-1].kind == "model_task":
                if reason not in operations[-1].reason_codes:
                    operations[-1].reason_codes.append(reason)
            incompatible = reason in {
                "case_incompatible",
                "origin_model_unavailable",
                "origin_config_unavailable",
                "unregistered_prompt_task",
                "prompt_input_blocks_invalid",
                "prompt_input_type_invalid",
            }
            result = {"status": "failed", "reason_code": reason, "injected_faults": faults.events}
        except (ValidationError, KeyError, TypeError, ValueError):
            reason = "case_incompatible"
            incompatible = True
            result = {"status": "failed", "reason_code": reason}
        finally:
            for operation in operations:
                selection = operation.provenance.get("control_selection")
                if selection:
                    attempt_id = UUID(selection["attempt_id"])
                    operation.provenance["control_outcome"] = gateway.outcomes.get(attempt_id, {})
                    logical_id = UUID(selection["logical_operation_id"])
                    control_operation = gateway.operations.get(logical_id)
                    if control_operation:
                        operation.provenance["control_decisions"] = list(
                            control_operation.decisions
                        )
                operation.provenance.setdefault("model_policy_version", gateway.policy.version)
            represented = {
                op.provenance.get("control_selection", {}).get("logical_operation_id")
                for op in operations
            }
            for identity, control_operation in gateway.operations.items():
                if str(identity) not in represented and control_operation.decisions:
                    operations.append(
                        OperationSnapshot(
                            kind="deterministic_operation",
                            name="model_admission",
                            version=gateway.controller.policy.implementation_version,
                            input_snapshot={},
                            input_hash=digest({}),
                            logical_operation_id=identity,
                            provenance={"control_decisions": list(control_operation.decisions)},
                            reason_codes=["model_admission_denied"],
                        )
                    )
            FROZEN_CLOCK.reset(token)
            EVALUATION_ORIGIN.reset(origin)
        checks = evaluate(case.expectations, result)
        usage = Usage(
            input_tokens=scoped.usage.input_tokens,
            output_tokens=scoped.usage.output_tokens,
            estimated_cost=scoped.usage.estimated_cost,
            budget_reserved_usd=scoped.usage.budget_reserved_usd,
            reserved_input_tokens=scoped.usage.reserved_input_tokens,
            reserved_output_tokens=scoped.usage.reserved_output_tokens,
            measurement="unknown" if scoped.usage.unknown_usage_attempts else "reported",
        )
        return TrialResult(
            status="case_incompatible"
            if incompatible
            else "completed"
            if all(c.status == "pass" for c in checks)
            else "failed",
            checks=checks,
            output=result,
            usage=usage,
            reason_code=reason,
            latency_ms=int((time.monotonic() - start) * 1000),
        ), operations

    async def view(self, id: UUID) -> dict[str, Any]:
        async with self.sessions() as session:
            run = await require(session, q.EvalRunRow, id)
            trials = list(
                await session.scalars(
                    select(q.EvalTrialRow)
                    .where(q.EvalTrialRow.run_id == id)
                    .order_by(q.EvalTrialRow.case_id, q.EvalTrialRow.trial_index)
                )
            )
            return {
                "id": run.id,
                "status": run.status,
                "candidate": run.candidate,
                "summary": run.summary,
                "reason_code": run.reason_code,
                "trials": [
                    {
                        "id": t.id,
                        "case_id": t.case_id,
                        "trial_index": t.trial_index,
                        "status": t.status,
                        "result": t.result,
                    }
                    for t in trials
                ],
            }
