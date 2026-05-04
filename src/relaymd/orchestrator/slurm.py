from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from uuid import UUID, uuid4

import structlog
from jinja2 import Environment, PackageLoader

from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings


class SlurmSubmissionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        cluster_name: str,
        partition: str,
        account: str,
        qos: str | None,
        gres: str,
        nodes: int | None,
        ntasks: int | None,
        wall_time: str,
        memory: str | None,
        memory_per_gpu: str | None,
        ssh_host: str,
        ssh_username: str,
        ssh_port: int,
        ssh_key_file: str | None,
        command: list[str],
        timeout_seconds: float,
        return_code: int | None,
        stdout: str | None,
        stderr: str | None,
        local_script_path: str | None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.cluster_name = cluster_name
        self.partition = partition
        self.account = account
        self.qos = qos
        self.gres = gres
        self.nodes = nodes
        self.ntasks = ntasks
        self.wall_time = wall_time
        self.memory = memory
        self.memory_per_gpu = memory_per_gpu
        self.ssh_host = ssh_host
        self.ssh_username = ssh_username
        self.ssh_port = ssh_port
        self.ssh_key_file = ssh_key_file
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.local_script_path = local_script_path

    @property
    def submission_target(self) -> str:
        return f"{self.ssh_username}@{self.ssh_host}:{self.ssh_port}"

    def to_log_fields(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "cluster_name": self.cluster_name,
            "partition": self.partition,
            "account": self.account,
            "qos": self.qos,
            "gres": self.gres,
            "nodes": self.nodes,
            "ntasks": self.ntasks,
            "wall_time": self.wall_time,
            "memory": self.memory,
            "memory_per_gpu": self.memory_per_gpu,
            "ssh_host": self.ssh_host,
            "ssh_username": self.ssh_username,
            "ssh_port": self.ssh_port,
            "ssh_key_file": self.ssh_key_file,
            "submission_target": self.submission_target,
            "command": self.command,
            "timeout_seconds": self.timeout_seconds,
            "return_code": self.return_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "local_script_path": self.local_script_path,
        }


class _SubmissionContext(TypedDict):
    stage: str
    cluster_name: str
    partition: str
    account: str
    qos: str | None
    gres: str
    nodes: int | None
    ntasks: int | None
    wall_time: str
    memory: str | None
    memory_per_gpu: str | None
    ssh_host: str
    ssh_username: str
    ssh_port: int
    ssh_key_file: str | None
    command: list[str]
    timeout_seconds: float
    return_code: int | None
    stdout: str | None
    stderr: str | None
    local_script_path: str | None


def _build_submission_context(
    cluster: ClusterConfig,
    *,
    command: list[str],
    timeout_seconds: float,
    return_code: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    local_script_path: str | None = None,
    stage: str,
) -> _SubmissionContext:
    return {
        "stage": stage,
        "cluster_name": cluster.name,
        "partition": cluster.partition,
        "account": cluster.account,
        "qos": cluster.qos,
        "gres": cluster.slurm_gres,
        "nodes": cluster.nodes,
        "ntasks": cluster.ntasks,
        "wall_time": cluster.wall_time,
        "memory": cluster.memory,
        "memory_per_gpu": cluster.memory_per_gpu,
        "ssh_host": cluster.ssh_host,
        "ssh_username": cluster.ssh_username,
        "ssh_port": cluster.ssh_port,
        "ssh_key_file": cluster.ssh_key_file,
        "command": command,
        "timeout_seconds": timeout_seconds,
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "local_script_path": local_script_path,
    }


def _shell_single_quote(value: str) -> str:
    # Always return a single-quoted shell literal.
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _template_environment() -> Environment:
    return Environment(
        loader=PackageLoader("relaymd.orchestrator", "templates"),
        autoescape=False,
    )


def _render_sbatch_script(
    cluster: ClusterConfig,
    *,
    settings: OrchestratorSettings,
    worker_id: UUID | None = None,
) -> str:
    worker_id = worker_id or uuid4()
    docker_username = settings.apptainer_docker_username.strip()
    docker_password = settings.apptainer_docker_password
    template = _template_environment().get_template("job.sbatch.j2")
    return template.render(
        cluster_name=cluster.name,
        worker_id_short=worker_id.hex[:8],
        partition=cluster.partition,
        account=cluster.account,
        gres=cluster.slurm_gres,
        nodes=cluster.nodes,
        ntasks=cluster.ntasks,
        qos=cluster.qos,
        memory=cluster.memory,
        memory_per_gpu=cluster.memory_per_gpu,
        wall_time=cluster.wall_time,
        apptainer_image=cluster.apptainer_image,
        infisical_token_shell_quoted=_shell_single_quote(settings.infisical_token),
        apptainer_docker_login=bool(docker_username and docker_password),
        apptainer_docker_username_shell_quoted=(
            _shell_single_quote(docker_username) if docker_username else None
        ),
        apptainer_docker_password_shell_quoted=(
            _shell_single_quote(docker_password) if docker_password else None
        ),
        slurm_sigterm_margin_seconds=settings.slurm_sigterm_margin_seconds,
        worker_heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
        worker_checkpoint_poll_interval_seconds=settings.worker_checkpoint_poll_interval_seconds,
        worker_orchestrator_timeout_seconds=settings.worker_orchestrator_timeout_seconds,
        worker_sigterm_checkpoint_wait_seconds=settings.worker_sigterm_checkpoint_wait_seconds,
        worker_sigterm_checkpoint_poll_seconds=settings.worker_sigterm_checkpoint_poll_seconds,
        worker_sigterm_process_wait_seconds=settings.worker_sigterm_process_wait_seconds,
        worker_idle_strategy=cluster.idle_strategy or settings.worker_idle_strategy,
        worker_idle_poll_interval_seconds=(
            cluster.idle_poll_interval_seconds
            if cluster.idle_poll_interval_seconds is not None
            else settings.worker_idle_poll_interval_seconds
        ),
        worker_idle_poll_max_seconds=(
            cluster.idle_poll_max_seconds
            if cluster.idle_poll_max_seconds is not None
            else settings.worker_idle_poll_max_seconds
        ),
        worker_platform="hpc",
        log_directory=cluster.log_directory,
    )


def _write_sbatch_script_to_disk(
    *,
    cluster: ClusterConfig,
    settings: OrchestratorSettings,
    rendered_script: str,
) -> str | None:
    if not settings.log_directory or not settings.log_directory.strip():
        return None

    base_dir = Path(settings.log_directory).expanduser() / "slurm"
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    filename = f"{cluster.name}-{timestamp}-{uuid4().hex[:8]}.sbatch"
    script_path = base_dir / filename
    script_path.write_text(_redact_sbatch_script_for_disk(rendered_script), encoding="utf-8")
    return str(script_path)


def _redact_sbatch_script_for_disk(rendered_script: str) -> str:
    redacted = re.sub(
        r"(?m)^(export INFISICAL_BOOTSTRAP_TOKEN=).*$",
        r"\1'[REDACTED]'",
        rendered_script,
    )
    return re.sub(
        r"(?m)^(export APPTAINER_DOCKER_PASSWORD=).*$",
        r"\1'[REDACTED]'",
        redacted,
    )


async def submit_slurm_job(
    cluster: ClusterConfig,
    settings: OrchestratorSettings,
    *,
    worker_id: UUID | None = None,
) -> str:
    rendered = _render_sbatch_script(
        cluster,
        settings=settings,
        worker_id=worker_id,
    )

    logger = structlog.get_logger(__name__)
    logger.debug("Submitting job script:\n%s", _redact_sbatch_script_for_disk(rendered))
    local_script_path = _write_sbatch_script_to_disk(
        cluster=cluster,
        settings=settings,
        rendered_script=rendered,
    )

    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
    ]
    if cluster.ssh_port != 22:
        command.extend(["-p", str(cluster.ssh_port)])
    if cluster.ssh_key_file:
        command.extend(["-i", cluster.ssh_key_file])
    command.append(f"{cluster.ssh_username}@{cluster.ssh_host}")
    if cluster.log_directory:
        command.append(
            f"mkdir -p {_shell_single_quote(cluster.log_directory)} && sbatch --parsable"
        )
    else:
        command.extend(["sbatch", "--parsable"])

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=rendered.encode("utf-8")),
            timeout=settings.sbatch_submit_timeout_seconds,
        )
    except TimeoutError as exc:
        with suppress(ProcessLookupError):
            process.kill()
        with suppress(Exception):  # noqa: BLE001
            await asyncio.wait_for(process.communicate(), timeout=1.0)
        raise SlurmSubmissionError(
            f"sbatch submission timed out after {settings.sbatch_submit_timeout_seconds:.1f}s",
            **_build_submission_context(
                cluster,
                command=command,
                timeout_seconds=settings.sbatch_submit_timeout_seconds,
                local_script_path=local_script_path,
                stage="timeout",
            ),
        ) from exc
    if process.returncode != 0:
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        raise SlurmSubmissionError(
            f"sbatch submission failed: rc={process.returncode}, stderr={stderr_text}",
            **_build_submission_context(
                cluster,
                command=command,
                timeout_seconds=settings.sbatch_submit_timeout_seconds,
                return_code=process.returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                local_script_path=local_script_path,
                stage="nonzero_exit",
            ),
        )

    output = stdout.decode("utf-8", errors="replace").strip()
    if not output:
        raise SlurmSubmissionError(
            "sbatch --parsable returned empty output",
            **_build_submission_context(
                cluster,
                command=command,
                timeout_seconds=settings.sbatch_submit_timeout_seconds,
                return_code=process.returncode,
                local_script_path=local_script_path,
                stage="empty_output",
            ),
        )

    return output.split(";", 1)[0]
