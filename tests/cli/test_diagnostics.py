from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from relaymd.cli import diagnostics
from relaymd.cli.runtime_paths import RelaymdPaths


def _paths(tmp_path: Path) -> RelaymdPaths:
    data_root = tmp_path / "data"
    service_root = tmp_path / "apps" / "relaymd"
    return RelaymdPaths(
        service_root=service_root,
        data_root=data_root,
        current_link=service_root / "current",
        config_dir=data_root / "config",
        yaml_config=data_root / "config" / "relaymd-config.yaml",
        env_file=data_root / "config" / "relaymd-service.env",
        status_file=data_root / "state" / "relaymd-service.status",
        service_log_dir=data_root / "logs" / "service",
        orchestrator_wrapper_log=data_root / "logs" / "service" / "orchestrator.log",
        proxy_wrapper_log=data_root / "logs" / "service" / "proxy.log",
        current_release=service_root / "current",
        releases_dir=service_root / "releases",
        orchestrator_session="relaymd-service",
        proxy_session="relaymd-service-proxy",
        orchestrator_port="36158",
        proxy_port="36159",
        primary_host="",
    )


def _fake_cli_settings() -> SimpleNamespace:
    return SimpleNamespace(
        api_token="api-token",
        b2_endpoint_url="https://s3.example",
        b2_bucket_name="bucket",
        b2_access_key_id="key-id",
        b2_secret_access_key="secret",
        cf_bearer_token="download-token",
    )


def _fake_orchestrator_settings(tmp_path: Path) -> SimpleNamespace:
    sif_path = tmp_path / "worker.sif"
    sif_path.write_text("sif", encoding="utf-8")
    socket_path = tmp_path / "tailscale.sock"
    socket_path.write_text("socket", encoding="utf-8")
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    return SimpleNamespace(
        api_token="api-token",
        axiom_token="axiom-token",
        tailscale_auth_key="tskey",
        slurm_cluster_configs=[
            SimpleNamespace(name="gpu", sif_path=str(sif_path), image_uri=None)
        ],
        salad_api_key=None,
        salad_org=None,
        salad_project=None,
        salad_container_group=None,
        tailscale_socket=str(socket_path),
        database_url=f"sqlite+aiosqlite:///{db_dir / 'relaymd.db'}",
    )


def _fake_orchestrator_settings_without_provisioning(tmp_path: Path) -> SimpleNamespace:
    missing_socket_path = tmp_path / "missing-tailscale.sock"
    db_dir = tmp_path / "db-no-provisioning"
    db_dir.mkdir()
    return SimpleNamespace(
        api_token="api-token",
        axiom_token="axiom-token",
        tailscale_auth_key="",
        slurm_cluster_configs=[],
        salad_api_key=None,
        salad_org=None,
        salad_project=None,
        salad_container_group=None,
        tailscale_socket=str(missing_socket_path),
        database_url=f"sqlite+aiosqlite:///{db_dir / 'relaymd.db'}",
    )


def _prepare_release(paths: RelaymdPaths) -> None:
    paths.env_file.parent.mkdir(parents=True)
    paths.env_file.write_text("INFISICAL_TOKEN=client:secret\n", encoding="utf-8")
    paths.yaml_config.write_text("database_url: sqlite+aiosqlite:///relaymd.db\n", encoding="utf-8")
    paths.current_link.mkdir(parents=True)
    cli = paths.current_link / "relaymd"
    cli.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    cli.chmod(0o755)
    (paths.current_link / "relaymd-orchestrator.sif").write_text("sif", encoding="utf-8")


def _patch_orchestrator_settings(monkeypatch, settings: SimpleNamespace) -> None:
    monkeypatch.setattr(
        diagnostics.orchestrator_config,
        "OrchestratorSettings",
        lambda: settings,
    )
    monkeypatch.setattr(diagnostics.orchestrator_config, "load_settings", lambda: settings)


def test_collect_readiness_reports_missing_infisical_token(monkeypatch, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _prepare_release(paths)
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.setattr(
        diagnostics.cli_config,
        "load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("INFISICAL_TOKEN is required")),
    )
    orch_settings = _fake_orchestrator_settings(tmp_path)
    _patch_orchestrator_settings(monkeypatch, orch_settings)
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: f"/usr/bin/{name}")

    readiness = diagnostics.collect_readiness(paths)

    assert readiness["_ok"] is False
    assert readiness["secrets"]["ok"] is False
    assert readiness["secrets"]["token_present"] is False
    assert readiness["cli_submit"]["ok"] is False


def test_collect_readiness_redacts_secret_values(monkeypatch, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _prepare_release(paths)
    secret = "client-id:very-secret-value"
    monkeypatch.setenv("INFISICAL_TOKEN", secret)
    monkeypatch.setattr(
        diagnostics.cli_config,
        "load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError(f"bad token {secret}")),
    )
    orch_settings = _fake_orchestrator_settings(tmp_path)
    _patch_orchestrator_settings(monkeypatch, orch_settings)

    payload = json.dumps(diagnostics.collect_readiness(paths))

    assert secret not in payload
    assert "[redacted]" in payload


def test_collect_readiness_reports_successful_full_readiness(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _prepare_release(paths)
    monkeypatch.setenv("INFISICAL_TOKEN", "client:secret")
    monkeypatch.setenv("RELAYMD_API_TOKEN", "api-token")
    monkeypatch.setenv("RELAYMD_DASHBOARD_USERNAME", "operator")
    monkeypatch.setenv("RELAYMD_DASHBOARD_PASSWORD", "password")
    monkeypatch.setattr(diagnostics.cli_config, "load_settings", _fake_cli_settings)
    orch_settings = _fake_orchestrator_settings(tmp_path)
    _patch_orchestrator_settings(monkeypatch, orch_settings)
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: f"/usr/bin/{name}")

    readiness = diagnostics.collect_readiness(paths)

    assert readiness["_ok"] is True
    assert readiness["secrets"]["hydration_ok"] is True
    assert readiness["cli_submit"]["api_token"] == "present"
    assert readiness["cli_submit"]["b2"] == "present"
    assert readiness["orchestrator_config"]["axiom_token"] == "present"


def test_collect_readiness_reports_missing_proxy_auth(monkeypatch, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _prepare_release(paths)
    monkeypatch.setenv("INFISICAL_TOKEN", "client:secret")
    for name in (
        "RELAYMD_API_TOKEN",
        "RELAYMD_DASHBOARD_USERNAME",
        "RELAYMD_DASHBOARD_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(diagnostics.cli_config, "load_settings", _fake_cli_settings)
    orch_settings = _fake_orchestrator_settings(tmp_path)
    _patch_orchestrator_settings(monkeypatch, orch_settings)
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: f"/usr/bin/{name}")

    readiness = diagnostics.collect_readiness(paths)

    assert readiness["_ok"] is False
    assert readiness["proxy_auth"]["ok"] is False
    assert readiness["proxy_auth"]["password"] == "missing"


def test_collect_readiness_does_not_require_tailscale_without_provisioning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _prepare_release(paths)
    monkeypatch.setenv("INFISICAL_TOKEN", "client:secret")
    monkeypatch.setenv("RELAYMD_API_TOKEN", "api-token")
    monkeypatch.setenv("RELAYMD_DASHBOARD_USERNAME", "operator")
    monkeypatch.setenv("RELAYMD_DASHBOARD_PASSWORD", "password")
    monkeypatch.setattr(diagnostics.cli_config, "load_settings", _fake_cli_settings)
    orch_settings = _fake_orchestrator_settings_without_provisioning(tmp_path)
    _patch_orchestrator_settings(monkeypatch, orch_settings)

    readiness = diagnostics.collect_readiness(paths)

    assert readiness["_ok"] is True
    assert readiness["orchestrator_config"]["tailscale_auth_key"] == "not_required"
    assert readiness["network"]["ok"] is True
    assert readiness["network"]["tailscale_socket"] == "not_required"
    assert readiness["network"]["required"] is False
    assert readiness["network"]["checked"] is False
