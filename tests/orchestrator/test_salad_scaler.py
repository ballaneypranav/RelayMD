from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest
from relaymd.models import Job, JobStatus

from relaymd.orchestrator import main as orchestrator_main
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.main import create_app
from relaymd.orchestrator.scheduler import apply_salad_autoscaling_policy


@asynccontextmanager
async def app_with_db(settings: OrchestratorSettings):
    app = create_app(settings, start_background_tasks=False)
    with patch.object(orchestrator_main, "_ensure_tailscale_running", return_value=None):
        async with app.router.lifespan_context(app):
            yield app


def _salad_settings() -> OrchestratorSettings:
    return OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        slurm_cluster_configs=[],
        salad_api_key="salad-key",
        salad_org="org",
        salad_project="project",
        salad_container_group="group",
        salad_max_replicas=4,
    )


def _mock_async_client(get_replicas: int):
    client_cm = AsyncMock()
    client = AsyncMock()
    client_cm.__aenter__.return_value = client
    client_cm.__aexit__.return_value = False

    get_response = Mock()
    get_response.json.return_value = {"replicas": get_replicas}
    get_response.raise_for_status.return_value = None

    patch_response = Mock()
    patch_response.raise_for_status.return_value = None

    client.get.return_value = get_response
    client.patch.return_value = patch_response
    return client_cm, client


@pytest.mark.asyncio
async def test_scale_up_when_jobs_queued_and_no_idle_hpc_workers() -> None:
    settings = _salad_settings()
    client_cm, client = _mock_async_client(get_replicas=0)

    async with app_with_db(settings):
        async with get_sessionmaker()() as session:
            session.add(
                Job(
                    title="queued-job",
                    input_bundle_path="jobs/1/input/bundle.tar.gz",
                    status=JobStatus.queued,
                )
            )
            await session.commit()

        with patch("relaymd.orchestrator.salad_scaler.httpx.AsyncClient", return_value=client_cm):
            await apply_salad_autoscaling_policy(settings)

    client.get.assert_awaited_once()
    client.patch.assert_awaited_once()
    assert client.get.await_args.kwargs["headers"]["Salad-Api-Key"] == "salad-key"
    assert client.patch.await_args.kwargs["headers"]["Salad-Api-Key"] == "salad-key"
    assert client.patch.await_args.kwargs["json"] == {"replicas": 1}


@pytest.mark.asyncio
async def test_scale_down_to_zero_when_queue_is_empty() -> None:
    settings = _salad_settings()
    client_cm, client = _mock_async_client(get_replicas=3)

    async with app_with_db(settings):
        with patch("relaymd.orchestrator.salad_scaler.httpx.AsyncClient", return_value=client_cm):
            await apply_salad_autoscaling_policy(settings)

    client.get.assert_awaited_once()
    client.patch.assert_awaited_once()
    assert client.get.await_args.kwargs["headers"]["Salad-Api-Key"] == "salad-key"
    assert client.patch.await_args.kwargs["headers"]["Salad-Api-Key"] == "salad-key"
    assert client.patch.await_args.kwargs["json"] == {"replicas": 0}


@pytest.mark.asyncio
async def test_skips_salad_api_when_api_key_unset() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        slurm_cluster_configs=[],
        salad_api_key=None,
        salad_org="org",
        salad_project="project",
        salad_container_group="group",
    )

    async with app_with_db(settings):
        with patch("relaymd.orchestrator.salad_scaler.httpx.AsyncClient") as async_client:
            await apply_salad_autoscaling_policy(settings)

    async_client.assert_not_called()
