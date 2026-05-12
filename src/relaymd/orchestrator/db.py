from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import ClusterProvisioningState, Job, JobEvent, Worker

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_database_url: str | None = None

_ALEMBIC_DIR = Path(__file__).parent.parent / "alembic"


def _connect_args_for_url(database_url: str) -> dict[str, bool]:
    if "file::memory:" in database_url or "mode=memory" in database_url:
        return {"uri": True}
    return {}


def init_engine(database_url: str) -> None:
    global _engine, _sessionmaker, _database_url

    engine_kwargs: dict[str, object] = {
        "connect_args": _connect_args_for_url(database_url),
        "echo": False,
    }
    if ":memory:" in database_url:
        engine_kwargs["poolclass"] = StaticPool

    _engine = create_async_engine(database_url, **engine_kwargs)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    _database_url = database_url

    # Ensure SQLModel metadata includes all mapped tables used by the orchestrator.
    _ = (Job, JobEvent, Worker, ClusterProvisioningState)


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
    if _database_url is None:
        raise RuntimeError("Database engine has not been initialized")
    if ":memory:" in _database_url:
        # Alembic can't migrate in-memory SQLite (each connection is a separate DB).
        engine = get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
    else:
        _run_migrations(_database_url)


def _run_migrations(database_url: str) -> None:
    sync_url = database_url.replace("+aiosqlite", "")
    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


async def dispose_engine() -> None:
    global _engine, _sessionmaker, _database_url
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
    _database_url = None
