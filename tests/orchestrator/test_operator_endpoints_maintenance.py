# ruff: noqa: PLR2004

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from relaymd.models import Job, JobStatus

from relaymd.orchestrator.db import get_sessionmaker
from tests.orchestrator.test_operator_endpoints import (
    app_client,
    make_settings,
    make_slurm_settings,
)


@pytest.mark.asyncio
async def test_prune_jobs_deletes_terminal_jobs_older_than_cutoff() -> None:
    headers = {"X-API-Token": "test-token"}
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=60)
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)

    async with app_client(make_settings()) as (_app, client):
        async with get_sessionmaker()() as session:
            session.add_all(
                [
                    Job(
                        title="old-completed",
                        input_bundle_path="x",
                        status=JobStatus.completed,
                        created_at=old,
                        updated_at=old,
                    ),
                    Job(
                        title="old-failed",
                        input_bundle_path="x",
                        status=JobStatus.failed,
                        created_at=old,
                        updated_at=old,
                    ),
                    Job(
                        title="recent-completed",
                        input_bundle_path="x",
                        status=JobStatus.completed,
                        created_at=recent,
                        updated_at=recent,
                    ),
                    Job(
                        title="old-queued",
                        input_bundle_path="x",
                        status=JobStatus.queued,
                        created_at=old,
                        updated_at=old,
                    ),
                ]
            )
            await session.commit()

        response = await client.delete("/jobs?older_than_days=30", headers=headers)
        assert response.status_code == 200
        assert response.json()["deleted"] == 2

        list_response = await client.get("/jobs", headers=headers)
        titles = [j["title"] for j in list_response.json()]
        assert "old-completed" not in titles
        assert "old-failed" not in titles
        assert "recent-completed" in titles
        assert "old-queued" in titles


@pytest.mark.asyncio
async def test_prune_jobs_rejects_non_terminal_status() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_settings()) as (_app, client):
        response = await client.delete("/jobs?status=running&older_than_days=1", headers=headers)
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_prune_jobs_returns_zero_when_nothing_matches() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_settings()) as (_app, client):
        response = await client.delete("/jobs?older_than_days=30", headers=headers)
        assert response.status_code == 200
        assert response.json()["deleted"] == 0


@pytest.mark.asyncio
async def test_prune_jobs_requires_api_token() -> None:
    async with app_client(make_settings()) as (_app, client):
        response = await client.delete("/jobs")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_slurm_clusters_includes_enabled_default_true() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_slurm_settings()) as (_app, client):
        response = await client.get("/config/slurm-clusters", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["clusters"][0]["name"] == "gilbreth"
    assert payload["clusters"][0]["enabled"] is True
    assert payload["clusters"][1]["name"] == "anvil"
    assert payload["clusters"][1]["enabled"] is True


@pytest.mark.asyncio
async def test_put_slurm_cluster_enabled_map_updates_atomically() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_slurm_settings()) as (_app, client):
        put_response = await client.put(
            "/config/slurm-clusters/enabled",
            headers=headers,
            json={"enabled": {"gilbreth": False, "anvil": True}},
        )
        assert put_response.status_code == 204

        get_response = await client.get("/config/slurm-clusters", headers=headers)
    assert get_response.status_code == 200
    by_name = {cluster["name"]: cluster for cluster in get_response.json()["clusters"]}
    assert by_name["gilbreth"]["enabled"] is False
    assert by_name["anvil"]["enabled"] is True


@pytest.mark.asyncio
async def test_put_slurm_cluster_enabled_map_rejects_missing_or_unknown_names() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_slurm_settings()) as (_app, client):
        bad_put = await client.put(
            "/config/slurm-clusters/enabled",
            headers=headers,
            json={"enabled": {"gilbreth": False, "unknown": True}},
        )
        assert bad_put.status_code == 400

        get_response = await client.get("/config/slurm-clusters", headers=headers)
    assert get_response.status_code == 200
    by_name = {cluster["name"]: cluster for cluster in get_response.json()["clusters"]}
    assert by_name["gilbreth"]["enabled"] is True
    assert by_name["anvil"]["enabled"] is True
