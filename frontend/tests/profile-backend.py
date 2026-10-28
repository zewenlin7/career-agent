"""Real isolated PostgreSQL/FastAPI backend for the Profile browser suite. Never production DB."""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import Response
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from career_agent.api.app import create_app
from career_agent.config import Settings
from career_agent.infrastructure.db import Base

name = "career_browser_" + uuid4().hex
admin_url = "postgresql+asyncpg://career:career_local_only@127.0.0.1:55432/postgres"
url = admin_url.rsplit("/", 1)[0] + "/" + name


async def admin(sql):
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(sql))
    finally:
        await engine.dispose()


asyncio.run(admin(f'CREATE DATABASE "{name}"'))
try:
    config = Config("../alembic.ini")
    config.set_main_option("script_location", "../migrations")
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    with tempfile.TemporaryDirectory(prefix="career-profile-browser-") as directory:
        app = create_app(
            Settings(
                database_url=SecretStr(url),
                data_dir=Path(directory),
                font_dir=Path("/private/tmp/career-agent-cjk-fonts"),
                live_enabled=False,
                ops_token=SecretStr("synthetic-profile-browser-token"),
            )
        )

        # Real API/DB/Gateway paths with an explicitly offline test-only model adapter.
        from career_agent.models.gateway import ModelGateway
        from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry

        class BrowserFixture(FixtureTaskProvider):
            async def generate(self, candidate, context, task):
                await asyncio.sleep(0.5)
                return await super().generate(candidate, context, task)

        @asynccontextmanager
        async def fixture_dependencies(settings, mode):
            yield (
                ModelGateway(registry(settings, False), POLICY, {"fixture": BrowserFixture()}),
                None,
            )

        app.state.preparation_dependencies = fixture_dependencies

        @app.post("/__reset")
        async def reset():
            async with app.state.sessions.begin() as session:
                for table in reversed(Base.metadata.sorted_tables):
                    if table.name == "control_events":
                        await session.execute(text("TRUNCATE control_events"))
                    else:
                        await session.execute(table.delete())
            return Response(status_code=204)

        uvicorn.run(app, host="127.0.0.1", port=3131, access_log=False, log_level="error")
finally:
    asyncio.run(admin(f'DROP DATABASE "{name}" WITH (FORCE)'))
