from __future__ import annotations

from relaymd.models import Job, Worker
from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine


def test_job_and_worker_tables_exist() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert Job.__tablename__ in table_names
    assert Worker.__tablename__ in table_names
