from __future__ import annotations

from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from relaymd.worker.gateway import (
    TAILSCALE_SOCKS5_PROXY_URL,
    ApiOrchestratorGateway,
)
from relaymd_api_client import errors as api_errors
from relaymd_api_client.models.platform import Platform as ApiPlatform

REGISTER_SYNC_TARGET = "relaymd.worker.gateway.register_worker_workers_register_post.sync"


def _disable_retry_sleep(monkeypatch) -> None:
    monkeypatch.setattr("tenacity.nap.sleep", lambda _seconds: None)


def _build_gateway(*, max_attempts: int = 3) -> tuple[ApiOrchestratorGateway, Mock]:
    logger = Mock()
    gateway = ApiOrchestratorGateway(
        orchestrator_url="http://orchestrator",
        api_token="api-token",
        logger=logger,
        register_worker_max_attempts=max_attempts,
    )
    gateway._client = cast(Any, object())
    return gateway, logger


def test_register_worker_retries_connect_timeout_then_succeeds(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    request = httpx.Request("POST", "http://orchestrator/workers/register")
    expected_worker_id = str(uuid4())
    register_sync = Mock(
        side_effect=[
            httpx.ConnectTimeout("timed out connecting to orchestrator", request=request),
            {"worker_id": expected_worker_id},
        ]
    )
    monkeypatch.setattr(REGISTER_SYNC_TARGET, register_sync)
    gateway, logger = _build_gateway(max_attempts=3)

    worker_id = gateway.register_worker(
        platform=ApiPlatform.SALAD,
        gpu_model="NVIDIA A100",
        gpu_count=1,
        vram_gb=80,
    )

    assert str(worker_id) == expected_worker_id
    assert register_sync.call_count == 2
    logger.warning.assert_called_once()


def test_register_worker_raises_after_exhausting_retries(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    request = httpx.Request("POST", "http://orchestrator/workers/register")
    register_sync = Mock(side_effect=httpx.ConnectTimeout("connect timeout", request=request))
    monkeypatch.setattr(REGISTER_SYNC_TARGET, register_sync)
    gateway, _ = _build_gateway(max_attempts=3)

    with pytest.raises(
        RuntimeError,
        match="Failed to register worker with orchestrator",
    ) as excinfo:
        gateway.register_worker(
            platform=ApiPlatform.SALAD,
            gpu_model="NVIDIA A100",
            gpu_count=1,
            vram_gb=80,
        )

    assert "after 3 attempts" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, httpx.ConnectTimeout)
    assert register_sync.call_count == 3


def test_register_worker_does_not_retry_on_unexpected_status_401(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    register_sync = Mock(side_effect=api_errors.UnexpectedStatus(401, b"unauthorized"))
    monkeypatch.setattr(REGISTER_SYNC_TARGET, register_sync)
    gateway, logger = _build_gateway(max_attempts=4)

    with pytest.raises(api_errors.UnexpectedStatus):
        gateway.register_worker(
            platform=ApiPlatform.SALAD,
            gpu_model="NVIDIA A100",
            gpu_count=1,
            vram_gb=80,
        )

    assert register_sync.call_count == 1
    logger.warning.assert_not_called()


def test_gateway_uses_socks5_proxy_when_userspace_proxy_is_available(monkeypatch) -> None:
    created_kwargs: dict[str, Any] = {}

    class _FakeClientContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, exc_type, exc, tb) -> bool:
            _ = (exc_type, exc, tb)
            return False

    def _build_client(**kwargs: Any) -> _FakeClientContext:
        created_kwargs.update(kwargs)
        return _FakeClientContext()

    monkeypatch.setattr("relaymd.worker.gateway.RelaymdApiClient", _build_client)
    monkeypatch.setattr(
        ApiOrchestratorGateway,
        "_should_use_tailscale_userspace_proxy",
        staticmethod(lambda: True),
    )

    gateway, logger = _build_gateway(max_attempts=3)
    with gateway:
        pass

    assert created_kwargs["httpx_args"] == {"proxy": TAILSCALE_SOCKS5_PROXY_URL}
    logger.info.assert_called_once()


def test_gateway_skips_proxy_when_userspace_proxy_is_unavailable(monkeypatch) -> None:
    created_kwargs: dict[str, Any] = {}

    class _FakeClientContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, exc_type, exc, tb) -> bool:
            _ = (exc_type, exc, tb)
            return False

    def _build_client(**kwargs: Any) -> _FakeClientContext:
        created_kwargs.update(kwargs)
        return _FakeClientContext()

    monkeypatch.setattr("relaymd.worker.gateway.RelaymdApiClient", _build_client)
    monkeypatch.setattr(
        ApiOrchestratorGateway,
        "_should_use_tailscale_userspace_proxy",
        staticmethod(lambda: False),
    )

    gateway, logger = _build_gateway(max_attempts=3)
    with gateway:
        pass

    assert created_kwargs["httpx_args"] == {}
    logger.info.assert_not_called()
