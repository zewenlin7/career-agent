import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from career_agent.config import Settings
from career_agent.infrastructure import entities  # noqa: F401
from career_agent.infrastructure.db import Base, ValidatedJSON, ValidatedList

config = context.config
url = config.attributes.get("database_url") or Settings().database_url.get_secret_value()


def render_item(kind, obj, autogen_context):
    if kind == "type" and isinstance(obj, (ValidatedJSON, ValidatedList)):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "postgresql.JSONB()"
    return False


def configure(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def migrate():
    engine = create_async_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    async with engine.connect() as connection:
        await connection.run_sync(configure)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(migrate())
