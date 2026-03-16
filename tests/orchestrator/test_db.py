from __future__ import annotations

from relaymd.models import Job, Worker
from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine


def test_job_and_worker_tables_exist() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert Job.__tablename__ in table_names
    assert Worker.__tablename__ in table_names

    worker_columns = {column["name"] for column in inspector.get_columns(str(Worker.__tablename__))}
    assert "provider_state" in worker_columns
    assert "provider_state_raw" in worker_columns
    assert "provider_reason" in worker_columns
    assert "provider_last_checked_at" in worker_columns
