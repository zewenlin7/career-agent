"""Temporary PostgreSQL database and private temp artifact store per workflow trial."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_agent.application.services import create_fact, verify_user_fact
from career_agent.config import Settings
from career_agent.domain.schemas import FactCreate
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.research import ResearchAdapter

_MIGRATION_LOCK = asyncio.Lock()


@asynccontextmanager
async def sandbox(
    settings: Settings,
    gateway: ModelGateway,
    research: ResearchAdapter,
    *,
    allow_paid_models: bool = False,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    from career_agent.api.app import create_app

    if any(candidate.provider != "fixture" for candidate in gateway.registry) and not (
        allow_paid_models
        and settings.live_enabled
        and all(c.provider == "openai" for c in gateway.registry)
    ):
        raise ModelGatewayError("eval_live_mode_forbidden")
    server = make_url(settings.database_url.get_secret_value()).set(database="postgres")
    name = "career_eval_" + uuid4().hex
    url = server.set(database=name).render_as_string(hide_password=False)
    admin = create_async_engine(
        server, isolation_level="AUTOCOMMIT", poolclass=NullPool, hide_parameters=True
    )
    created = False
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        cfg = Config("alembic.ini")
        cfg.attributes["database_url"] = url
        # Alembic uses process-global environment state; trial execution remains concurrent.
        async with _MIGRATION_LOCK:
            await asyncio.to_thread(command.upgrade, cfg, "head")
        with TemporaryDirectory(prefix="career_eval_") as directory:
            local = settings.model_copy(
                update={
                    "database_url": SecretStr(url),
                    "data_dir": Path(directory),
                    "live_enabled": False,
                    "ops_enabled": False,
                    "ops_token": None,
                    "openai_api_key": None,
                    "tavily_api_key": None,
                }
            )
            app = create_app(local)

            @asynccontextmanager
            async def dependencies(
                conf: Settings, mode: str
            ) -> AsyncIterator[tuple[ModelGateway, ResearchAdapter]]:
                # Business mode is frozen context (cache identity), not provider authorization.
                if mode not in {"fixture", "live"}:
                    raise ModelGatewayError("eval_live_mode_forbidden")
                yield gateway, research

            async with app.router.lifespan_context(app):
                app.state.sessions.configure(info={"evaluation_data_dir": Path(directory)})
                app.state.preparation_dependencies = dependencies
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://eval.local"
                ) as client:
                    yield client, app.state.sessions
    finally:
        if created:
            async with admin.connect() as conn:
                await conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


def replace_refs(value: Any, refs: dict[str, str]) -> Any:
    if isinstance(value, str):
        return refs.get(value, value)
    if isinstance(value, list):
        return [replace_refs(v, refs) for v in value]
    if isinstance(value, dict):
        return {k: replace_refs(v, refs) for k, v in value.items()}
    return value


async def bootstrap(
    client: AsyncClient, source: dict[str, Any], sessions: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    # No ambient defaults: absence of an authoritative input is case_incompatible.
    required = {"facts", "profile", "job", "resume"}
    if not required <= source.keys():
        raise ModelGatewayError("case_incompatible")
    refs: dict[str, str] = {}

    async def post(path: str, data: dict[str, Any]) -> dict[str, Any]:
        response = await client.post("/api/v1/" + path, json=replace_refs(data, refs))
        if response.status_code != 201:
            raise ModelGatewayError("case_incompatible")
        result: dict[str, Any] = response.json()
        return result

    # Restore frozen evidence inside the isolated trial, not through retired Product APIs.
    async with sessions.begin() as session:
        for index, item in enumerate(source["facts"]):
            if item["status"] not in {"verified", "proposed"}:
                raise ModelGatewayError("case_incompatible")
            fact = await create_fact(
                session, FactCreate(statement=item["statement"], category=item["category"])
            )
            if item["status"] == "verified":
                await verify_user_fact(session, fact.id)
            refs[f"$fact:{index}"] = str(fact.id)
    response = await client.put(
        "/api/v1/profile",
        json={"expected_revision": 0, "data": replace_refs(source["profile"], refs)},
    )
    if response.status_code != 200:
        raise ModelGatewayError("case_incompatible")
    refs["$profile"] = response.json()["id"]
    job = await post("jobs", source["job"])
    refs.update(
        {
            "$job": job["id"],
            "$job_revision": job["job_revision_id"],
            "$application": job["application_id"],
        }
    )
    if source["resume"] is not None:
        resume = await post("resume-variants", source["resume"])
        refs["$resume_revision"] = resume["resume_revision_id"]
    return refs


async def actual_cas_recovery(client: AsyncClient, application_id: str) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/interviews",
        json={
            "application_id": application_id,
            "round_name": "合成技术面试",
        },
    )
    if created.status_code != 201:
        raise ModelGatewayError("case_incompatible")
    interview = created.json()
    path = "/api/v1/interviews/" + interview["id"]
    revision = interview["content_revision"]
    first = await client.patch(path, json={"expected_revision": revision, "round_name": "合成一面"})
    stale = await client.patch(path, json={"expected_revision": revision, "round_name": "过期修改"})
    current = (await client.get(path)).json()
    recovered = await client.patch(
        path,
        json={
            "expected_revision": current["content_revision"],
            "round_name": "合成二面",
        },
    )
    return {
        "status": "completed",
        "valid": first.status_code == 200
        and stale.status_code == 409
        and recovered.status_code == 200
        and recovered.json()["content_revision"] == revision + 2,
    }
