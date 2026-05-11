from __future__ import annotations

from datetime import datetime

from relaymd.models import ClusterProvisioningState, Job, Worker
from sqlalchemy import Column, DateTime, MetaData, String, Table, inspect, text
from sqlmodel import SQLModel, create_engine

from relaymd.orchestrator.db import _ensure_job_lifecycle_columns


def test_job_and_worker_tables_exist() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert Job.__tablename__ in table_names
    assert Worker.__tablename__ in table_names
    assert ClusterProvisioningState.__tablename__ in table_names

    worker_columns = {column["name"] for column in inspector.get_columns(str(Worker.__tablename__))}
    assert "provider_state" in worker_columns
    assert "provider_state_raw" in worker_columns
    assert "provider_reason" in worker_columns
    assert "provider_last_checked_at" in worker_columns

    job_columns = {column["name"] for column in inspector.get_columns(str(Job.__tablename__))}
    assert "assigned_at" in job_columns
    assert "started_at" in job_columns
    assert "status_changed_at" in job_columns


def test_job_lifecycle_column_backfill_for_existing_schema() -> None:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "job",
        metadata,
        Column("id", String, primary_key=True),
        Column("title", String, nullable=False),
        Column("status", String, nullable=False),
        Column("input_bundle_path", String, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )
    metadata.create_all(engine)

    updated_at = datetime(2026, 1, 1, 12, 0, 0)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO job (id, title, status, input_bundle_path, updated_at) "
                "VALUES (:id, :title, :status, :input_bundle_path, :updated_at)"
            ),
            {
                "id": "job-1",
                "title": "job",
                "status": "running",
                "input_bundle_path": "jobs/1/input/bundle.tar.gz",
                "updated_at": updated_at,
            },
        )
        _ensure_job_lifecycle_columns(connection)

        row = connection.execute(
            text("SELECT assigned_at, started_at, status_changed_at FROM job WHERE id = :id"),
            {"id": "job-1"},
        ).one()

    assert str(row.assigned_at).startswith("2026-01-01 12:00:00")
    assert row.started_at is None
    assert str(row.status_changed_at).startswith("2026-01-01 12:00:00")
