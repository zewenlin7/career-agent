from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        try:
            async with session.begin():
                yield session
        except BaseException:
            for store, ref in session.info.get("artifact_cleanup", []):
                store.remove(ref)
            raise


DB = Annotated[AsyncSession, Depends(db, scope="function")]
