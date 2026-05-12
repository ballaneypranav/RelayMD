from __future__ import annotations

from pathlib import Path

from relaymd.models import ClusterProvisioningState, Job, JobEvent, Worker
from sqlalchemy import create_engine, inspect

from relaymd.orchestrator.db import _run_migrations


def _migrated_inspector(db_path: Path):
    url = f"sqlite:///{db_path}"
    _run_migrations(url)
    engine = create_engine(url)
    return inspect(engine)


def test_migrations_create_all_expected_tables(tmp_path: Path) -> None:
    inspector = _migrated_inspector(tmp_path / "test.db")
    table_names = set(inspector.get_table_names())
    assert Job.__tablename__ in table_names
    assert Worker.__tablename__ in table_names
    assert ClusterProvisioningState.__tablename__ in table_names
    assert JobEvent.__tablename__ in table_names


def test_migrations_job_columns(tmp_path: Path) -> None:
    inspector = _migrated_inspector(tmp_path / "test.db")
    job_columns = {col["name"] for col in inspector.get_columns(str(Job.__tablename__))}
    for col in (
        "assigned_at",
        "started_at",
        "status_changed_at",
        "preferred_clusters_json",
        "comment",
        "queue_blocked_reason",
    ):
        assert col in job_columns, f"missing column: {col}"


def test_migrations_jobevent_indexes(tmp_path: Path) -> None:
    inspector = _migrated_inspector(tmp_path / "test.db")
    index_names = {idx["name"] for idx in inspector.get_indexes(str(JobEvent.__tablename__))}
    assert "ix_jobevent_job_id" in index_names
    assert "ix_jobevent_job_seq" in index_names


def test_migrations_idempotent(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    _run_migrations(url)
    _run_migrations(url)  # second run should be a no-op without errors
