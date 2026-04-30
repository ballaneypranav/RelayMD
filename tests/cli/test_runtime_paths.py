from __future__ import annotations

from pathlib import Path

from relaymd.cli.runtime_paths import named_path, resolve_paths


def test_resolve_paths_derives_config_paths_from_data_root(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "relaymd-service"
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_ENV_FILE", raising=False)
    monkeypatch.delenv("RELAYMD_STATUS_FILE", raising=False)

    paths = resolve_paths()

    assert paths.data_root == data_root
    assert paths.yaml_config == data_root / "config" / "relaymd-config.yaml"
    assert paths.env_file == data_root / "config" / "relaymd-service.env"
    assert paths.status_file == data_root / "state" / "relaymd-service.status"
    assert named_path("config") == data_root / "config"


def test_resolve_paths_allows_explicit_path_overrides(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "relaymd-service"
    config = tmp_path / "custom.yaml"
    env_file = tmp_path / "service.env"
    status = tmp_path / "status.env"
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.setenv("RELAYMD_CONFIG", str(config))
    monkeypatch.setenv("RELAYMD_ENV_FILE", str(env_file))
    monkeypatch.setenv("RELAYMD_STATUS_FILE", str(status))

    paths = resolve_paths()

    assert paths.yaml_config == config
    assert paths.env_file == env_file
    assert paths.status_file == status

