"""Single-owner durable attempt journal; no business row locks or automatic replay."""

import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from weakref import WeakSet

from sqlalchemy import DateTime, event, or_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from career_agent.domain.rules import DomainError
from career_agent.models.contracts import (
    ModelCandidate,
    ModelGatewayError,
    ModelRequestContext,
    TaskSpec,
)
from career_agent.models.control.controller import Controller, Lease
from career_agent.models.control.recovery_contracts import (
    AutomaticPolicy,
    ControlEventData,
    DurableSnapshot,
    EffectiveState,
    JournalData,
    OperatorRequest,
    ReconcileRequest,
    utcnow,
)
from career_agent.models.control.state import adjust, operator_candidate, restore, snapshot
from career_agent.ops.entities import (
    AttemptJournal,
    ControlEvent,
    ControllerState,
    RecoveryIncident,
)
from career_agent.preparation.budget import input_bound
from career_agent.runtime.contracts import Usage


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


GLOBAL_SCOPE = "__global_control__"
_LIVE_OWNERS: WeakSet["DurableControl"] = WeakSet()
_GLOBAL_LOCKS: dict[tuple[str, asyncio.AbstractEventLoop], asyncio.Lock] = {}


class DurableControl:
    def __init__(
        self,
        engine: AsyncEngine,
        controller: Controller,
        policy: AutomaticPolicy,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self.engine, self.controller, self.policy, self.now = (
            engine,
            controller,
            policy.model_copy(deep=True),
            now,
        )
        self.controller.automatic_policy = self.policy.model_copy(deep=True)
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.scope = controller.policy.quota_scope
        if self.scope == GLOBAL_SCOPE:
            raise ValueError("reserved_control_scope")
        self.database_identity = digest(str(engine.url))
        self.policy_hash = digest(
            {
                "base": controller.policy.model_dump(mode="json"),
                "automatic": policy.model_dump(mode="json"),
            }
        )
        self.global_lock = _GLOBAL_LOCKS.setdefault(
            (self.database_identity, asyncio.get_running_loop()), asyncio.Lock()
        )
        self.lock = asyncio.Lock()
        self.start_lock = asyncio.Lock()
        self.ack_tasks: set[asyncio.Task[None]] = set()
        self.rollback_pending: set[UUID] = set()
        self.controller.utc_clock = now
        self.guard: AsyncConnection | None = None
        self.guard_key = int.from_bytes(
            hashlib.sha256(self.scope.encode()).digest()[:8], "big", signed=True
        )
        self.controller.effective.ready = False

    async def start(self) -> None:
        async with self.global_lock, self.start_lock:
            if self.guard is not None:
                if not self.controller.effective.ready:
                    raise ModelGatewayError("controller_not_ready")
                return
            await self._start()

    async def _start(self) -> None:
        try:
            self.guard = await self.engine.connect()
            owned = await self.guard.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": self.guard_key}
            )
            await self.guard.commit()
            if not owned:
                raise DomainError("controller_owner_exists", 409)
            async with self.lock, self.sessions.begin() as session:
                row = await session.scalar(
                    select(ControllerState)
                    .where(ControllerState.scope == self.scope)
                    .with_for_update()
                )
                last = await session.scalar(
                    select(ControlEvent)
                    .where(ControlEvent.scope == self.scope)
                    .order_by(ControlEvent.sequence.desc())
                )
                saved = (
                    DurableSnapshot.model_validate(
                        last.data["snapshot"] if last else row.data if row else {}
                    )
                    if (last or row)
                    else None
                )
                if saved:
                    if saved.policy_hash != self.policy_hash:
                        raise DomainError("controller_state_incompatible", 409)
                    restore(self.controller, saved, self.now())
                else:
                    restore(
                        self.controller,
                        DurableSnapshot(
                            policy_hash=self.policy_hash,
                            saved_at=self.now(),
                            effective=EffectiveState(),
                        ),
                        self.now(),
                    )
                global_event = await session.scalar(
                    select(ControlEvent)
                    .where(ControlEvent.scope == GLOBAL_SCOPE)
                    .order_by(ControlEvent.sequence.desc())
                )
                self.controller.effective.global_kill = bool(
                    global_event and global_event.data["snapshot"]["effective"]["global_kill"]
                )
                self.controller.effective.global_revision = (
                    global_event.sequence if global_event else 0
                )
                self.controller.effective.generation = uuid4()
                journals = list(
                    await session.scalars(
                        select(AttemptJournal).where(AttemptJournal.scope == self.scope)
                    )
                )
                for item in journals:
                    data = JournalData.model_validate(item.data)
                    if item.status == "reserved":
                        item.status = "not_dispatched"
                        data.provider_outcome = "recovered_not_dispatched"
                        data.recovered = True
                        item.data = data.model_dump(mode="json")
                    elif item.status in {"dispatch_intent", "unknown"}:
                        item.status = "unknown"
                        data.recovered = True
                        item.data = data.model_dump(mode="json")
                        await self._incident(session, item, "dispatch_outcome_unknown")
                        await self._link(session, item, missing_is_incident=False)
                        data = JournalData.model_validate(item.data)
                        expiry = (data.dispatched_at or item.created_at) + timedelta(
                            seconds=self.controller.policy.window_seconds
                        )
                        if expiry > self.now():
                            selection = data.selection
                            lease_id = UUID(selection["lease_id"])
                            mono = self.controller.clock()
                            age = max(
                                0,
                                (
                                    self.now() - (data.dispatched_at or item.created_at)
                                ).total_seconds(),
                            )
                            prior = self.controller.leases.get(lease_id)
                            restored_tokens = (
                                data.usage.input_tokens + data.usage.output_tokens
                                if data.usage
                                and data.usage.input_tokens is not None
                                and data.usage.output_tokens is not None
                                else data.financial_reservation.reserved_input_tokens
                                + selection["reserved_output_tokens"]
                            )
                            self.controller.leases[lease_id] = Lease(
                                lease_id,
                                selection["route"],
                                selection["provider"],
                                max(prior.tokens if prior else 0, restored_tokens),
                                selection["reserved_output_tokens"],
                                mono - age,
                                selection["traffic_class"] in {"background", "evaluation"},
                                dispatched=True,
                                settled=True,
                                dispatch_time=mono - age,
                                uncertain=data.usage is None
                                or data.usage.input_tokens is None
                                or data.usage.output_tokens is None,
                                sequence=self.controller.sequence,
                            )
                    elif item.status == "settled":
                        data.recovered = True
                        item.data = data.model_dump(mode="json")
                        await self._link(session, item)
                self.controller.effective.ready = False
                event = await self._event(
                    session, "bootstrap", "recovery_complete", uuid4(), "bootstrap", row=row
                )
            self.controller.effective.revision = event.sequence
            self.controller.effective.ready = True
            _LIVE_OWNERS.add(self)
        except BaseException:
            self.controller.effective.ready = False
            await self.close()
            raise

    def watch(self, session: AsyncSession, attempt_id: UUID) -> None:
        """Attach acknowledgement to the actual outer business transaction, not its flush."""
        key = (id(self), attempt_id)
        watched = session.info.setdefault("control_acknowledgements", set())
        if key in watched:
            return
        watched.add(key)

        def notify(committed: bool) -> None:
            if key not in watched:
                return
            watched.remove(key)
            if not committed:
                self.rollback_pending.add(attempt_id)
            task = asyncio.create_task(self.business_ack(attempt_id, committed))
            self.ack_tasks.add(task)
            task.add_done_callback(self.ack_tasks.discard)

        def committed(sync_session: Any) -> None:
            if not sync_session.in_nested_transaction():
                notify(True)

        def rolled_back(sync_session: Any) -> None:
            notify(False)  # A failed savepoint is conservatively protected too.

        event.listen(session.sync_session, "after_commit", committed)
        event.listen(session.sync_session, "after_rollback", rolled_back)

    async def business_ack(self, attempt_id: UUID, committed: bool) -> None:
        try:
            async with self.lock:
                await self._ready()
                async with self.sessions.begin() as session:
                    item = await session.scalar(
                        select(AttemptJournal)
                        .where(
                            AttemptJournal.scope == self.scope,
                            AttemptJournal.attempt_id == attempt_id,
                        )
                        .with_for_update()
                    )
                    if item is None or item.status in {"not_dispatched", "business_committed"}:
                        return
                    if committed:
                        await self._link(session, item, missing_is_incident=False)
                        if item.status != "business_committed":
                            return
                    elif item.status != "reserved":
                        data = JournalData.model_validate(item.data)
                        if data.recovered:
                            self.rollback_pending.discard(attempt_id)
                            return
                        data.recovered = True
                        item.data = data.model_dump(mode="json")
                        if item.status == "dispatch_intent":
                            item.status = "unknown"
                        await self._incident(session, item, "business_transaction_rolled_back")
                    recorded = await self._event(
                        session,
                        "business_ack",
                        "business_committed" if committed else "business_rolled_back",
                        uuid4(),
                        "ack",
                        attempt_id=attempt_id,
                    )
                self.controller.effective.revision = recorded.sequence
                self.rollback_pending.discard(attempt_id)
        except BaseException:
            self.controller.effective.ready = False
            # Admission fails closed if acknowledgement cannot be made durable.

    async def close(self) -> None:
        if self.ack_tasks:
            await asyncio.gather(*list(self.ack_tasks))
        _LIVE_OWNERS.discard(self)
        self.controller.effective.ready = False
        if self.guard is not None:
            try:
                await self.guard.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": self.guard_key}
                )
                await self.guard.commit()
            finally:
                await self.guard.close()
                self.guard = None

    async def _ready(self) -> None:
        if not self.controller.effective.ready or self.guard is None:
            raise ModelGatewayError("controller_not_ready")
        try:
            await self.guard.execute(text("SELECT 1"))
            await self.guard.commit()
        except Exception:
            self.controller.effective.ready = False
            raise ModelGatewayError("controller_ownership_lost") from None

    async def _event(
        self,
        session: AsyncSession,
        kind: str,
        reason: str,
        request_id: UUID,
        request_hash: str,
        *,
        row: ControllerState | None = None,
        route: str | None = None,
        attempt_id: UUID | None = None,
        logical_operation_id: UUID | None = None,
        window: bool = False,
        observations: int | None = None,
        effective: EffectiveState | None = None,
        decisions: list[dict[str, Any]] | None = None,
    ) -> ControlEvent:
        if row is None:
            row = await session.scalar(
                select(ControllerState).where(ControllerState.scope == self.scope).with_for_update()
            )
        if (
            row is not None
            and kind != "bootstrap"
            and row.data["effective"]["generation"] != str(self.controller.effective.generation)
        ):
            raise ModelGatewayError("controller_generation_stale")
        before = max(row.revision if row else 0, self.controller.effective.revision)
        state = snapshot(self.controller, self.now(), self.policy_hash)
        state.effective = (effective or self.controller.effective).model_copy(deep=True)
        state.effective.revision = before + 1
        if row is None:
            row = ControllerState(
                scope=self.scope, revision=before + 1, data=state.model_dump(mode="json")
            )
            session.add(row)
        else:
            row.revision = before + 1
            row.data = state.model_dump(mode="json")
        event = ControlEvent(
            scope=self.scope,
            sequence=before + 1,
            request_id=request_id,
            request_hash=request_hash,
            data=ControlEventData(
                logical_operation_id=logical_operation_id,
                kind=kind,
                reason=reason,
                policy_version=self.policy.version,
                before_revision=before,
                after_revision=before + 1,
                occurred_at=self.now(),
                route=route,
                attempt_id=attempt_id,
                snapshot=state,
                observations=observations,
                decisions=decisions or [],
                input_window_start=self.now() - timedelta(seconds=self.policy.window_seconds)
                if window
                else None,
                input_window_end=self.now() if window else None,
            ).model_dump(mode="json"),
        )
        session.add(event)
        await session.flush()
        return event

    async def _recovery_admission(
        self, session: AsyncSession, context: ModelRequestContext
    ) -> None:
        uncertain = await session.scalars(
            select(AttemptJournal).where(
                AttemptJournal.scope == self.scope,
                AttemptJournal.status.in_(["unknown", "settled"]),
            )
        )
        for unresolved in uncertain:
            previous = JournalData.model_validate(unresolved.data)
            if unresolved.status != "unknown" and not previous.recovered:
                continue
            if (
                not previous.budget_owner_refs
                or not context.budget_owner_refs
                or set(previous.budget_owner_refs) & set(context.budget_owner_refs)
            ):
                raise ModelGatewayError("recovery_decision_required")

    async def prepare(
        self, context: ModelRequestContext, candidate: ModelCandidate, task: TaskSpec
    ) -> None:
        selection = context.selection
        assert selection is not None
        if self.ack_tasks:
            await asyncio.gather(*list(self.ack_tasks))
        async with self.lock:
            await self._ready()
            try:
                async with self.sessions.begin() as session:
                    old = await session.scalar(
                        select(AttemptJournal).where(
                            AttemptJournal.attempt_id == selection.attempt_id
                        )
                    )
                    if old:
                        return
                    await self._recovery_admission(session, context)
                    inputs = input_bound(context, task)
                    cost = (
                        inputs * candidate.input_cost_per_million
                        + context.max_output_tokens * candidate.output_cost_per_million
                    ) / Decimal(1000000)
                    data = JournalData(
                        selection=selection.model_dump(mode="json", exclude={"deadline"}),
                        budget_owner_refs=context.budget_owner_refs,
                        financial_reservation=Usage(
                            reserved_input_tokens=inputs,
                            reserved_output_tokens=context.max_output_tokens,
                            budget_reserved_usd=cost,
                            pricing_version=candidate.pricing_version,
                        ),
                    )
                    session.add(
                        AttemptJournal(
                            scope=self.scope,
                            attempt_id=selection.attempt_id,
                            operation_id=context.logical_operation_id,
                            status="reserved",
                            data=data.model_dump(mode="json"),
                        )
                    )
                    event = await self._event(
                        session,
                        "reserved",
                        "attempt_reserved",
                        uuid4(),
                        "reserved",
                        route=selection.route,
                        attempt_id=selection.attempt_id,
                    )
                self.controller.effective.revision = event.sequence
            except ModelGatewayError:
                raise
            except BaseException:
                self.controller.effective.ready = False
                raise

    async def admission_denied(
        self, context: ModelRequestContext, decisions: list[dict[str, Any]]
    ) -> None:
        async with self.lock:
            if self.guard is None or not self.controller.effective.ready:
                return  # Boot/ownership failure is fail-closed, not a provider attempt.
            async with self.sessions.begin() as session:
                event = await self._event(
                    session,
                    "admission_denied",
                    "admission_denied",
                    uuid4(),
                    "admission",
                    decisions=decisions,
                    logical_operation_id=context.logical_operation_id,
                )
            self.controller.effective.revision = event.sequence

    async def intent(self, context: ModelRequestContext) -> None:
        assert context.selection is not None
        if self.ack_tasks:
            await asyncio.gather(*list(self.ack_tasks))
        async with self.lock:
            await self._ready()
            try:
                async with self.sessions.begin() as session:
                    await self._recovery_admission(session, context)
                    item = await session.scalar(
                        select(AttemptJournal)
                        .where(AttemptJournal.attempt_id == context.selection.attempt_id)
                        .with_for_update()
                    )
                    if item is None or item.status != "reserved":
                        raise ModelGatewayError("invalid_dispatch_intent")
                    data = JournalData.model_validate(item.data)
                    data.dispatched_at = self.now()
                    item.status = "dispatch_intent"
                    item.data = data.model_dump(mode="json")
                    event = await self._event(
                        session,
                        "dispatch_intent",
                        "dispatch_intent",
                        uuid4(),
                        "intent",
                        route=context.selection.route,
                        attempt_id=context.selection.attempt_id,
                    )
                self.controller.effective.revision = event.sequence
            except ModelGatewayError as exc:
                if exc.code != "recovery_decision_required":
                    self.controller.effective.ready = False
                raise
            except BaseException:
                self.controller.effective.ready = False
                raise

    async def finish(
        self,
        context: ModelRequestContext,
        usage: Usage | None,
        code: str | None,
        dispatched: bool,
        latency_ms: int,
    ) -> None:
        assert context.selection is not None
        async with self.lock:
            await self._ready()
            try:
                async with self.sessions.begin() as session:
                    item = await session.scalar(
                        select(AttemptJournal)
                        .where(AttemptJournal.attempt_id == context.selection.attempt_id)
                        .with_for_update()
                    )
                    if item is None:
                        raise ModelGatewayError("journal_missing")
                    if item.status in {"settled", "not_dispatched", "business_committed"}:
                        return
                    data = JournalData.model_validate(item.data)
                    data.dispatch_confirmed = dispatched
                    data.usage = usage
                    data.provider_outcome = code or "completed"
                    data.latency_ms = latency_ms
                    data.settled_at = self.now()
                    item.status = "settled" if dispatched else "not_dispatched"
                    item.data = data.model_dump(mode="json")
                    event = await self._event(
                        session,
                        item.status,
                        data.provider_outcome,
                        uuid4(),
                        "finish",
                        route=context.selection.route,
                        attempt_id=context.selection.attempt_id,
                    )
                self.controller.effective.revision = event.sequence
            except BaseException:
                self.controller.effective.ready = False
                raise

    async def _incident(
        self, session: AsyncSession, item: AttemptJournal, reason: str
    ) -> RecoveryIncident:
        incident = await session.scalar(
            select(RecoveryIncident).where(RecoveryIncident.attempt_id == item.attempt_id)
        )
        if incident is None:
            incident = RecoveryIncident(
                scope=self.scope, attempt_id=item.attempt_id, reason=reason, status="open"
            )
            session.add(incident)
        return incident

    async def _link(
        self, session: AsyncSession, item: AttemptJournal, *, missing_is_incident: bool = True
    ) -> None:
        from career_agent.evaluation.entities import InvocationRow
        from career_agent.infrastructure.entities import ModelCall

        data = JournalData.model_validate(item.data)
        call = await session.scalar(
            select(ModelCall).where(
                ModelCall.versions["control_metadata"]["attempt_id"].astext == str(item.attempt_id)
            )
        )
        if call is None or call.status.value not in {"succeeded", "failed"}:
            if missing_is_incident:
                await self._incident(session, item, "provider_result_without_business_commit")
            return
        if (
            call.logical_operation_id != item.operation_id
            or call.provider != data.selection["provider"]
            or call.model != data.selection["model"]
            or call.task_type != data.selection["task_type"]
        ):
            raise DomainError("journal_provenance_mismatch")
        data.model_call_id = call.id
        invocation = await session.scalar(
            select(InvocationRow).where(InvocationRow.model_call_id == call.id)
        )
        if invocation and invocation.data.get("output_ref"):
            data.artifact_ref = UUID(invocation.data["output_ref"])
        if call.status.value == "succeeded" and invocation is None:
            from career_agent.evaluation.entities import JudgeRow

            judge = await session.scalar(
                select(JudgeRow).where(
                    JudgeRow.model_call_id == call.id, JudgeRow.status == "completed"
                )
            )
            if judge is None:
                if missing_is_incident:
                    await self._incident(session, item, "provider_result_without_business_commit")
                return
            data.artifact_ref = judge.id
        if data.usage is None:
            data.usage = Usage.model_validate(call.usage)
            data.provider_outcome = call.error_code or "completed"
            data.dispatch_confirmed = True
        item.data = data.model_dump(mode="json")
        item.status = "business_committed"
        incident = await session.scalar(
            select(RecoveryIncident).where(RecoveryIncident.attempt_id == item.attempt_id)
        )
        if incident:
            incident.status = "resolved"
            incident.resolution = "business_commit_found"
            incident.revision += 1

    async def reconcile(self, attempt_id: UUID, request: ReconcileRequest) -> dict[str, Any]:
        async with self.lock:
            await self._ready()
            async with self.sessions.begin() as session:
                old = await self._receipt(
                    session,
                    request.request_id,
                    digest(
                        {"attempt_id": str(attempt_id), "request": request.model_dump(mode="json")}
                    ),
                )
                if old:
                    return {"revision": old.sequence, "idempotent": True}
                item = await session.scalar(
                    select(AttemptJournal)
                    .where(
                        AttemptJournal.attempt_id == attempt_id, AttemptJournal.scope == self.scope
                    )
                    .with_for_update()
                )
                if item is None:
                    raise DomainError("not_found", 404)
                incident = await session.scalar(
                    select(RecoveryIncident).where(RecoveryIncident.attempt_id == attempt_id)
                )
                if (incident.revision if incident else 0) != request.expected_revision:
                    raise DomainError("revision_conflict", 409)
                if item.status in {"settled", "unknown"}:
                    await self._link(session, item)
                if (
                    request.resolution == "manual_acknowledge"
                    and incident
                    and incident.status != "resolved"
                ):
                    # Acknowledgement is not financial forgiveness or replay authorization.
                    incident.status = "acknowledged"
                    incident.resolution = request.reason_code
                    incident.revision += 1
                event = await self._event(
                    session,
                    "reconcile",
                    request.reason_code,
                    request.request_id,
                    digest(
                        {"attempt_id": str(attempt_id), "request": request.model_dump(mode="json")}
                    ),
                    attempt_id=attempt_id,
                )
            self.controller.effective.revision = event.sequence
            return {"revision": event.sequence, "attempt_status": item.status, "replayed": False}

    async def _receipt(
        self, session: AsyncSession, request_id: UUID, request_hash: str
    ) -> ControlEvent | None:
        old = await session.scalar(
            select(ControlEvent).where(
                ControlEvent.scope == self.scope, ControlEvent.request_id == request_id
            )
        )
        if old and old.request_hash != request_hash:
            raise DomainError("idempotency_conflict", 409)
        return old

    async def operate(self, request: OperatorRequest) -> dict[str, Any]:
        async with self.global_lock, self.lock:
            await self._ready()
            before = self.controller.effective.model_copy(deep=True)
            try:
                async with self.sessions.begin() as session:
                    old = await self._receipt(
                        session, request.request_id, digest(request.model_dump(mode="json"))
                    )
                    if old:
                        return {"revision": old.sequence, "idempotent": True}
                    row = await session.scalar(
                        select(ControllerState)
                        .where(ControllerState.scope == self.scope)
                        .with_for_update()
                    )
                    if row is None or row.revision != request.expected_revision:
                        raise DomainError("revision_conflict", 409)
                    candidate = operator_candidate(
                        self.controller.effective,
                        request,
                        self.policy,
                        self.controller.policy,
                        self.now(),
                    )
                    decisions = (
                        await self._tick(session, candidate) if request.action == "tick" else []
                    )
                    if request.action == "global_kill":
                        candidate.global_revision = await self._persist_global(session, request)
                    event = await self._event(
                        session,
                        request.action,
                        "operator_" + request.action,
                        request.request_id,
                        digest(request.model_dump(mode="json")),
                        row=row,
                        window=request.action == "tick",
                        effective=candidate,
                        decisions=decisions,
                    )
                candidate.revision = event.sequence
                self.controller.effective = candidate
                if request.action == "global_kill":
                    for owner in _LIVE_OWNERS:
                        if owner.database_identity == self.database_identity:
                            owner.controller.effective.global_kill = bool(request.enabled)
                            owner.controller.effective.global_revision = candidate.global_revision
                return {
                    "revision": event.sequence,
                    "effective": self.controller.effective.model_dump(mode="json"),
                }
            except DomainError:
                self.controller.effective = before
                raise
            except BaseException:
                before.ready = False
                self.controller.effective = before
                raise

    async def _persist_global(self, session: AsyncSession, request: OperatorRequest) -> int:
        # All owners serialize only the global control row; no business/budget row lock.
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 7310402001})
        row = await session.scalar(
            select(ControllerState).where(ControllerState.scope == GLOBAL_SCOPE).with_for_update()
        )
        last = await session.scalar(
            select(ControlEvent)
            .where(ControlEvent.scope == GLOBAL_SCOPE)
            .order_by(ControlEvent.sequence.desc())
        )
        before = max(row.revision if row else 0, last.sequence if last else 0)
        if request.expected_global_revision != before:
            raise DomainError("global_revision_conflict", 409)
        state = DurableSnapshot(
            policy_hash="global-control-v1",
            saved_at=self.now(),
            effective=EffectiveState(revision=before + 1, global_kill=bool(request.enabled)),
        )
        if row is None:
            session.add(
                ControllerState(
                    scope=GLOBAL_SCOPE, revision=before + 1, data=state.model_dump(mode="json")
                )
            )
        else:
            row.revision, row.data = before + 1, state.model_dump(mode="json")
        session.add(
            ControlEvent(
                scope=GLOBAL_SCOPE,
                sequence=before + 1,
                request_id=request.request_id,
                request_hash=digest(request.model_dump(mode="json")),
                data=ControlEventData(
                    kind="global_kill",
                    reason="operator_global_kill",
                    policy_version=self.policy.version,
                    before_revision=before,
                    after_revision=before + 1,
                    occurred_at=self.now(),
                    snapshot=state,
                ).model_dump(mode="json"),
            )
        )

        return before + 1

    async def _tick(self, session: AsyncSession, candidate: EffectiveState) -> list[dict[str, Any]]:
        now = self.now()
        for route in list(candidate.overrides):
            if candidate.overrides[route].expires_at <= now:
                del candidate.overrides[route]
        rows = list(
            await session.scalars(
                select(AttemptJournal).where(
                    AttemptJournal.scope == self.scope,
                    or_(
                        AttemptJournal.status.in_(["reserved", "settled"]),
                        (AttemptJournal.status == "business_committed")
                        & (
                            AttemptJournal.data["settled_at"].astext.cast(DateTime(timezone=True))
                            >= now - timedelta(seconds=self.policy.window_seconds)
                        ),
                    ),
                )
            )
        )
        facts: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row.status == "reserved":
                data = JournalData.model_validate(row.data)
                lease = self.controller.leases.get(UUID(data.selection["lease_id"]))
                if lease is None or lease.released:
                    row.status = "not_dispatched"
                    data.provider_outcome = "cancelled_before_dispatch"
                    row.data = data.model_dump(mode="json")
                continue
            if row.status == "settled":
                await self._link(session, row, missing_is_incident=False)
            d = JournalData.model_validate(row.data)
            if d.settled_at and (now - d.settled_at).total_seconds() <= self.policy.window_seconds:
                facts.setdefault(d.selection["route"], []).append(
                    {
                        "outcome": d.provider_outcome,
                        "task_type": d.selection["task_type"],
                        "output_tokens": d.usage.output_tokens if d.usage else None,
                    }
                )
        decisions = []
        for route, items in facts.items():
            base = self.controller.policy.routes.get(route, self.controller.policy.default_route)
            provider = route.split(":", 1)[0]
            bucket = self.controller.policy.feedback_bucket(provider, route)
            feedback = self.controller.feedback.get(self.controller.feedback_key(provider, bucket))
            mono = self.controller.clock()
            pressure = bool(
                feedback
                and (
                    feedback.blocked_until > mono
                    or feedback.requests == 0
                    and feedback.requests_until > mono
                    or feedback.tokens == 0
                    and feedback.tokens_until > mono
                )
            )
            for item in items:
                item["capacity_pressure"] = pressure
            reason = adjust(candidate, route, items, self.policy, now, base.concurrency)
            if reason:
                decisions.append({"route": route, "reason": reason, "observations": len(items)})
        return decisions

    async def loop(self) -> None:
        while True:
            await asyncio.sleep(self.policy.tick_seconds)
            try:
                await self.operate(
                    OperatorRequest(
                        request_id=uuid4(),
                        expected_revision=self.controller.effective.revision,
                        action="tick",
                    )
                )
            except DomainError as exc:
                if exc.code != "revision_conflict":
                    self.controller.effective.ready = False
                    return
            except Exception:
                self.controller.effective.ready = False
                return
