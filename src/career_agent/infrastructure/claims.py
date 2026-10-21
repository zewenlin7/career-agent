"""Short bounded waits for transaction-scoped business idempotency claims."""

import asyncio
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.models.contracts import ModelGatewayError

CLAIM_VERSION = "business-reuse-claim-v2"


async def claim(session: AsyncSession, key: str, *, wait_seconds: float = 5) -> bool:
    # The DB lock lives until business commit/rollback, not merely until a model returns.
    # Try-lock polling leaves the transaction usable on contention timeout. No worker/replay.
    deadline = time.monotonic() + max(0, wait_seconds)
    contended = False
    while True:
        if await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 4301))"), {"key": key}
        ):
            return contended
        contended = True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ModelGatewayError("reuse_in_progress")
        await asyncio.sleep(min(0.025, remaining))
