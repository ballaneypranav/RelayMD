import uuid

from relaymd.models import Job, JobAssigned, JobEvent, NoJobAvailable, Worker
from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine


def test_sqlmodel_tables_create_without_error() -> None:
    job_table_name = str(Job.__tablename__)
    job_event_table_name = str(JobEvent.__tablename__)
    worker_table_name = str(Worker.__tablename__)
    assert job_table_name
    assert job_event_table_name
    assert worker_table_name
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert job_table_name in tables
    assert job_event_table_name in tables
    assert worker_table_name in tables
    job_event_fks = inspector.get_foreign_keys(job_event_table_name)
    assert any(
        fk.get("referred_table") == job_table_name
        and fk.get("constrained_columns") == ["job_id"]
        for fk in job_event_fks
    )


def test_job_request_response_json_shapes() -> None:
    job_id = uuid.uuid4()
    assigned = JobAssigned(
        job_id=job_id,
        input_bundle_path="jobs/123/input/bundle.tar.gz",
        latest_checkpoint_path=None,
    )
    no_job = NoJobAvailable()

    assert assigned.model_dump(mode="json") == {
        "status": "assigned",
        "job_id": str(job_id),
        "input_bundle_path": "jobs/123/input/bundle.tar.gz",
        "latest_checkpoint_path": None,
    }
    assert no_job.model_dump(mode="json") == {"status": "no_job_available"}
