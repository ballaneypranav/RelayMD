from __future__ import annotations

from relaymd.models import Platform, Worker
from relaymd.orchestrator.scheduling import score_worker


def test_score_prefers_more_gpus_on_hpc() -> None:
    four_gpu = Worker(platform=Platform.hpc, gpu_model="NVIDIA A100", gpu_count=4, vram_gb=80)
    one_gpu = Worker(platform=Platform.hpc, gpu_model="NVIDIA A100", gpu_count=1, vram_gb=80)
    assert score_worker(four_gpu) > score_worker(one_gpu)


def test_score_prefers_hpc_over_salad_for_equal_gpu_count() -> None:
    hpc_worker = Worker(platform=Platform.hpc, gpu_model="NVIDIA A10", gpu_count=1, vram_gb=24)
    salad_worker = Worker(platform=Platform.salad, gpu_model="NVIDIA A10", gpu_count=1, vram_gb=24)
    assert score_worker(hpc_worker) > score_worker(salad_worker)


def test_score_prefers_higher_vram_models_among_single_gpu_hpc() -> None:
    h100 = Worker(platform=Platform.hpc, gpu_model="NVIDIA H100", gpu_count=1, vram_gb=0)
    a100 = Worker(platform=Platform.hpc, gpu_model="NVIDIA A100", gpu_count=1, vram_gb=0)
    a10 = Worker(platform=Platform.hpc, gpu_model="NVIDIA A10", gpu_count=1, vram_gb=0)
    assert score_worker(h100) > score_worker(a100) > score_worker(a10)
