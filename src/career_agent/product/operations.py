"""Committed operation handles, explicit synchronous execution, no hidden worker/replay."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from career_agent.application.services import require
from career_agent.config import Settings
from career_agent.domain.rules import CallStatus, DomainError, RunStatus
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.claims import claim
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import WorkflowState
from career_agent.preparation.providers import dependencies
from career_agent.preparation.workflows import PreparationWorkflow
from career_agent.product.contracts import OperationCreate, OperationOut
from career_agent.product.entities import ProductOperation
from career_agent.runtime.contracts import Budget, Usage


def view(row: ProductOperation) -> OperationOut:
    return OperationOut.model_validate(
        {
            "id": row.id,
            "request_id": row.request_id,
            "kind": row.kind,
            "status": row.status,
            "run_id": row.run_id,
            "package_id": row.package_id,
            "research_report_id": row.research_report_id,
            "reason": row.reason,
            "created_at": row.created_at,
            "allowed_actions": ["execute"]
            if row.status == "pending"
            else ["inspect_recovery"]
            if row.status == "recovery_required"
            else ["read"],
        }
    )


async def create(session: AsyncSession, payload: OperationCreate) -> OperationOut:
    await claim(session, "product-request:" + str(payload.request_id))
    old = await session.scalar(
        select(ProductOperation).where(ProductOperation.request_id == payload.request_id)
    )
    data = payload.model_dump(mode="json")
    if old:
        if OperationCreate.model_validate(old.payload).model_dump(mode="json") != data:
            raise DomainError("idempotency_conflict")
        return view(old)
    if payload.application_binding is not None:
        from career_agent.product.bindings import validate_request

        await validate_request(session, payload)
    if payload.kind != "company_research":
        assert payload.request.profile_id is not None
        await require(session, e.PersonalProfile, payload.request.profile_id)
    await require(session, e.JobRevision, payload.request.job_revision_id)
    row = ProductOperation(
        request_id=payload.request_id, kind=payload.kind, run_id=uuid4(), payload=data
    )
    session.add(row)
    await session.flush()
    return view(row)


async def read(session: AsyncSession, id: UUID) -> OperationOut:
    row = await require(session, ProductOperation, id, lock=True)
    if row.status == "running":
        # Session lock is held for the live request; after process loss it is released by PG.
        free = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 4302))"), {"key": str(id)}
        )
        if free:
            row.status, row.reason = "recovery_required", "execution_interrupted"
    return view(row)


def terminal_status(status: str, reason: str | None) -> str:
    if reason == "recovery_decision_required":
        return "recovery_required"
    return {"completed": "success", "failed": "failure"}.get(status, status)


@asynccontextmanager
async def business_transaction(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    # Observe the transaction outcome, not success/failure of session close or response delivery.
    # Unknown commit outcomes retain files for reconciliation; never guess rollback.
    committed = rolled_back = body_failed = False

    def did_commit(session: Session) -> None:
        nonlocal committed
        if not session.in_nested_transaction():
            committed = True

    def did_rollback(session: Session) -> None:
        nonlocal rolled_back
        if not session.in_nested_transaction():
            rolled_back = True

    async with sessions() as session:
        event.listen(session.sync_session, "after_commit", did_commit)
        event.listen(session.sync_session, "after_rollback", did_rollback)
        try:
            async with session.begin():
                try:
                    yield session
                except BaseException:
                    body_failed = True
                    raise
        except BaseException:
            # A rollback following a failed COMMIT does not prove the server never committed.
            if body_failed and rolled_back and not committed:
                for store, ref in session.info.get("artifact_cleanup", []):
                    store.remove(ref)
            raise
        finally:
            event.remove(session.sync_session, "after_commit", did_commit)
            event.remove(session.sync_session, "after_rollback", did_rollback)


async def execute(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    id: UUID,
    factory: Any = dependencies,
) -> OperationOut:
    engine = sessions.kw["bind"]
    async with engine.connect() as lock:
        acquired = await lock.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 4302))"), {"key": str(id)}
        )
        await lock.commit()
        if not acquired:
            raise DomainError("operation_in_progress")
        try:
            async with sessions.begin() as session:
                row = await require(session, ProductOperation, id, lock=True)
                if row.status == "running":
                    row.status, row.reason = "recovery_required", "execution_interrupted"
                if row.status != "pending":
                    return view(row)
                payload = OperationCreate.model_validate(row.payload)
                run_id = row.run_id
                row.status = "running"
            try:
                async with factory(settings, payload.request.mode) as (gateway, research):
                    async with business_transaction(sessions) as session:
                        runner = PreparationWorkflow(
                            session, settings, gateway, research, payload.request
                        )
                        runner.execution_run_id = run_id
                        if payload.kind == "company_research":
                            await research_execute(runner, run_id)
                            package_id = None
                            research_id = runner.state.research_report_id
                            reason = runner.state.stop_reason
                            status = terminal_status("failed" if reason else "completed", reason)
                        else:
                            result = await runner.execute(payload.kind)
                            package_id = UUID(result["package_id"])
                            research_id = None
                            outcome = result["outcome"]
                            reason = outcome["reason"]
                            status = terminal_status(outcome["status"], reason)
                        row = await require(session, ProductOperation, id, lock=True)
                        row.status, row.reason = status, reason
                        row.package_id, row.research_report_id = package_id, research_id
                        # Final operation and authoritative business results commit together.
            except BaseException as exc:
                failure_reason = (
                    exc.code
                    if isinstance(exc, (DomainError, ModelGatewayError))
                    else "execution_interrupted"
                )

                async def interrupted() -> None:
                    async with sessions.begin() as session:
                        row = await require(session, ProductOperation, id, lock=True)
                        if row.status == "running":
                            row.status = "recovery_required"
                            row.reason = failure_reason

                await asyncio.shield(interrupted())
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if not isinstance(exc, Exception):
                    raise
            async with sessions() as session:
                return view(await require(session, ProductOperation, id))
        finally:
            await lock.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 4302))"), {"key": str(id)}
            )
            await lock.commit()


async def research_execute(r: PreparationWorkflow, run_id: UUID) -> None:
    limits = r.request.limits.model_copy(deep=True)
    limits.max_estimated_cost = min(limits.max_estimated_cost, r.settings.max_run_cost)
    r.run = e.AgentRun(
        id=run_id,
        workflow="company_research",
        workflow_version="company-research-product-v1",
        status=RunStatus.RUNNING,
        started_at=e.utcnow(),
        requested_outputs=["company_research_synthesis"],
        budget=Budget(
            token_limit=limits.max_input_tokens + limits.max_output_tokens,
            cost_limit=limits.max_estimated_cost,
        ).model_dump(mode="json"),
    )
    r.session.add(r.run)
    await r.session.flush()
    r.state = WorkflowState(
        run_id=run_id,
        workflow="company_research",
        workflow_version="company-research-product-v1",
        mode=r.request.mode,
        profile_id=None,
        job_revision_id=r.request.job_revision_id,
        requested_outputs=["company_research_synthesis"],
        limits=limits,
    )
    await r.node("validate_research_inputs")
    if not r.state.stop_reason:
        await r.node("research_company")
        if r.step.status == CallStatus.FAILED:
            r.state.stop_reason = r.step.reason_code or "research_unavailable"
    r.run.status = RunStatus.FAILED if r.state.stop_reason else RunStatus.COMPLETED
    r.run.stop_reason, r.run.finished_at = r.state.stop_reason, e.utcnow()
    u = r.state.usage
    r.run.consumed_usage = Usage(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        estimated_cost=u.estimated_cost,
        budget_reserved_usd=u.budget_reserved_usd,
        reserved_input_tokens=u.reserved_input_tokens,
        reserved_output_tokens=u.reserved_output_tokens,
        search_calls=u.search_calls,
    ).model_dump(mode="json")
    if r.accepted_call_id and r.state.research_report_id:
        from career_agent.evaluation.recording import bind_artifact

        await bind_artifact(
            r.session, r.accepted_call_id, r.state.research_report_id, r.settings.judge_sampling
        )
