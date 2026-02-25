from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from relaymd.orchestrator.config import ClusterConfig


def _template_environment() -> Environment:
    repo_root = Path(__file__).resolve().parents[3]
    return Environment(
        loader=FileSystemLoader(str(repo_root)),
        autoescape=False,
    )


def _render_sbatch_script(
    cluster: ClusterConfig,
    *,
    gpu_count: int,
    infisical_token: str,
) -> str:
    template = _template_environment().get_template("deploy/slurm/job.sbatch.j2")
    return template.render(
        cluster_name=cluster.name,
        partition=cluster.partition,
        account=cluster.account,
        gpu_type=cluster.gpu_type,
        gpu_count=gpu_count,
        wall_time=cluster.wall_time,
        sif_path=cluster.sif_path,
        infisical_token=infisical_token,
    )


async def submit_slurm_job(cluster: ClusterConfig, gpu_count: int, infisical_token: str) -> str:
    rendered = _render_sbatch_script(
        cluster,
        gpu_count=gpu_count,
        infisical_token=infisical_token,
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
        stdout, stderr = await process.communicate()
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
