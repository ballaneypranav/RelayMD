from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import ANY, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus, Platform, Worker, WorkerStatus
from sqlmodel import select

from relaymd.orchestrator import main as orchestrator_main
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.main import create_app
from relaymd.orchestrator.scheduler import submit_pending_slurm_jobs
from relaymd.orchestrator.services.slurm_provisioning_service import (
    _normalize_slurm_state,
    _parse_squeue_output,
)
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
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
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
    )
    worker_id = UUID("12345678-1234-5678-1234-567812345678")
    job_id = await submit_slurm_job(cluster, settings, worker_id=worker_id)

    assert job_id == "12345"
    assert command_args == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
        "test-user@test-host",
        "sbatch",
        "--parsable",
    ]
    rendered = captured["script"]
    assert "#SBATCH --job-name=w-12345678" in rendered
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
    )

    await submit_slurm_job(cluster, settings)

    rendered = captured["script"]
    assert "APPTAINER_DOCKER_USERNAME" not in rendered
    assert "APPTAINER_DOCKER_PASSWORD" not in rendered
    assert "SINGULARITY_DOCKER_USERNAME" not in rendered
    assert "SINGULARITY_DOCKER_PASSWORD" not in rendered
    # docker URI must appear in the flock/pull block, not on the exec line.
    assert "docker://ghcr.io/acme/relaymd-worker:latest" in rendered
    assert 'apptainer exec "${apptainer_args[@]}" "${_APPTAINER_IMAGE}" /bin/sh -lc' in rendered
    assert "'python -m relaymd.worker'" in rendered
    assert "flock -x 200" in rendered
    assert "apptainer pull" in rendered
    assert "#SBATCH --gres=gpu:1" in rendered
    assert "#SBATCH --nodes=1" in rendered
    assert "#SBATCH --ntasks=8" in rendered
    assert "#SBATCH --qos=standby" in rendered
    assert "#SBATCH --mem=120G" in rendered
    assert "--mem-per-gpu" not in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_renders_bind_mount_worker_source(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_WORKER_BIND_PATHS", "/repo:/opt/relaymd-src")
    monkeypatch.setenv(
        "RELAYMD_WORKER_PYTHONPATH",
        "/opt/relaymd-src/packages/relaymd-worker/src:/opt/relaymd-src/packages/relaymd-core/src",
    )
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
        sif_path="/shared/relaymd-worker-base.sif",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
    )

    await submit_slurm_job(cluster, settings)

    rendered = captured["script"]
    assert "--bind '/repo:/opt/relaymd-src'" in rendered
    assert (
        "--env PYTHONPATH='/opt/relaymd-src/packages/relaymd-worker/src:"
        "/opt/relaymd-src/packages/relaymd-core/src'"
    ) in rendered
    assert 'apptainer exec "${apptainer_args[@]}" "${_APPTAINER_IMAGE}" /bin/sh -lc' in rendered
    assert "'python -m relaymd.worker'" in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_shell_quotes_worker_pythonpath(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_WORKER_PYTHONPATH", "/safe/path'; touch /tmp/pwned; echo '")
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
        sif_path="/shared/relaymd-worker-base.sif",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
    )

    await submit_slurm_job(cluster, settings)

    rendered = captured["script"]
    assert "--env PYTHONPATH='/safe/path'\"'\"'; touch /tmp/pwned; echo '\"'\"''" in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_uses_registry_credentials_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("APPTAINER_DOCKER_USERNAME", "gh-user")
    monkeypatch.setenv("APPTAINER_DOCKER_PASSWORD", "  gh-token  ")
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
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
    )

    await submit_slurm_job(cluster, settings)

    rendered = captured["script"]
    assert "export APPTAINER_DOCKER_USERNAME='gh-user'" in rendered
    assert "export APPTAINER_DOCKER_PASSWORD='  gh-token  '" in rendered
    assert 'apptainer pull "${_SIF_TMP}" "${_APPTAINER_IMAGE}"' in rendered
    assert "--docker-login" not in rendered


@pytest.mark.asyncio
async def test_submit_slurm_job_redacts_secrets_in_debug_log(monkeypatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setenv("APPTAINER_DOCKER_USERNAME", "gh-user")
    monkeypatch.setenv("APPTAINER_DOCKER_PASSWORD", "gh-token")

    class FakeLogger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def debug(self, fmt: str, rendered: str) -> None:
            _ = fmt
            self.messages.append(rendered)

    fake_logger = FakeLogger()

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
    monkeypatch.setattr(
        "relaymd.orchestrator.slurm.structlog.get_logger",
        lambda _: fake_logger,
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
        wall_time="3:30:00",
    )
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
    )

    await submit_slurm_job(cluster, settings)

    assert len(fake_logger.messages) == 1
    logged_script = fake_logger.messages[0]
    assert "export INFISICAL_BOOTSTRAP_TOKEN='[REDACTED]'" in logged_script
    assert "export APPTAINER_DOCKER_PASSWORD='[REDACTED]'" in logged_script
    assert "client-id:client-secret" not in logged_script
    assert "gh-token" not in logged_script


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
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")

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
        log_directory=str(tmp_path),
    )

    await submit_slurm_job(cluster, settings)

    scripts = sorted((tmp_path / "slurm").glob("*.sbatch"))
    assert len(scripts) == 1
    content = scripts[0].read_text(encoding="utf-8")
    assert "#SBATCH --partition=gpu" in content
    assert "#SBATCH --account=lab-account" in content
    assert "client-id:client-secret" not in content
    assert "export INFISICAL_BOOTSTRAP_TOKEN='[REDACTED]'" in content


@pytest.mark.asyncio
async def test_submit_slurm_job_shell_escapes_infisical_token(monkeypatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "tok$HOME`date`'abc\\def")
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
    submitted_worker_ids: list[UUID] = []

    async def fake_submit(*args, **kwargs) -> str:
        _ = args
        submitted_worker_ids.append(kwargs["worker_id"])
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
    assert submitted_worker_ids == [worker.id]
    assert worker.provider_id == "gilbreth:44444"
    assert worker.status == WorkerStatus.queued
    assert worker.provider_state == "submitted"
    assert worker.last_heartbeat >= datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5)


@pytest.mark.asyncio
async def test_submit_pending_jobs_logs_provisioning_skip_without_queued_jobs() -> None:
    settings = _settings_with_cluster()

    with patch("relaymd.orchestrator.services.slurm_provisioning_service.logger.info") as info_mock:
        async with app_client(settings):
            submitted_count = await submit_pending_slurm_jobs(settings)

    assert submitted_count == 0
    info_mock.assert_any_call("provisioning_skipped_no_queued_jobs", cluster_name="gilbreth")


@pytest.mark.asyncio
async def test_submit_pending_jobs_logs_slurm_submission_success(monkeypatch) -> None:
    settings = _settings_with_cluster()

    async def fake_submit(*args, **kwargs) -> str:
        _ = (args, kwargs)
        return "44444"

    monkeypatch.setattr("relaymd.orchestrator.scheduler.submit_slurm_job", fake_submit)

    info_log = patch("relaymd.orchestrator.services.slurm_provisioning_service.logger.info")
    with info_log as info_mock:
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
                worker = (await session.exec(select(Worker))).one()

    assert submitted_count == 1
    assert worker.provider_id == "gilbreth:44444"
    info_mock.assert_any_call(
        "provisioning_evaluated",
        cluster_name="gilbreth",
        job_id=ANY,
        strategy="reactive",
    )
    info_mock.assert_any_call(
        "slurm_submission_started",
        cluster_name="gilbreth",
        job_id=ANY,
    )
    info_mock.assert_any_call(
        "placeholder_worker_created",
        cluster_name="gilbreth",
        job_id=ANY,
        provider_id=worker.provider_id,
        worker_id=str(worker.id),
    )
    info_mock.assert_any_call(
        "slurm_cluster_submission_succeeded",
        slurm_job_id="44444",
        provider_id=worker.provider_id,
        worker_id=str(worker.id),
        cluster_name="gilbreth",
        partition="gpu",
        account="lab-account",
        qos=None,
        gres="gpu:a100:2",
        nodes=None,
        ntasks=None,
        wall_time="3:30:00",
        memory=None,
        memory_per_gpu=None,
        ssh_host="test-host",
        ssh_username="test-user",
        ssh_port=22,
        ssh_key_file=None,
        submission_target="test-user@test-host:22",
    )


def test_parse_squeue_output_and_state_mapping() -> None:
    statuses = _parse_squeue_output(
        "11111|PENDING|Priority\n22222|RUNNING|None\n33333|COMPLETING|\n"
    )

    assert statuses["11111"].provider_state == "pending"
    assert statuses["11111"].provider_state_raw == "PENDING"
    assert statuses["11111"].provider_reason == "Priority"

    assert statuses["22222"].provider_state == "running"
    assert statuses["22222"].provider_state_raw == "RUNNING"
    assert statuses["22222"].provider_reason is None

    assert statuses["33333"].provider_state == "completing"
    assert statuses["33333"].provider_state_raw == "COMPLETING"
    assert statuses["33333"].provider_reason is None


@pytest.mark.parametrize(
    ("raw_state", "expected"),
    [
        ("PD", "pending"),
        ("CONFIGURING", "pending"),
        ("R", "running"),
        ("CG", "completing"),
        ("SUSPENDED", "unknown"),
    ],
)
def test_normalize_slurm_state(raw_state: str, expected: str) -> None:
    assert _normalize_slurm_state(raw_state) == expected


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
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
        "test-user@test-host",
        "squeue",
        "--jobs",
        "11111,22222",
        "--noheader",
        "--format=%i\\|%T\\|%r",
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
                return b"33333|RUNNING|None\n", b""

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
    kept = remaining[0]
    assert kept.provider_id == "gilbreth:33333"
    assert kept.provider_state == "running"
    assert kept.provider_state_raw == "RUNNING"
    assert kept.provider_reason is None
    assert kept.provider_last_checked_at is not None
    assert command_args == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
        "test-user@test-host",
        "squeue",
        "--jobs",
        "33333",
        "--noheader",
        "--format=%i\\|%T\\|%r",
    ]


@pytest.mark.asyncio
async def test_reap_dead_slurm_placeholders_recovers_from_mixed_invalid_job_ids(
    monkeypatch,
) -> None:
    from relaymd.orchestrator.scheduler import reap_dead_slurm_placeholders

    settings = _settings_with_cluster()

    async def fake_squeue_mixed(*args, **kwargs):
        _ = kwargs
        jobs = str(args[args.index("--jobs") + 1])

        class FakeProc:
            def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
                self.returncode = returncode
                self._stdout = stdout
                self._stderr = stderr

            async def communicate(self):
                return self._stdout, self._stderr

        if jobs == "11111,22222":
            return FakeProc(
                1,
                b"",
                b"slurm_load_jobs error: Invalid job id specified",
            )
        if jobs == "11111":
            return FakeProc(0, b"11111|RUNNING|None\n", b"")
        if jobs == "22222":
            return FakeProc(
                1,
                b"",
                b"slurm_load_jobs error: Invalid job id specified",
            )

        raise AssertionError(f"unexpected squeue --jobs payload: {jobs}")

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.create_subprocess_exec",
        fake_squeue_mixed,
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
        assert reaped == 1

        async with get_sessionmaker()() as session:
            remaining = (await session.exec(select(Worker))).all()

    assert len(remaining) == 1
    assert remaining[0].provider_id == "gilbreth:11111"
    assert remaining[0].provider_state == "running"
    assert remaining[0].provider_state_raw == "RUNNING"


@pytest.mark.asyncio
async def test_reap_dead_slurm_placeholders_skips_reap_after_generic_squeue_nonzero_exit(
    monkeypatch,
) -> None:
    from relaymd.orchestrator.scheduler import reap_dead_slurm_placeholders

    settings = _settings_with_cluster()
    warning_log = patch("relaymd.orchestrator.services.slurm_provisioning_service.logger.warning")

    async def fake_squeue_nonzero(*args, **kwargs):
        _ = (args, kwargs)

        class FakeProc:
            returncode = 1

            async def communicate(self):
                return b"", b"squeue: error: slurm controller temporarily unavailable"

        return FakeProc()

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.create_subprocess_exec",
        fake_squeue_nonzero,
    )

    with warning_log as warning_mock:
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

    warning_mock.assert_any_call(
        "slurm_squeue_query_nonzero_exit",
        cluster_name="gilbreth",
        attempt=1,
        max_attempts=2,
        return_code=1,
        stderr="squeue: error: slurm controller temporarily unavailable",
        slurm_job_ids=["33333"],
        submission_target="test-user@test-host:22",
    )
    warning_mock.assert_any_call(
        "slurm_placeholder_reap_skipped_due_to_status_query_failure",
        cluster_name="gilbreth",
        placeholder_count=1,
    )
    assert len(remaining) == 1
    assert remaining[0].provider_id == "gilbreth:33333"


@pytest.mark.asyncio
async def test_reap_dead_slurm_placeholders_retries_after_squeue_timeout(monkeypatch) -> None:
    from relaymd.orchestrator.scheduler import reap_dead_slurm_placeholders

    settings = _settings_with_cluster()
    timeout_state = {"count": 0}
    warning_log = patch("relaymd.orchestrator.services.slurm_provisioning_service.logger.warning")

    async def fake_wait_for(awaitable, timeout):
        if timeout == 30.0 and timeout_state["count"] == 0:
            timeout_state["count"] += 1
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError
        return await awaitable

    async def fake_squeue_live(*args, **kwargs):
        _ = (args, kwargs)

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return b"33333|RUNNING|None\n", b""

            def kill(self):
                return None

        return FakeProc()

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.create_subprocess_exec",
        fake_squeue_live,
    )
    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.wait_for",
        fake_wait_for,
    )

    with warning_log as warning_mock:
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

    assert timeout_state["count"] == 1
    warning_mock.assert_any_call(
        "slurm_squeue_query_timeout",
        cluster_name="gilbreth",
        attempt=1,
        max_attempts=2,
        timeout_seconds=30.0,
        slurm_job_ids=["33333"],
        submission_target="test-user@test-host:22",
    )
    assert len(remaining) == 1
    assert remaining[0].provider_id == "gilbreth:33333"
    assert remaining[0].provider_state == "running"


@pytest.mark.asyncio
async def test_reap_dead_slurm_placeholders_skips_reap_after_squeue_timeout_retries(
    monkeypatch,
) -> None:
    from relaymd.orchestrator.scheduler import reap_dead_slurm_placeholders

    settings = _settings_with_cluster()
    warning_log = patch("relaymd.orchestrator.services.slurm_provisioning_service.logger.warning")

    async def fake_wait_for(awaitable, timeout):
        if timeout == 30.0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError
        return await awaitable

    async def fake_squeue_noop(*args, **kwargs):
        _ = (args, kwargs)

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return b"", b""

            def kill(self):
                return None

        return FakeProc()

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.create_subprocess_exec",
        fake_squeue_noop,
    )
    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.asyncio.wait_for",
        fake_wait_for,
    )

    with warning_log as warning_mock:
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

    warning_mock.assert_any_call(
        "slurm_squeue_query_timeout",
        cluster_name="gilbreth",
        attempt=2,
        max_attempts=2,
        timeout_seconds=30.0,
        slurm_job_ids=["33333"],
        submission_target="test-user@test-host:22",
    )
    warning_mock.assert_any_call(
        "slurm_placeholder_reap_skipped_due_to_status_query_failure",
        cluster_name="gilbreth",
        placeholder_count=1,
    )
    assert len(remaining) == 1
    assert remaining[0].provider_id == "gilbreth:33333"


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

    async def fake_submit(
        cluster: ClusterConfig,
        _settings: OrchestratorSettings,
        *,
        worker_id: UUID | None = None,
    ) -> str:
        _ = worker_id
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


@pytest.mark.asyncio
async def test_submit_pending_jobs_rolls_back_session_after_unexpected_error(
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

    async def fake_submit_cluster_if_needed(self, *, cluster: ClusterConfig) -> bool:
        now = datetime.now(UTC).replace(tzinfo=None)
        if cluster.name == "gilbreth":
            self._session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model=cluster.gpu_type,
                    gpu_count=cluster.gpu_count,
                    vram_gb=0,
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:bad",
                    last_heartbeat=now,
                    registered_at=now,
                )
            )
            raise RuntimeError("boom")

        self._session.add(
            Worker(
                platform=Platform.hpc,
                gpu_model=cluster.gpu_type,
                gpu_count=cluster.gpu_count,
                vram_gb=0,
                status=WorkerStatus.queued,
                provider_id="anvil:good",
                last_heartbeat=now,
                registered_at=now,
            )
        )
        await self._session.commit()
        return True

    monkeypatch.setattr(
        "relaymd.orchestrator.services.slurm_provisioning_service.SlurmProvisioningService.submit_cluster_if_needed",
        fake_submit_cluster_if_needed,
    )

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
    assert workers[0].provider_id == "anvil:good"
