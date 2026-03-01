from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _render_template(payload: dict[str, object]) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    environment = Environment(
        loader=FileSystemLoader(str(repo_root)),
        autoescape=False,
    )
    template = environment.get_template("deploy/slurm/job.sbatch.j2")
    return template.render(**payload)


def test_job_template_renders_cluster_a_values() -> None:
    rendered = _render_template(
        {
            "cluster_name": "gilbreth",
            "partition": "gpu",
            "account": "lab-123",
            "gpu_type": "a100",
            "gpu_count": 2,
            "wall_time": "3:30:00",
            "sif_path": "/shared/containers/relaymd.sif",
            "memory_per_gpu": "60G",
            "infisical_token": "client-id:client-secret",
        }
    )

    assert "#SBATCH --partition=gpu" in rendered
    assert "#SBATCH --gres=gpu:a100:2" in rendered
    assert "#SBATCH --mem-per-gpu=60G" in rendered
    assert "#SBATCH --export=ALL,INFISICAL_BOOTSTRAP_TOKEN=client-id:client-secret" in rendered
    assert "#SBATCH --time=3:30:00" in rendered
    assert "#SBATCH --signal=TERM@300" in rendered
    assert '--env WORKER_PLATFORM="hpc"' in rendered


def test_job_template_renders_cluster_b_values_with_default_wall_time() -> None:
    rendered = _render_template(
        {
            "cluster_name": "anvil",
            "partition": "gpu-debug",
            "account": "proj-999",
            "gpu_type": "a40",
            "gpu_count": 1,
            "gres": "gpu:1",
            "nodes": 1,
            "ntasks": 8,
            "qos": "standby",
            "sif_path": "/anvil/projects/proj-999/containers/relaymd.sif",
            "memory": "80G",
            "infisical_token": "other-client:other-secret",
        }
    )

    assert "#SBATCH --partition=gpu-debug" in rendered
    assert "#SBATCH --gres=gpu:1" in rendered
    assert "#SBATCH --nodes=1" in rendered
    assert "#SBATCH --ntasks=8" in rendered
    assert "#SBATCH --qos=standby" in rendered
    assert "#SBATCH --mem=80G" in rendered
    assert "#SBATCH --export=ALL,INFISICAL_BOOTSTRAP_TOKEN=other-client:other-secret" in rendered
    assert "#SBATCH --time=4:00:00" in rendered
    assert "#SBATCH --signal=TERM@300" in rendered
    assert '--env WORKER_PLATFORM="hpc"' in rendered


def test_job_template_renders_registry_backed_image() -> None:
    rendered = _render_template(
        {
            "cluster_name": "gilbreth",
            "partition": "gpu",
            "account": "lab-123",
            "gpu_type": "a100",
            "gpu_count": 1,
            "apptainer_image": "docker://ghcr.io/acme/relaymd-worker:latest",
            "infisical_token": "client-id:client-secret",
        }
    )

    # The flock pre-pull block must reference the docker URI for the slug/pull.
    assert "docker://ghcr.io/acme/relaymd-worker:latest" in rendered
    # The exec line must use the resolved shell variable (not the raw URI).
    assert '"${_APPTAINER_IMAGE}" python -m relaymd.worker' in rendered
    # flock serialisation block must be present.
    assert "flock -x 200" in rendered
    assert "apptainer pull" in rendered
