from __future__ import annotations

import importlib.util
import pathlib

import pytest

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_infisical_secrets.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_infisical_secrets", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load check_infisical_secrets module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_script_module()

    monkeypatch.setenv("INFISICAL_CLIENT_ID", "client-id")
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")

    class _FakeManager:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def fetch_mapped_secrets(self, *, required, optional=None):
            _ = optional
            return {name: f"{name}-value" for name in required.values()}

    monkeypatch.setattr(module, "InfisicalSecretManager", _FakeManager)

    result = module.main()
    captured = capsys.readouterr()

    assert result == 0
    assert "✓ AXIOM_TOKEN = AXIOM_..." in captured.out
    assert captured.err == ""


def test_main_missing_required_env(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module()

    monkeypatch.delenv("INFISICAL_CLIENT_ID", raising=False)
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")

    with pytest.raises(SystemExit, match="1"):
        module.main()

    captured = capsys.readouterr()
    assert "Missing required environment variable: INFISICAL_CLIENT_ID" in captured.err


def test_main_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module()

    monkeypatch.setenv("INFISICAL_CLIENT_ID", "client-id")
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")

    class _FailingManager:
        def __init__(self, **kwargs):
            _ = kwargs
            raise RuntimeError("bad creds")

    monkeypatch.setattr(module, "InfisicalSecretManager", _FailingManager)

    with pytest.raises(SystemExit, match="1"):
        module.main()

    captured = capsys.readouterr()
    assert "Infisical auth failed." in captured.err
    assert "Error: bad creds" in captured.err


def test_main_fails_when_secret_empty(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module()

    monkeypatch.setenv("INFISICAL_CLIENT_ID", "client-id")
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")

    class _FakeManager:
        def __init__(self, **kwargs):
            _ = kwargs

        def fetch_mapped_secrets(self, *, required, optional=None):
            _ = optional
            values = {name: f"{name}-value" for name in required.values()}
            values["AXIOM_TOKEN"] = ""
            return values

    monkeypatch.setattr(module, "InfisicalSecretManager", _FakeManager)

    with pytest.raises(SystemExit, match="1"):
        module.main()

    captured = capsys.readouterr()
    assert "Secret AXIOM_TOKEN is empty" in captured.err
