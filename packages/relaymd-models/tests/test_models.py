import uuid

from relaymd.models import Job, JobAssigned, NoJobAvailable, Worker
from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine


def test_sqlmodel_tables_create_without_error() -> None:
    assert Job.__tablename__
    assert Worker.__tablename__
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert Job.__tablename__ in tables
    assert Worker.__tablename__ in tables


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
