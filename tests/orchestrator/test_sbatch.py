from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus, Platform, Worker
from sqlmodel import select

from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.main import create_app
from relaymd.orchestrator.scheduler import submit_pending_slurm_jobs
from relaymd.orchestrator.slurm import submit_slurm_job


@asynccontextmanager
async def app_client(settings: OrchestratorSettings):
    app = create_app(settings, start_background_tasks=False)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


def _settings_with_cluster() -> OrchestratorSettings:
    return OrchestratorSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab-account",
                gpu_type="a100",
                gpu_count=2,
                sif_path="/shared/relaymd.sif",
                max_pending_jobs=1,
                wall_time="3:30:00",
            )
        ],
    )


@pytest.mark.asyncio
async def test_submit_slurm_job_renders_expected_script(monkeypatch, tmp_path: Path) -> None:
    _ = tmp_path
    captured: dict[str, str] = {}
    command_args: list[str] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"12345\n", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        _ = kwargs
        command_args.extend(str(arg) for arg in args[:2])
        script_path = str(args[2])
        captured["script"] = Path(script_path).read_text(encoding="utf-8")
        return FakeProcess()

    monkeypatch.setattr(
        "relaymd.orchestrator.slurm.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    cluster = ClusterConfig(
        name="gilbreth",
        partition="gpu",
        account="lab-account",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
    )
    job_id = await submit_slurm_job(cluster, settings)

    assert job_id == "12345"
    assert command_args == ["sbatch", "--parsable"]
    rendered = captured["script"]
    assert "#SBATCH --gres=gpu:a100:2" in rendered
    assert "#SBATCH --export=ALL" in rendered
    assert "#SBATCH --export=ALL,INFISICAL_BOOTSTRAP_TOKEN=client-id:client-secret" not in rendered
    assert 'export INFISICAL_BOOTSTRAP_TOKEN="client-id:client-secret"' in rendered
    assert "#SBATCH --signal=TERM@300" in rendered
    assert '--env HEARTBEAT_INTERVAL_SECONDS="60"' in rendered
    assert '--env WORKER_PLATFORM="hpc"' in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_times_out_and_kills_process(monkeypatch) -> None:
    kill_called = {"value": False}

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(3600)
            return b"", b""

        def kill(self) -> None:
            kill_called["value"] = True

    async def fake_create_subprocess_exec(*args, **kwargs):
        _ = (args, kwargs)
        return FakeProcess()

    monkeypatch.setattr(
        "relaymd.orchestrator.slurm.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    cluster = ClusterConfig(
        name="gilbreth",
        partition="gpu",
        account="lab-account",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        sbatch_submit_timeout_seconds=0.01,
    )

    with pytest.raises(RuntimeError, match="timed out"):
        await submit_slurm_job(cluster, settings)

    assert kill_called["value"] is True


@pytest.mark.asyncio
async def test_submit_pending_jobs_skips_when_pending_placeholder_exists(monkeypatch) -> None:
    settings = _settings_with_cluster()
    submit_calls: list[str] = []

    async def fake_submit(*args, **kwargs) -> str:
        _ = (args, kwargs)
        submit_calls.append("called")
        return "99999"

    monkeypatch.setattr("relaymd.orchestrator.scheduler.submit_slurm_job", fake_submit)

    async with app_client(settings):
        async with get_sessionmaker()() as session:
            session.add(
                Job(
                    title="queued-job",
                    input_bundle_path="jobs/1/input/bundle.tar.gz",
                    status=JobStatus.queued,
                )
            )
            session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model="a100",
                    gpu_count=2,
                    vram_gb=0,
                    slurm_job_id="gilbreth:12345",
                    last_heartbeat=datetime(1970, 1, 1),
                    registered_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

        submitted_count = await submit_pending_slurm_jobs(settings)

    assert submitted_count == 0
    assert submit_calls == []


@pytest.mark.asyncio
async def test_submit_pending_jobs_records_recent_placeholder_heartbeat(monkeypatch) -> None:
    settings = _settings_with_cluster()

    async def fake_submit(*args, **kwargs) -> str:
        _ = (args, kwargs)
        return "44444"

    monkeypatch.setattr("relaymd.orchestrator.scheduler.submit_slurm_job", fake_submit)

    async with app_client(settings):
        async with get_sessionmaker()() as session:
            session.add(
                Job(
                    title="queued-job",
                    input_bundle_path="jobs/1/input/bundle.tar.gz",
                    status=JobStatus.queued,
                )
            )
            await session.commit()

        submitted_count = await submit_pending_slurm_jobs(settings)
        assert submitted_count == 1

        async with get_sessionmaker()() as session:
            workers = (await session.exec(select(Worker))).all()

    assert len(workers) == 1
    worker = workers[0]
    assert worker.slurm_job_id == "gilbreth:44444"
    assert worker.last_heartbeat >= datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5)
