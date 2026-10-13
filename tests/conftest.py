import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_agent.api.app import create_app
from career_agent.config import Settings
from career_agent.infrastructure.db import Base


@pytest.fixture
def synthetic():
    return json.loads((Path(__file__).parent / "fixtures" / "synthetic.json").read_text())


@pytest.fixture(scope="session")
def migrated_url():
    """Create only a random test DB; never truncate/drop the configured database."""
    server = make_url(
        os.getenv(
            "CAREER_AGENT_TEST_DATABASE_URL",
            "postgresql+asyncpg://career:career_local_only@127.0.0.1:55432/postgres",
        )
    )
    if server.drivername != "postgresql+asyncpg":
        pytest.fail("Integration tests require PostgreSQL+asyncpg, never SQLite")
    name = "career_test_" + uuid4().hex
    url = server.set(database=name).render_as_string(hide_password=False)

    async def admin(sql):
        engine = create_async_engine(server, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await conn.execute(text(sql))
        finally:
            await engine.dispose()

    asyncio.run(admin(f'CREATE DATABASE "{name}"'))
    try:
        cfg = Config("alembic.ini")
        cfg.attributes["database_url"] = url
        command.upgrade(cfg, "head")
        yield url
    finally:
        asyncio.run(admin(f'DROP DATABASE "{name}" WITH (FORCE)'))


@pytest.fixture
async def sessions(migrated_url):
    engine = create_async_engine(migrated_url, poolclass=NullPool, hide_parameters=True)
    # This URL is created by the fixture above, never the user's application DB.
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(migrated_url, sessions, tmp_path):
    app = create_app(
        Settings(database_url=SecretStr(migrated_url), data_dir=tmp_path, live_enabled=False)
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.fixture(autouse=True)
def offline_network_boundary(monkeypatch):
    """Tests may reach temporary local PostgreSQL, never a live external provider."""
    import socket

    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    original_dns = socket.getaddrinfo

    def check(address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("external_network_disabled_in_tests")

    def connect(sock, address):
        check(address)
        return original(sock, address)

    def connect_ex(sock, address):
        check(address)
        return original_ex(sock, address)

    def dns(host, *args, **kwargs):
        if host not in {None, "127.0.0.1", "::1", "localhost", b"localhost"}:
            raise AssertionError("external_network_disabled_in_tests")
        return original_dns(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", dns)
