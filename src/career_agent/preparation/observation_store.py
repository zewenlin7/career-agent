"""Private, exact read-only search observations; never a model response cache."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import Field, ValidationError
from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.domain.schemas import Contract
from career_agent.infrastructure.claims import claim
from career_agent.infrastructure.db import Base, ValidatedJSON
from career_agent.infrastructure.entities import Row
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.research import (
    ResearchAdapter,
    SearchInput,
    SearchResult,
    SearchReuseContract,
    SearchToolMetadata,
)

IDENTITY_VERSION = "search-observation-v1"


def digest(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def normalize_query(query: str) -> str:
    # No case folding, punctuation removal or semantic normalization.
    return " ".join(query.split())


class StoredSearch(Contract):
    identity_version: str = IDENTITY_VERSION
    identity: dict[str, Any]
    result: SearchResult
    source_refs: list[UUID] = Field(default_factory=list)


class SearchObservation(Row, Base):
    __tablename__ = "search_observations"
    identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(StoredSearch))


class ReuseDecision(Row, Base):
    __tablename__ = "reuse_decisions"
    run_id: Mapped[UUID | None] = mapped_column(index=True)  # no dependency on uncommitted run
    category: Mapped[str] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(128))
    disposition: Mapped[str] = mapped_column(String(20))
    identity_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    observation_id: Mapped[UUID | None] = mapped_column()


async def search_reuse(
    sessions: async_sessionmaker[AsyncSession],
    adapter: ResearchAdapter,
    query: SearchInput,
    *,
    scope: str,
    mode: str,
    clock: Callable[[], datetime],
    ttl_hours: int,
    run_id: UUID,
    fetch: Callable[[SearchInput], Awaitable[SearchResult]],
    wait_seconds: float = 5,
    force_refresh: bool = False,
) -> tuple[SearchResult, bool]:
    normalized = SearchInput(query=normalize_query(query.query))
    meta = SearchToolMetadata()
    contract = getattr(adapter, "reuse_contract", None)
    if not isinstance(contract, SearchReuseContract):
        # Unknown adapter contracts cannot safely share persisted observations.
        return await fetch(normalized), False
    identity = {
        "version": IDENTITY_VERSION,
        "provider": contract.model_dump(mode="json"),
        "tool": {
            key: getattr(meta, key)
            for key in (
                "tool_name",
                "tool_version",
                "input_schema_version",
                "output_schema_version",
            )
        },
        "query": normalized.query,
        "scope": scope,
        "mode": mode,
    }
    key = digest(identity)
    # Independent commit preserves successful observations even if synthesis/business rolls back.
    async with sessions.begin() as session:
        contended = await claim(session, "search:" + key, wait_seconds=wait_seconds)
        now = clock()
        candidates = await session.scalars(
            select(SearchObservation)
            .where(
                SearchObservation.identity_hash == key,
                SearchObservation.retrieved_at <= now,
                SearchObservation.expires_at > now,
            )
            .order_by(SearchObservation.retrieved_at.desc())
        )
        for row in candidates:
            if force_refresh:
                break
            try:
                data = StoredSearch.model_validate(row.data)
            except ValidationError:
                continue
            if (
                row.data.get("identity_version") != IDENTITY_VERSION
                or data.identity != identity
                or data.source_refs != [item.id for item in data.result.evidence]
                or digest(data.result.model_dump(mode="json")) != row.content_hash
            ):
                continue
            session.add(
                ReuseDecision(
                    run_id=run_id,
                    category="external_observation",
                    operation=meta.tool_name,
                    disposition="reused",
                    identity_hash=key,
                    observation_id=row.id,
                )
            )
            return data.result, True
        if contended and not force_refresh:
            raise ModelGatewayError("reuse_result_unavailable")
        result = await fetch(normalized)
        now = clock()
        data = StoredSearch(
            identity=identity, result=result, source_refs=[e.id for e in result.evidence]
        )
        row = SearchObservation(
            identity_hash=key,
            content_hash=digest(result.model_dump(mode="json")),
            retrieved_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            data=data.model_dump(mode="json"),
        )
        session.add(row)
        await session.flush()
        session.add(
            ReuseDecision(
                run_id=run_id,
                category="external_observation",
                operation=meta.tool_name,
                disposition="executed",
                identity_hash=key,
                observation_id=row.id,
            )
        )
        return result, False
