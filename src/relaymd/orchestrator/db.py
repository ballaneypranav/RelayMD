from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import ClusterProvisioningState, Job, JobEvent, Worker

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _connect_args_for_url(database_url: str) -> dict[str, bool]:
    if "file::memory:" in database_url or "mode=memory" in database_url:
        return {"uri": True}
    return {}


def init_engine(database_url: str) -> None:
    global _engine, _sessionmaker

    engine_kwargs: dict[str, object] = {
        "connect_args": _connect_args_for_url(database_url),
        "echo": False,
    }
    if ":memory:" in database_url:
        engine_kwargs["poolclass"] = StaticPool

    _engine = create_async_engine(database_url, **engine_kwargs)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

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
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with engine.begin() as connection:
        await connection.run_sync(_ensure_job_lifecycle_columns)
    async with engine.begin() as connection:
        await connection.run_sync(_ensure_job_event_indexes)


def _ensure_job_lifecycle_columns(connection: Connection) -> None:
    if connection.dialect.name == "sqlite":
        table_exists = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'job'"
        ).first()
        if table_exists is None:
            return
        existing_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(job)").all()
        }
    else:
        inspector = inspect(connection)
        if "job" not in inspector.get_table_names():
            return
        existing_columns = {column["name"] for column in inspector.get_columns("job")}

    missing_columns = {
        "assigned_at": "DATETIME",
        "started_at": "DATETIME",
        "status_changed_at": "DATETIME",
        "progress": "FLOAT",
        "progress_codes_json": "TEXT",
        "checkpoint_cycle_status": "TEXT",
        "checkpoint_cycle_failures_json": "TEXT",
    }.items()
    for column_name, column_type in missing_columns:
        if column_name not in existing_columns:
            connection.execute(text(f"ALTER TABLE job ADD COLUMN {column_name} {column_type}"))

    connection.execute(
        text("UPDATE job SET status_changed_at = updated_at WHERE status_changed_at IS NULL")
    )
    connection.execute(
        text(
            "UPDATE job SET assigned_at = updated_at "
            "WHERE assigned_at IS NULL AND status IN ('assigned', 'running')"
        )
    )


def _ensure_job_event_indexes(connection: Connection) -> None:
    if connection.dialect.name == "sqlite":
        table_exists = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'jobevent'"
        ).first()
        if table_exists is None:
            return
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_jobevent_job_id ON jobevent (job_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_jobevent_occurred_at ON jobevent (occurred_at)"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_jobevent_job_seq ON jobevent (job_id, event_seq)"
        )
        return

    inspector = inspect(connection)
    if "jobevent" not in inspector.get_table_names():
        return
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobevent_job_id ON jobevent (job_id)"))
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_jobevent_occurred_at ON jobevent (occurred_at)")
    )
    connection.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_jobevent_job_seq ON jobevent (job_id, event_seq)")
    )


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
