from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus, Platform, Worker, WorkerStatus
from sqlmodel import select

from relaymd.orchestrator import main as orchestrator_main
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.main import create_app
from relaymd.orchestrator.scheduler import submit_pending_slurm_jobs
from relaymd.orchestrator.slurm import SlurmSubmissionError, submit_slurm_job


@asynccontextmanager
async def app_client(settings: OrchestratorSettings):
    app = create_app(settings, start_background_tasks=False)
    with patch.object(orchestrator_main, "_ensure_tailscale_running", return_value=None):
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield app, client


def _settings_with_cluster() -> OrchestratorSettings:
    return OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab-account",
                ssh_host="test-host",
                ssh_username="test-user",
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

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            if input is not None:
                captured["script"] = input.decode("utf-8")
            return b"12345\n", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        _ = kwargs
        command_args.extend(str(arg) for arg in args)
        return FakeProcess()

    monkeypatch.setattr(
        "relaymd.orchestrator.slurm.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    cluster = ClusterConfig(
        name="gilbreth",
        partition="gpu",
        account="lab-account",
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        memory_per_gpu="60G",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
    )
    job_id = await submit_slurm_job(cluster, settings)

    assert job_id == "12345"
    assert command_args == [
        "ssh",
        "-q",
        "-o",
        "BatchMode=yes",
        "test-user@test-host",
        "sbatch",
        "--parsable",
    ]
    rendered = captured["script"]
    assert "#SBATCH --gres=gpu:a100:2" in rendered
    assert "#SBATCH --mem-per-gpu=60G" in rendered
    assert "#SBATCH --export=ALL" in rendered
    assert "#SBATCH --export=ALL,INFISICAL_BOOTSTRAP_TOKEN=client-id:client-secret" not in rendered
    assert "export INFISICAL_BOOTSTRAP_TOKEN='client-id:client-secret'" in rendered
    assert "#SBATCH --signal=TERM@300" in rendered
    assert '--env HEARTBEAT_INTERVAL_SECONDS="60"' in rendered
    assert '--env WORKER_PLATFORM="hpc"' in rendered
    assert '--env RELAYMD_CLUSTER_NAME="gilbreth"' in rendered
    assert '--env SLURM_JOB_ID="${SLURM_JOB_ID}"' in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_accepts_registry_image_uri(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            if input is not None:
                captured["script"] = input.decode("utf-8")
            return b"12345\n", b""

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
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a100",
        gpu_count=1,
        image_uri="ghcr.io/acme/relaymd-worker:latest",
        nodes=1,
        ntasks=8,
        qos="standby",
        gres="gpu:1",
        memory="120G",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
    )

    await submit_slurm_job(cluster, settings)

    rendered = captured["script"]
    assert "APPTAINER_DOCKER_USERNAME" not in rendered
    assert "APPTAINER_DOCKER_PASSWORD" not in rendered
    assert "SINGULARITY_DOCKER_USERNAME" not in rendered
    assert "SINGULARITY_DOCKER_PASSWORD" not in rendered
    # docker URI must appear in the flock/pull block, not on the exec line.
    assert "docker://ghcr.io/acme/relaymd-worker:latest" in rendered
    assert '"${_APPTAINER_IMAGE}" python -m relaymd.worker' in rendered
    assert "flock -x 200" in rendered
    assert "apptainer pull" in rendered
    assert "#SBATCH --gres=gpu:1" in rendered
    assert "#SBATCH --nodes=1" in rendered
    assert "#SBATCH --ntasks=8" in rendered
    assert "#SBATCH --qos=standby" in rendered
    assert "#SBATCH --mem=120G" in rendered
    assert "--mem-per-gpu" not in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_times_out_and_kills_process(monkeypatch) -> None:
    kill_called = {"value": False}

    class FakeProcess:
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
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
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        sbatch_submit_timeout_seconds=0.01,
    )

    with pytest.raises(SlurmSubmissionError, match="timed out") as exc_info:
        await submit_slurm_job(cluster, settings)

    assert exc_info.value.stage == "timeout"
    assert exc_info.value.cluster_name == "gilbreth"
    assert exc_info.value.submission_target == "test-user@test-host:22"

    assert kill_called["value"] is True


@pytest.mark.asyncio
async def test_submit_slurm_job_nonzero_exit_exposes_submission_context(monkeypatch) -> None:
    class FakeProcess:
        returncode = 1

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            _ = input
            return b"", b"sbatch: error: QOSMinGRES"

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
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        qos="standby",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
    )

    with pytest.raises(SlurmSubmissionError) as exc_info:
        await submit_slurm_job(cluster, settings)

    exc = exc_info.value
    assert exc.stage == "nonzero_exit"
    assert exc.cluster_name == "gilbreth"
    assert exc.partition == "gpu"
    assert exc.account == "lab-account"
    assert exc.qos == "standby"
    assert exc.submission_target == "test-user@test-host:22"
    assert exc.return_code == 1
    assert exc.stderr == "sbatch: error: QOSMinGRES"


@pytest.mark.asyncio
async def test_submit_slurm_job_writes_script_to_orchestrator_log_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            _ = input
            return b"12345\n", b""

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
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        log_directory=str(tmp_path),
    )

    await submit_slurm_job(cluster, settings)

    scripts = sorted((tmp_path / "slurm").glob("*.sbatch"))
    assert len(scripts) == 1
    content = scripts[0].read_text(encoding="utf-8")
    assert "#SBATCH --partition=gpu" in content
    assert "#SBATCH --account=lab-account" in content


@pytest.mark.asyncio
async def test_submit_slurm_job_shell_escapes_infisical_token(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            if input is not None:
                captured["script"] = input.decode("utf-8")
            return b"12345\n", b""

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
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a100",
        gpu_count=2,
        sif_path="/shared/relaymd.sif",
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="tok$HOME`date`'abc\\def",
    )

    await submit_slurm_job(cluster, settings)

    rendered = captured["script"]
    assert "export INFISICAL_BOOTSTRAP_TOKEN='tok$HOME`date`'\"'\"'abc\\def'" in rendered


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
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:12345",
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
    assert worker.provider_id == "gilbreth:44444"
    assert worker.status == WorkerStatus.queued
    assert worker.last_heartbeat >= datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5)


@pytest.mark.asyncio
async def test_reap_dead_slurm_placeholders_removes_dead_jobs(monkeypatch) -> None:
    """Placeholder workers whose SLURM jobs are no longer in squeue must be deleted."""
    from relaymd.orchestrator.scheduler import reap_dead_slurm_placeholders

    settings = _settings_with_cluster()

    command_args: list[str] = []

    async def fake_squeue_dead(*args, **kwargs):
        """squeue returns empty — both jobs are gone."""
        command_args.extend(str(arg) for arg in args)

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return b"", b""

        return FakeProc()

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.create_subprocess_exec",
        fake_squeue_dead,
    )

    async with app_client(settings):
        async with get_sessionmaker()() as session:
            session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model="a100",
                    gpu_count=2,
                    vram_gb=0,
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:11111",
                    last_heartbeat=datetime(1970, 1, 1),
                    registered_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model="a100",
                    gpu_count=2,
                    vram_gb=0,
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:22222",
                    last_heartbeat=datetime(1970, 1, 1),
                    registered_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

        reaped = await reap_dead_slurm_placeholders(settings)
        assert reaped == 2

        async with get_sessionmaker()() as session:
            remaining = (await session.exec(select(Worker))).all()

    assert remaining == []
    assert command_args == [
        "ssh",
        "-q",
        "-o",
        "BatchMode=yes",
        "test-user@test-host",
        "squeue",
        "--jobs",
        "11111,22222",
        "--noheader",
        "--format=%i",
    ]


@pytest.mark.asyncio
async def test_reap_dead_slurm_placeholders_keeps_live_jobs(monkeypatch) -> None:
    """Placeholder workers whose SLURM jobs are still in squeue must be preserved."""
    from relaymd.orchestrator.scheduler import reap_dead_slurm_placeholders

    settings = _settings_with_cluster()

    command_args: list[str] = []

    async def fake_squeue_live(*args, **kwargs):
        """squeue reports job 33333 as still running."""
        command_args.extend(str(arg) for arg in args)

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return b"33333\n", b""

        return FakeProc()

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.create_subprocess_exec",
        fake_squeue_live,
    )

    async with app_client(settings):
        async with get_sessionmaker()() as session:
            session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model="a100",
                    gpu_count=2,
                    vram_gb=0,
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:33333",
                    last_heartbeat=datetime(1970, 1, 1),
                    registered_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

        reaped = await reap_dead_slurm_placeholders(settings)
        assert reaped == 0

        async with get_sessionmaker()() as session:
            remaining = (await session.exec(select(Worker))).all()

    assert len(remaining) == 1
    assert remaining[0].provider_id == "gilbreth:33333"
    assert command_args == [
        "ssh",
        "-q",
        "-o",
        "BatchMode=yes",
        "test-user@test-host",
        "squeue",
        "--jobs",
        "33333",
        "--noheader",
        "--format=%i",
    ]


@pytest.mark.asyncio
async def test_submit_pending_jobs_logs_slurm_error_and_continues_other_clusters(
    monkeypatch,
) -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab-account",
                ssh_host="gilbreth-host",
                ssh_username="test-user",
                gpu_type="a100",
                gpu_count=1,
                sif_path="/shared/relaymd.sif",
                max_pending_jobs=3,
            ),
            ClusterConfig(
                name="anvil",
                partition="gpu",
                account="lab-account",
                ssh_host="anvil-host",
                ssh_username="test-user",
                gpu_type="a100",
                gpu_count=1,
                sif_path="/shared/relaymd.sif",
                max_pending_jobs=3,
            ),
        ],
    )

    async def fake_submit(cluster: ClusterConfig, _settings: OrchestratorSettings) -> str:
        if cluster.name == "gilbreth":
            raise SlurmSubmissionError(
                "sbatch submission failed: rc=1, stderr=sbatch: error: QOSMinGRES",
                stage="nonzero_exit",
                cluster_name=cluster.name,
                partition="gpu",
                account=cluster.account,
                qos=cluster.qos,
                gres=cluster.slurm_gres,
                nodes=1,
                ntasks=1,
                wall_time=cluster.wall_time,
                memory=cluster.memory,
                memory_per_gpu=cluster.memory_per_gpu,
                ssh_host=cluster.ssh_host,
                ssh_username=cluster.ssh_username,
                ssh_port=cluster.ssh_port,
                ssh_key_file=cluster.ssh_key_file,
                command=["ssh", "test-user@gilbreth-host", "sbatch", "--parsable"],
                timeout_seconds=60.0,
                return_code=1,
                stdout="",
                stderr="sbatch: error: QOSMinGRES",
                local_script_path="/tmp/relaymd-logs/slurm/gilbreth.sbatch",
            )
        return "77777"

    monkeypatch.setattr("relaymd.orchestrator.scheduler.submit_slurm_job", fake_submit)

    error_log = patch("relaymd.orchestrator.services.slurm_provisioning_service.logger.error")
    with error_log as error_mock:
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

            async with get_sessionmaker()() as session:
                workers = (await session.exec(select(Worker))).all()

    assert submitted_count == 1
    assert len(workers) == 1
    assert workers[0].provider_id == "anvil:77777"
    error_mock.assert_called_once()
    _, kwargs = error_mock.call_args
    assert kwargs["cluster_name"] == "gilbreth"
    assert kwargs["submission_target"] == "test-user@gilbreth-host:22"
    assert kwargs["stderr"] == "sbatch: error: QOSMinGRES"
    assert kwargs["stage"] == "nonzero_exit"
