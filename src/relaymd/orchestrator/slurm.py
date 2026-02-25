from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import suppress

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
        gpu_type=cluster.gpu_type,
        gpu_count=cluster.gpu_count,
        wall_time=cluster.wall_time,
        sif_path=cluster.sif_path,
        infisical_token_shell_quoted=_shell_single_quote(settings.infisical_token),
        slurm_sigterm_margin_seconds=settings.slurm_sigterm_margin_seconds,
        worker_heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
        worker_checkpoint_poll_interval_seconds=settings.worker_checkpoint_poll_interval_seconds,
        worker_orchestrator_timeout_seconds=settings.worker_orchestrator_timeout_seconds,
        worker_sigterm_checkpoint_wait_seconds=settings.worker_sigterm_checkpoint_wait_seconds,
        worker_sigterm_checkpoint_poll_seconds=settings.worker_sigterm_checkpoint_poll_seconds,
        worker_sigterm_process_wait_seconds=settings.worker_sigterm_process_wait_seconds,
        worker_platform="hpc",
    )


async def submit_slurm_job(cluster: ClusterConfig, settings: OrchestratorSettings) -> str:
    rendered = _render_sbatch_script(
        cluster,
        settings=settings,
    )

    tmp_script_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sbatch",
            prefix=f"relaymd-{cluster.name}-",
            delete=False,
            encoding="utf-8",
        ) as tmp_script:
            tmp_script.write(rendered)
            tmp_script_path = tmp_script.name

        process = await asyncio.create_subprocess_exec(
            "sbatch",
            "--parsable",
            tmp_script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.sbatch_submit_timeout_seconds,
            )
        except TimeoutError as exc:
            with suppress(ProcessLookupError):
                process.kill()
            with suppress(Exception):  # noqa: BLE001
                await asyncio.wait_for(process.communicate(), timeout=1.0)
            raise RuntimeError(
                "sbatch submission timed out after "
                f"{settings.sbatch_submit_timeout_seconds:.1f}s"
            ) from exc
        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                "sbatch submission failed: "
                f"rc={process.returncode}, stderr={stderr_text}"
            )

        output = stdout.decode("utf-8", errors="replace").strip()
        if not output:
            raise RuntimeError("sbatch --parsable returned empty output")

        return output.split(";", 1)[0]
    finally:
        if tmp_script_path is not None:
            with suppress(FileNotFoundError):
                os.unlink(tmp_script_path)
