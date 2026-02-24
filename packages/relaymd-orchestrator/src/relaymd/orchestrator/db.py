from __future__ import annotations

from collections.abc import AsyncGenerator

from relaymd.models import Job, Worker
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _connect_args_for_url(database_url: str) -> dict[str, bool]:
    if "file::memory:" in database_url or "mode=memory" in database_url:
        return {"uri": True}
    return {}


def init_engine(database_url: str) -> None:
    global _engine, _sessionmaker

    _engine = create_async_engine(
        database_url,
        connect_args=_connect_args_for_url(database_url),
        echo=False,
    )
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Ensure SQLModel metadata includes all mapped tables used by the orchestrator.
    _ = (Job, Worker)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine has not been initialized")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database sessionmaker has not been initialized")
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def create_db_and_tables() -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
