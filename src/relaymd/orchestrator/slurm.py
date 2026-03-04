from __future__ import annotations

import asyncio
from contextlib import suppress

import structlog
from jinja2 import Environment, PackageLoader

from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings


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
) -> str:
    template = _template_environment().get_template("job.sbatch.j2")
    return template.render(
        cluster_name=cluster.name,
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


async def submit_slurm_job(cluster: ClusterConfig, settings: OrchestratorSettings) -> str:
    rendered = _render_sbatch_script(
        cluster,
        settings=settings,
    )

    logger = structlog.get_logger(__name__)
    logger.debug("Submitting job script:\n%s", rendered)

    command = [
        "ssh",
        "-q",
        "-o",
        "BatchMode=yes",
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
        raise RuntimeError(
            f"sbatch submission timed out after {settings.sbatch_submit_timeout_seconds:.1f}s"
        ) from exc
    if process.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"sbatch submission failed: rc={process.returncode}, stderr={stderr_text}"
        )

    output = stdout.decode("utf-8", errors="replace").strip()
    if not output:
        raise RuntimeError("sbatch --parsable returned empty output")

    return output.split(";", 1)[0]
