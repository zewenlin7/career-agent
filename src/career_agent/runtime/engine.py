"""Synchronous bounded runtime, with committed action-boundary checkpoints.

In-flight checkpoints deliberately cannot be replayed. This is not a worker/recovery service.
"""

import hashlib
import json
import time
from collections.abc import Callable
from decimal import Decimal
from functools import partial
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application.services import require
from career_agent.config import Settings
from career_agent.domain.rules import CallStatus, DomainError, ObservationStatus, RunStatus
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError, ModelRequestContext, PrivacyClass
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.budget import input_bound
from career_agent.preparation.context import ContextLoader
from career_agent.preparation.contracts import (
    PrivateResult,
    TargetArtifact,
    TargetOutcome,
    WorkflowOutcome,
    WorkflowRequest,
    WorkflowState,
)
from career_agent.preparation.orchestrator import Orchestrator
from career_agent.preparation.research import ResearchAdapter
from career_agent.preparation.workflows import PreparationWorkflow
from career_agent.resume.renderer import CompileError
from career_agent.runtime.agent_contracts import (
    ActionObservation,
    ActionProgress,
    AgentCreate,
    AgentResume,
    AgentState,
    PlanAction,
    PlanProposal,
    StateTransition,
)
from career_agent.runtime.budget import RuntimeBudget, run_limits
from career_agent.runtime.contracts import Budget, Usage, VersionMetadata
from career_agent.runtime.evaluator import evaluate
from career_agent.runtime.plans import action_targets, fingerprint, validate_plan
from career_agent.runtime.registry import REGISTRY, validate_action_version

TERMINAL = {"completed", "partial", "failed", "cancelled"}
SAFE_FAILURES = (ModelGatewayError, DomainError, CompileError, ValidationError)


def code(exc: Exception) -> str:
    return str(getattr(exc, "code", "invalid_plan"))


class AgentEngine:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        gateway: ModelGateway,
        research: ResearchAdapter,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sessions, self.settings, self.gateway, self.research, self.clock = (
            sessions,
            settings,
            gateway,
            research,
            clock,
        )
        self.started = clock()

    def remaining(self, state: AgentState) -> float:
        return (
            state.limits.max_active_seconds
            - state.usage.active_seconds
            - (self.clock() - self.started)
        )

    def charge_time(self, state: AgentState) -> None:
        now = self.clock()
        state.usage.active_seconds += max(0, now - self.started)
        self.started = now

    async def load(
        self, session: AsyncSession, id: UUID, *, lock: bool = False
    ) -> tuple[e.AgentRun, AgentState]:
        run = await require(session, e.AgentRun, id, lock=lock)
        if run.run_kind != "agent":
            raise DomainError("not_agent_run", 404)
        checkpoint = await session.scalar(
            select(e.AgentCheckpoint)
            .where(e.AgentCheckpoint.run_id == id)
            .order_by(e.AgentCheckpoint.revision.desc())
        )
        if checkpoint is None:
            raise DomainError("checkpoint_missing", 409)
        return run, AgentState.model_validate(checkpoint.state)

    async def save(self, session: AsyncSession, run: e.AgentRun, state: AgentState) -> None:
        state.state_revision += 1
        session.add(
            e.AgentCheckpoint(
                run_id=run.id, revision=state.state_revision, state=state.model_dump(mode="json")
            )
        )
        run.status = (
            RunStatus.RUNNING
            if state.phase in {"ready", "planning", "executing"}
            else RunStatus(state.phase)
        )
        run.stop_reason = state.pending_reason
        u = state.usage
        pending = state.dispatch_reservation or Usage()
        run.consumed_usage = Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            estimated_cost=u.estimated_cost,
            budget_reserved_usd=u.budget_reserved_usd + pending.budget_reserved_usd,
            reserved_input_tokens=u.reserved_input_tokens + pending.reserved_input_tokens,
            reserved_output_tokens=u.reserved_output_tokens + pending.reserved_output_tokens,
            search_calls=u.search_calls,
            measurement="unknown"
            if u.unknown_usage_attempts or state.dispatch_reservation
            else "reported",
            pricing_version=self.settings.pricing_version,
        ).model_dump(mode="json")
        if state.phase in TERMINAL:
            run.finished_at = e.utcnow()
            targets = state.progress.requested_targets
            if not targets:
                targets = {
                    t: TargetOutcome(status="failed", reason=state.pending_reason or "invalid_plan")
                    for t in state.scope.targets
                }
                state.progress.requested_targets = targets
            for t, v in list(targets.items()):
                if v.status == "pending":
                    targets[t] = TargetOutcome(
                        status="blocked", reason=state.pending_reason or "execution_stopped"
                    )
            done = sum(v.status == "completed" for v in targets.values())
            outcome = WorkflowOutcome(
                status="completed" if done == len(targets) else "partial" if done else "failed",
                reason=state.pending_reason,
                targets=targets,
            )
            run.outcome = outcome.model_dump(mode="json")
            # Terminal normalization precedes the stored snapshot.
            for obj in session.new:
                if (
                    isinstance(obj, e.AgentCheckpoint)
                    and obj.run_id == run.id
                    and obj.revision == state.state_revision
                ):
                    obj.state = state.model_dump(mode="json")
        await session.flush()

    async def view(self, id: UUID) -> dict[str, Any]:
        async with self.sessions() as session:
            run, state = await self.load(session, id)
            return {
                "run_id": str(id),
                "state": state.model_dump(mode="json"),
                "outcome": run.outcome,
            }

    async def create(self, payload: AgentCreate) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            await require(session, e.PersonalProfile, payload.bindings.profile_id)
            await require(session, e.JobRevision, payload.bindings.job_revision_id)
            limits = payload.limits.model_copy(deep=True)
            limits.max_estimated_cost = min(limits.max_estimated_cost, self.settings.max_run_cost)
            run = e.AgentRun(
                run_kind="agent",
                workflow="agent_goal",
                workflow_version="agent-runtime-v1",
                status=RunStatus.RUNNING,
                started_at=e.utcnow(),
                budget=Budget(
                    token_limit=limits.max_input_tokens + limits.max_output_tokens,
                    cost_limit=limits.max_estimated_cost,
                ).model_dump(mode="json"),
            )
            session.add(run)
            await session.flush()
            goal = e.AgentGoal(run_id=run.id, data=payload.model_dump(mode="json"))
            session.add(goal)
            await session.flush()
            state = AgentState(
                run_id=run.id,
                goal_id=goal.id,
                bindings=payload.bindings,
                scope=payload.authorized_scope,
                original_scope=payload.authorized_scope,
                mode=payload.mode,
                limits=limits,
            )
            await self.save(session, run, state)
            id = run.id
        return await self.drive(id, payload.action_slice)

    def runner(
        self,
        session: AsyncSession,
        state: AgentState,
        request: WorkflowRequest | None = None,
        budget: RuntimeBudget | None = None,
    ) -> PreparationWorkflow:
        if request is None:
            request = WorkflowRequest(
                profile_id=state.bindings.profile_id,
                job_revision_id=state.bindings.job_revision_id,
                mode=state.mode,
                targets=["fit_analysis"],
                application_package_id=state.bindings.application_package_id,
            )
        r = PreparationWorkflow(
            session, self.settings, self.gateway, self.research, request, runtime_budget=budget
        )
        r.state = WorkflowState(
            run_id=state.run_id,
            workflow="prepare_application",
            job_revision_id=state.bindings.job_revision_id,
            profile_id=state.bindings.profile_id,
            requested_outputs=[],
            mode=state.mode,
        )
        return r

    async def validate_context(
        self, session: AsyncSession, state: AgentState
    ) -> PreparationWorkflow:
        for progress in state.progress.actions.values():
            if progress.status not in {"completed", "failed"}:
                validate_action_version(progress.action)
        r = self.runner(session, state)
        await r.validate_inputs()
        snapshot = {id: f.revision for id, f in r.fact_rows.items()}
        if state.fact_snapshot and snapshot != state.fact_snapshot:
            raise ModelGatewayError("context_changed")
        state.fact_snapshot = snapshot
        loader = ContextLoader(r)
        r.requirements = await loader.requirements()
        r.state.requirement_refs = [v.id for v in r.requirements]
        if state.bindings.resume_revision_id:
            await loader.resume(state.bindings.resume_revision_id)
        if state.bindings.application_package_id:
            await loader.interview()
        for value in state.progress.requested_targets.values():
            if value.status == "completed" and value.artifact_id:
                row = await require(session, e.PreparationArtifact, value.artifact_id)
                if row.profile_id != r.profile.id or row.job_revision_id != r.job.id:
                    raise ModelGatewayError("context_revision_mismatch")
                output = PrivateResult.model_validate(row.data).output
                if not isinstance(output, TargetArtifact):
                    raise ModelGatewayError("context_revision_mismatch")
                await Orchestrator(r).restore(output)
        return r

    async def resume(self, id: UUID, payload: AgentResume) -> dict[str, Any]:
        digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        duplicate = False
        async with self.sessions.begin() as session:
            run, state = await self.load(session, id, lock=True)
            receipt = await session.scalar(
                select(e.AgentResumeReceipt).where(
                    e.AgentResumeReceipt.run_id == id,
                    e.AgentResumeReceipt.request_id == payload.request_id,
                )
            )
            if receipt:
                if receipt.request_hash != digest:
                    raise DomainError("idempotency_conflict")
                duplicate = True
            else:
                if state.state_revision != payload.expected_checkpoint_revision:
                    raise DomainError("stale_checkpoint")
                if state.phase in {"planning", "executing"}:
                    raise DomainError("inflight_action_not_resumable")
                if state.phase in TERMINAL:
                    raise DomainError("run_terminal")
                session.add(
                    e.AgentResumeReceipt(
                        run_id=id, request_id=payload.request_id, request_hash=digest
                    )
                )
                if payload.decision == "cancel":
                    state.phase = "cancelled"
                    state.pending_reason = "user_cancelled"
                    await self.save(session, run, state)
                else:
                    # Resume proposals are unconfirmed until every check succeeds. Deep-copy
                    # nested progress/bindings too: context validation can update the snapshot.
                    candidate = state.model_copy(deep=True)
                    changed = False
                    for field in ("resume_revision_id", "application_package_id"):
                        supplied = getattr(payload, field)
                        current = getattr(candidate.bindings, field)
                        if supplied:
                            if current and supplied != current:
                                raise DomainError("immutable_binding")
                            changed |= current is None
                            setattr(candidate.bindings, field, supplied)
                    if payload.authorized_targets is not None:
                        new = set(payload.authorized_targets)
                        if len(new) != len(payload.authorized_targets) or not new <= set(
                            candidate.original_scope.targets
                        ):
                            raise DomainError("scope_expansion")
                        completed = {
                            t
                            for t, v in candidate.progress.requested_targets.items()
                            if v.status == "completed"
                        }
                        if not completed <= new:
                            raise DomainError("completed_target_immutable")
                        changed = True
                        candidate.scope = candidate.scope.model_copy(
                            update={"targets": payload.authorized_targets}
                        )
                        candidate.progress.requested_targets = {
                            t: candidate.progress.requested_targets.get(t, TargetOutcome())
                            for t in payload.authorized_targets
                        }
                    if candidate.phase == "waiting_decision":
                        if payload.decision != "continue":
                            raise DomainError("explicit_decision_required")
                        candidate.gate_approved = True
                        changed = True
                    if (
                        candidate.phase == "waiting_input"
                        and not changed
                        and candidate.pending_reason
                        in {
                            "resume_selection_required",
                            "application_package_required",
                            "goal_clarification_required",
                            "input_required",
                        }
                    ):
                        raise DomainError("input_required")
                    try:
                        await self.validate_context(session, candidate)
                    except SAFE_FAILURES as exc:
                        # Retain confirmed authorization and any outstanding Gate decision.
                        # Only the failure reason/waiting checkpoint is committed.
                        if state.phase != "waiting_decision":
                            state.phase = "waiting_input"
                        state.pending_reason = code(exc)
                        await self.save(session, run, state)
                    else:
                        candidate.needs_plan |= changed
                        candidate.phase = "ready"
                        candidate.pending_reason = None
                        await self.save(session, run, candidate)
        if duplicate:
            return await self.view(id)
        current = await self.view(id)
        if current["state"]["phase"] != "ready":
            return current
        return await self.drive(id, payload.action_slice)

    def finish(self, state: AgentState, reason: str | None = None) -> None:
        done = sum(v.status == "completed" for v in state.progress.requested_targets.values())
        state.phase = (
            "completed"
            if done and done == len(state.progress.requested_targets)
            else "partial"
            if done
            else "failed"
        )
        state.pending_reason = reason

    async def step(
        self, session: AsyncSession, state: AgentState, node: str, action: PlanAction | None = None
    ) -> e.AgentStep:
        if state.usage.steps >= state.limits.max_steps:
            raise ModelGatewayError("step_budget_exhausted")
        state.usage.steps += 1
        row = e.AgentStep(
            run_id=state.run_id,
            sequence=state.usage.steps,
            node=node,
            action=action.name if action else None,
            action_id=action.action_id if action else None,
            plan_revision=state.plan_revision or None,
            status=CallStatus.RUNNING,
            versions=VersionMetadata(
                workflow_version="agent-runtime-v1",
                action_name=action.name if action else None,
                action_version=action.action_version if action else None,
                input_schema_version=REGISTRY[action.name].args_schema_version if action else None,
                output_schema_version=REGISTRY[action.name].result_schema_version
                if action
                else None,
                evaluator_version="runtime-evaluator-v1" if node == "evaluate" else None,
            ).model_dump(mode="json"),
        )
        session.add(row)
        await session.flush()
        return row

    async def planner_context(self, session: AsyncSession, state: AgentState) -> dict[str, Any]:
        r = await self.validate_context(session, state)
        goal = await require(session, e.AgentGoal, state.goal_id)
        artifacts = []
        candidates = await session.scalars(
            select(e.PreparationArtifact)
            .where(
                e.PreparationArtifact.profile_id == state.bindings.profile_id,
                e.PreparationArtifact.job_revision_id == state.bindings.job_revision_id,
                e.PreparationArtifact.data["kind"].astext == "target",
            )
            .order_by(e.PreparationArtifact.created_at.desc())
            .limit(4)
        )
        for row in candidates:
            output = PrivateResult.model_validate(row.data).output
            if not isinstance(output, TargetArtifact):
                continue
            # Keep discovery conservative: these two fingerprints need no optional research
            # or interview package state. Richer reuse stays in the business context loader.
            if output.target not in {"fit_analysis", "resume_tailoring"}:
                continue
            if output.target not in state.scope.targets:
                continue
            source = (
                state.bindings.resume_revision_id if output.target == "resume_tailoring" else None
            )
            if output.fingerprint != Orchestrator(r).fingerprint(output.target, source):
                continue
            try:
                await Orchestrator(r).restore(output)
            except SAFE_FAILURES:
                continue
            artifacts.append({"id": str(row.id), "target": output.target, "status": "available"})
        previous = None
        if state.previous_observation_id:
            observation = await require(session, e.Observation, state.previous_observation_id)
            if observation.action_data:
                previous = {
                    k: observation.action_data.get(k)
                    for k in ["disposition", "reason_code", "evidence_refs"]
                }
        return {
            "goal": goal.data["goal"],
            "bindings": state.bindings.model_dump(mode="json"),
            "authorized_scope": state.scope.model_dump(mode="json"),
            "allowed_actions": [
                {
                    "name": v.name,
                    "version": v.version,
                    "permission_policy": v.permission_policy,
                }
                for v in REGISTRY.values()
            ],
            "artifacts": artifacts,
            "progress": {
                "requested_targets": {
                    k: v.model_dump(mode="json")
                    for k, v in state.progress.requested_targets.items()
                }
            },
            "previous_observation": previous,
            "remaining_budget": run_limits(state, remaining=True).model_dump(mode="json"),
        }

    async def plan(
        self, session: AsyncSession, state: AgentState, step: e.AgentStep, budget: RuntimeBudget
    ) -> None:
        from career_agent.evaluation.captured import freeze_inputs

        goal = await require(session, e.AgentGoal, state.goal_id)
        replay = await freeze_inputs(
            session,
            state.bindings.profile_id,
            state.bindings.job_revision_id,
            state.bindings.resume_revision_id,
            goal.data,
            self.settings.data_dir,
        )
        # A continuation Planner capture remains replayable as a model task. A fresh-goal
        # replay must not silently discard already-confirmed decisions or resume events.
        replay["agent_goal_compatible"] = state.plan_revision == 0
        context = await self.planner_context(session, state)
        task_type = "goal_replanning" if state.plan_revision else "goal_planning"
        prompt = self.gateway.prompts.resolve(task_type)
        spec = prompt.task(context)
        request = ModelRequestContext(
            task_type=task_type,
            workflow_version="agent-runtime-v1",
            workflow="agent_goal",
            output_schema=PlanProposal,
            max_output_tokens=2048,
            privacy_class=PrivacyClass.SYNTHETIC
            if state.mode == "fixture"
            else PrivacyClass.PRIVATE,
            budget_remaining=Budget(
                cost_limit=max(
                    Decimal(0), state.limits.max_estimated_cost - state.usage.budget_consumed_usd
                )
            ),
            **prompt.metadata,
        )
        self.gateway.prompts.trace_metadata(request, spec)
        bound = input_bound(request, spec)
        if bound > 8000:
            raise ModelGatewayError("planner_context_too_large")
        request = request.model_copy(
            update={"execution_seconds_remaining": max(0.0, budget.remaining_seconds())}
        )
        try:
            request = await self.gateway.prepare(request, spec)
        except ModelGatewayError as exc:
            step.versions = {**step.versions, "control_decisions": exc.control_decisions}
            raise
        candidate = self.gateway.candidate(request)
        try:
            reserved = budget.root.reserve_model(candidate, bound, request.max_output_tokens)
        except BaseException:
            self.gateway.cancel_prepared(request)
            raise
        call = e.ModelCall(
            step_id=step.id,
            task_type=request.task_type,
            logical_operation_id=request.logical_operation_id,
            provider=candidate.provider,
            model=candidate.model,
            status=CallStatus.RUNNING,
            attempts=1,
            versions=self.gateway.trace_metadata(request, spec).model_dump(mode="json"),
        )
        session.add(call)
        try:
            await session.flush()
        except BaseException:
            self.gateway.cancel_prepared(request)
            budget.root.cancel_model(reserved)
            raise
        start = self.clock()
        error: ModelGatewayError | None = None
        try:
            result = await budget.generate(self.gateway, request, spec)
        except ModelGatewayError as exc:
            if not self.gateway.was_dispatched(request):
                self.gateway.cancel_prepared(request)
                budget.root.cancel_model(reserved)
                await session.delete(call)
                step.versions = {**step.versions, "control_decisions": exc.control_decisions}
                raise
            usage = budget.root.settle(reserved, exc.usage)
            call.status, call.error_code = CallStatus.FAILED, exc.code
            if exc.diagnostic:
                call.versions = {
                    **call.versions,
                    "output_diagnostic": exc.diagnostic.model_dump(mode="json"),
                }
            error = exc
            result = None
        else:
            assert result is not None
            usage = budget.root.settle(reserved, result.usage)
            call.status = CallStatus.SUCCEEDED
            if result.versions.output_diagnostic:
                call.versions = {
                    **call.versions,
                    "output_diagnostic": result.versions.output_diagnostic.model_dump(mode="json"),
                }
            error = None
        control = self.gateway.trace_metadata(request, spec)
        call.versions = {
            **call.versions,
            "control_metadata": control.control_metadata,
            "control_decisions": control.control_decisions,
        }
        call.usage = usage.model_dump(mode="json")
        call.estimated_cost = usage.estimated_cost
        call.latency_ms = int((self.clock() - start) * 1000)
        call.finish_reason = result.finish_reason if result else None
        call.schema_validation_state = (
            "valid"
            if result
            else "invalid"
            if error and error.code in {"structured_output_invalid", "output_validation_failed"}
            else "not_validated"
        )
        session.add(
            e.Observation(
                model_call_id=call.id,
                status=ObservationStatus.OK if result else ObservationStatus.ERROR,
                error_code=call.error_code,
            )
        )
        from career_agent.evaluation.recording import record_model

        await record_model(
            session,
            call_id=call.id,
            run_id=state.run_id,
            step_id=step.id,
            context=request,
            task=spec,
            output=result.validated_output.model_dump(mode="json") if result else None,
            versions=call.versions,
            operation_id=call.logical_operation_id,
            source={
                "captured_source_version": "captured-source-v1",
                "replay": replay,
                "state": state.model_dump(mode="json"),
                "evidence": sorted(
                    {a["id"] for a in context["artifacts"]}
                    | {str(ref) for ref in state.bindings.model_dump().values() if ref is not None}
                ),
            },
            reason=error.code if error else None,
        )
        if error:
            raise error
        assert result is not None
        proposal = cast(PlanProposal, result.validated_output)
        allowed_refs = {a["id"] for a in context["artifacts"]} | {
            str(ref) for ref in state.bindings.model_dump().values() if ref is not None
        }
        proposal = validate_plan(proposal, state, allowed_refs).proposal
        # Cosmetic IDs/reasons cannot disguise the same plan. Explicit gate approval is
        # new authorization, so a previously waiting action may legitimately continue.
        positions = {a.action_id: n for n, a in enumerate(proposal.actions)}
        canonical = proposal.model_dump(mode="json", exclude={"reason_code", "evidence_refs"})
        for item in canonical["actions"]:
            item["action_id"] = positions[UUID(item["action_id"])]
            item["dependencies"] = sorted(positions[UUID(d)] for d in item["dependencies"])
            source = item["args"]["package_from_action"]
            if source:
                item["args"]["package_from_action"] = positions[UUID(source)]
        canonical["gate_approved"] = state.gate_approved
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        if digest in state.plan_fingerprints:
            raise ModelGatewayError("no_progress")
        state.plan_fingerprints.append(digest)
        state.plan_revision += 1
        step.plan_revision = state.plan_revision
        plan_row = e.AgentPlan(
            run_id=state.run_id,
            revision=state.plan_revision,
            data=proposal.model_dump(mode="json"),
        )
        session.add(plan_row)
        await session.flush()
        from career_agent.evaluation.recording import bind_artifact

        await bind_artifact(session, call.id, plan_row.id, self.settings.judge_sampling)
        if not state.progress.requested_targets:
            state.progress.requested_targets = {
                t: TargetOutcome() for t in proposal.requested_targets
            }
        # Completed actions remain provenance; only the new pending actions run.
        for old in state.progress.actions.values():
            if old.status in {"pending", "waiting", "blocked"}:
                old.status = "blocked"
        for action in proposal.actions:
            state.progress.actions[action.action_id] = ActionProgress(
                action=action, fingerprint=fingerprint(action)
            )
        state.needs_plan = False
        if proposal.missing_inputs:
            state.phase = "waiting_input"
            state.pending_reason = proposal.missing_inputs[0]
        else:
            state.phase = "ready"
            state.pending_reason = None

    async def execute_action(
        self, session: AsyncSession, state: AgentState, action: PlanAction, budget: RuntimeBudget
    ) -> ActionObservation:
        if action.name not in REGISTRY or not set(action_targets(action)) <= set(
            state.scope.targets
        ):
            raise ModelGatewayError("plan_authority_violation")
        validate_action_version(action)
        await self.validate_context(session, state)
        started = self.clock()
        deadline = started + REGISTRY[action.name].timeout_seconds
        budget = RuntimeBudget(state, lambda: min(self.remaining(state), deadline - self.clock()))
        args = action.args
        package = args.application_package_id or state.bindings.application_package_id
        if args.package_from_action:
            package = state.progress.actions[args.package_from_action].package_id
            if package is None:
                raise ModelGatewayError("dependency_failed")
        targets = args.targets or ["fit_analysis"]  # ignored by explicit interview workflow
        request = WorkflowRequest(
            profile_id=state.bindings.profile_id,
            job_revision_id=state.bindings.job_revision_id,
            mode=state.mode,
            targets=targets,
            limits=run_limits(state, remaining=True),
            resume_revision_id=args.resume_revision_id or state.bindings.resume_revision_id,
            bindings=args.bindings,
            application_package_id=package,
            fit_gate="informational" if state.gate_approved else state.scope.fit_gate,
        )
        runner = self.runner(session, state, request, budget)
        result = await runner.execute(action.name)
        runner.run.parent_run_id = state.run_id
        outcome = WorkflowOutcome.model_validate(result["outcome"])
        waited = outcome.status in {"needs_input", "decision_required"}
        disposition = (
            "needs_input"
            if outcome.status == "needs_input"
            else "decision_required"
            if waited
            else "executed"
        )
        if outcome.status in {"failed", "partial"}:
            disposition = "failed"
        elif outcome.status == "completed" and all(
            n.status in {"reused", "skipped"}
            for n in outcome.nodes
            if n.name in action_targets(action)
        ):
            disposition = "reused"
        return ActionObservation(
            action_id=action.action_id,
            disposition=disposition,
            reason_code=outcome.reason,
            child_run_id=runner.run.id,
            package_id=UUID(result["package_id"]),
            targets=outcome.targets,
            guardrails="passed"
            if outcome.status == "completed"
            else "not_run"
            if waited
            else "failed",
        )

    async def drive(self, id: UUID, action_slice: int) -> dict[str, Any]:
        self.started = self.clock()
        executed = 0
        while True:
            # Claim exactly one unit of work; persist its conservative reservation before dispatch.
            async with self.sessions.begin() as session:
                run, state = await self.load(session, id, lock=True)
                if state.phase != "ready":
                    break
                try:
                    budget = RuntimeBudget(state, partial(self.remaining, state))
                    budget.check_time()
                    action = None
                    if state.needs_plan:
                        if state.plan_revision:
                            if state.replan_count >= state.limits.max_replans:
                                raise ModelGatewayError("replan_budget_exhausted")
                            state.replan_count += 1
                        step = await self.step(
                            session, state, "replan" if state.plan_revision else "plan"
                        )
                        state.phase = "planning"
                    else:
                        if executed >= action_slice:
                            break
                        pending = [
                            v for v in state.progress.actions.values() if v.status == "pending"
                        ]
                        ready = [
                            v
                            for v in pending
                            if all(
                                state.progress.actions[d].status == "completed"
                                for d in v.action.dependencies
                            )
                        ]
                        if not ready:
                            if pending and state.replan_count < state.limits.max_replans:
                                state.needs_plan = True
                                await self.save(session, run, state)
                                continue
                            self.finish(state, "dependency_failed" if pending else None)
                            await self.save(session, run, state)
                            break
                        plan_row = await session.scalar(
                            select(e.AgentPlan).where(
                                e.AgentPlan.run_id == id,
                                e.AgentPlan.revision == state.plan_revision,
                            )
                        )
                        assert plan_row is not None
                        order = {
                            a.action_id: i
                            for i, a in enumerate(
                                PlanProposal.model_validate(plan_row.data).actions
                            )
                        }
                        action = min(ready, key=lambda p: order[p.action.action_id]).action
                        if state.usage.business_actions >= state.limits.max_total_business_actions:
                            raise ModelGatewayError("action_budget_exhausted")
                        if fingerprint(action) in state.attempted_fingerprints:
                            raise ModelGatewayError("no_progress")
                        validate_action_version(action)
                        state.usage.business_actions += 1
                        step = await self.step(session, state, "execute", action)
                        state.phase = "executing"
                        state.current_action_id = action.action_id
                    remaining = run_limits(state, remaining=True)
                    state.dispatch_reservation = Usage(
                        budget_reserved_usd=remaining.max_estimated_cost,
                        reserved_input_tokens=remaining.max_input_tokens,
                        reserved_output_tokens=remaining.max_output_tokens,
                    )
                    await self.save(session, run, state)
                    step_id = step.id
                except ModelGatewayError as exc:
                    self.finish(state, exc.code)
                    await self.save(session, run, state)
                    break
            # The existing business transaction is intact. Child artifacts, completion and the
            # next checkpoint commit together. Uncaught exceptions leave the dispatch in-flight.
            async with self.sessions() as session:
                try:
                    async with session.begin():
                        run, state = await self.load(session, id, lock=True)
                        step = await require(session, e.AgentStep, step_id)
                        before = state.state_revision
                        start = self.clock()
                        budget = RuntimeBudget(state, partial(self.remaining, state))
                        observation = None
                        try:
                            if state.phase == "planning":
                                await self.plan(session, state, step, budget)
                                decision = (
                                    "wait" if str(state.phase) == "waiting_input" else "continue"
                                )
                            else:
                                assert state.current_action_id is not None
                                progress = state.progress.actions[state.current_action_id]
                                action = progress.action
                                try:
                                    observation = await self.execute_action(
                                        session, state, action, budget
                                    )
                                except SAFE_FAILURES as exc:
                                    observation = ActionObservation(
                                        action_id=action.action_id,
                                        disposition="failed",
                                        reason_code=code(exc),
                                        targets={
                                            t: TargetOutcome(status="failed", reason=code(exc))
                                            for t in action_targets(action)
                                        },
                                        guardrails="failed",
                                    )
                                executed += 1
                                obs = e.Observation(
                                    action_step_id=step.id,
                                    action_data=observation.model_dump(mode="json"),
                                    status=ObservationStatus.ERROR
                                    if observation.disposition == "failed"
                                    else ObservationStatus.PARTIAL
                                    if observation.disposition
                                    in {"needs_input", "decision_required"}
                                    else ObservationStatus.OK,
                                    data_ref=observation.package_id,
                                    error_code=observation.reason_code,
                                )
                                session.add(obs)
                                await session.flush()
                                state.previous_observation_id = obs.id
                                progress.observation_id = obs.id
                                progress.package_id = observation.package_id
                                progress.child_run_id = observation.child_run_id
                                waited = observation.disposition in {
                                    "needs_input",
                                    "decision_required",
                                }
                                progress.status = (
                                    "waiting"
                                    if waited
                                    else "failed"
                                    if observation.disposition == "failed"
                                    else "completed"
                                )
                                if not waited:
                                    state.attempted_fingerprints.append(fingerprint(action))
                                for t, value in observation.targets.items():
                                    if t in state.progress.requested_targets:
                                        state.progress.requested_targets[t] = value
                                state.phase = "ready"
                                eval_step = await self.step(session, state, "evaluate", action)
                                decision = evaluate(state, observation)
                                eval_step.status = CallStatus.SUCCEEDED
                                eval_step.transition = StateTransition(
                                    before_revision=before,
                                    after_revision=before + 1,
                                    decision=decision,
                                    reason_code=observation.reason_code,
                                ).model_dump(mode="json")
                                if decision == "wait":
                                    state.phase = (
                                        "waiting_input"
                                        if observation.disposition == "needs_input"
                                        else "waiting_decision"
                                    )
                                    state.pending_reason = observation.reason_code
                                elif decision == "replan":
                                    state.needs_plan = True
                                    state.pending_reason = "authorized_path_changed"
                                elif decision == "finish":
                                    self.finish(state, observation.reason_code)
                            step.status = (
                                CallStatus.FAILED
                                if observation and observation.disposition == "failed"
                                else CallStatus.SUCCEEDED
                            )
                        except SAFE_FAILURES as exc:
                            step.status = CallStatus.FAILED
                            step.reason_code = code(exc)
                            self.finish(state, code(exc))
                            decision = "finish"
                        step.latency_ms = int((self.clock() - start) * 1000)
                        step.transition = StateTransition(
                            before_revision=before,
                            after_revision=before + 1,
                            decision=decision,
                            reason_code=state.pending_reason,
                        ).model_dump(mode="json")
                        state.dispatch_reservation = None
                        state.current_action_id = None
                        self.charge_time(state)
                        if (
                            state.usage.active_seconds >= state.limits.max_active_seconds
                            and state.phase not in TERMINAL
                        ):
                            self.finish(state, "active_time_exhausted")
                        run.requested_outputs = list(state.progress.requested_targets)
                        await self.save(session, run, state)
                except BaseException:
                    for store, ref in session.info.get("artifact_cleanup", []):
                        store.remove(ref)
                    raise
        return await self.view(id)
