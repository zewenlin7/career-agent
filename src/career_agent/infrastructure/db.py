from collections.abc import AsyncIterator
from types import GenericAlias
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from career_agent.config import Settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class ValidatedJSON(TypeDecorator[Any]):
    """Validate structured JSONB on both write and read, including direct ORM use."""

    impl = JSONB
    cache_ok = True

    def __init__(self, schema: type[BaseModel]) -> None:
        super().__init__()
        self.schema = schema

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return self.schema.model_validate(value).model_dump(mode="json")

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return self.schema.model_validate(value).model_dump(mode="json")


def make_engine(settings: Settings) -> Any:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
    )


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session, session.begin():
        yield session


class ValidatedList(TypeDecorator[Any]):
    """Typed JSONB lists for notes, opaque references and metadata codes."""

    impl = JSONB
    cache_ok = True

    def __init__(self, item_schema: Any) -> None:
        super().__init__()
        self.item_schema = item_schema

    def _validate(self, value: Any) -> Any:
        from pydantic import TypeAdapter

        adapter = TypeAdapter[Any](cast(Any, GenericAlias(list, self.item_schema)))
        return adapter.dump_python(adapter.validate_python(value), mode="json")

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return self._validate(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return self._validate(value)
