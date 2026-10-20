"""One process owner, shared by live request gateways and explicit CLI lifecycles."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from career_agent.config import Settings
from career_agent.infrastructure.db import make_engine
from career_agent.models.control.controller import Controller
from career_agent.models.control.durable import DurableControl, digest

_owners: dict[str, tuple[DurableControl, int, asyncio.Task[None]]] = {}
_lock = asyncio.Lock()


@asynccontextmanager
async def control_owner(settings: Settings) -> AsyncIterator[DurableControl]:
    scope = (
        digest(settings.database_url.get_secret_value())
        + ":"
        + settings.runtime_control.quota_scope
    )
    async with _lock:
        if scope in _owners:
            owner, count, task = _owners[scope]
            if (
                owner.policy != settings.automatic_control
                or owner.controller.policy != settings.runtime_control
            ):
                raise ValueError("control_policy_conflict")
            _owners[scope] = owner, count + 1, task
        else:
            engine = make_engine(settings)
            owner = DurableControl(
                engine, Controller(settings.runtime_control), settings.automatic_control
            )
            try:
                await owner.start()
            except BaseException:
                await engine.dispose()
                raise
            task = asyncio.create_task(owner.loop())
            _owners[scope] = owner, 1, task
    try:
        yield owner
    finally:
        async with _lock:
            owner, count, task = _owners[scope]
            if count > 1:
                _owners[scope] = owner, count - 1, task
            else:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                await owner.close()
                await owner.engine.dispose()
                del _owners[scope]
