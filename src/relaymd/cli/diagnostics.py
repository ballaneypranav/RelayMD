from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from relaymd.cli import config as cli_config
from relaymd.cli.runtime_paths import RelaymdPaths, resolve_paths
from relaymd.orchestrator import config as orchestrator_config

SECRET_ENV_NAMES = (
    "INFISICAL_TOKEN",
    "RELAYMD_API_TOKEN",
    "RELAYMD_DASHBOARD_PASSWORD",
    "RELAYMD_DASHBOARD_USERNAME",
    "B2_APPLICATION_KEY",
    "B2_APPLICATION_KEY_ID",
    "DOWNLOAD_BEARER_TOKEN",
    "AXIOM_TOKEN",
    "TAILSCALE_AUTH_KEY",
    "GHCR_PAT",
    "GHCR_USERNAME",
)


def _present(value: str | None) -> str:
    return "present" if value and value.strip() else "missing"


def _redact_error(exc: Exception) -> str:
    message = str(exc)
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name, "")
        if value:
            message = message.replace(value, "[redacted]")
    return message


def _section(ok: bool, **values: Any) -> dict[str, Any]:
    return {"ok": ok, **values}


def _path_exists(path: Path) -> str:
    return "present" if path.exists() else "missing"


def _sqlite_path_from_url(database_url: str) -> Path | None:
    if database_url.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
    elif database_url.startswith("sqlite+aiosqlite:///"):
        raw_path = database_url.removeprefix("sqlite+aiosqlite:///")
    else:
        return None

    if raw_path == ":memory:":
        return None
    return Path(raw_path).expanduser()


def _config_section(paths: RelaymdPaths) -> dict[str, Any]:
    config_exists = paths.yaml_config.is_file()
    parsed = False
    error = ""
    try:
        orchestrator_config.OrchestratorSettings()
        parsed = True
    except Exception as exc:  # noqa: BLE001
        error = _redact_error(exc)
    return _section(
        config_exists and parsed,
        path=str(paths.yaml_config),
        exists=config_exists,
        parsed=parsed,
        error=error,
    )


def _env_file_section(paths: RelaymdPaths) -> dict[str, Any]:
    exists = paths.env_file.is_file()
    return _section(exists, path=str(paths.env_file), exists=exists)


def _cli_submit_section() -> tuple[dict[str, Any], cli_config.CliSettings | None]:
    try:
        settings = cli_config.load_settings()
    except Exception as exc:  # noqa: BLE001
        return (
            _section(
                False,
                api_token="missing",
                b2="missing",
                error=_redact_error(exc),
            ),
            None,
        )

    b2_present = all(
        value.strip()
        for value in (
            settings.b2_endpoint_url,
            settings.b2_bucket_name,
            settings.b2_access_key_id,
            settings.b2_secret_access_key,
        )
    )
    return (
        _section(
            bool(settings.api_token.strip()) and b2_present,
            api_token=_present(settings.api_token),
            b2="present" if b2_present else "missing",
            cf_bearer_token=_present(settings.cf_bearer_token),
        ),
        settings,
    )


def _orchestrator_section() -> tuple[
    dict[str, Any],
    orchestrator_config.OrchestratorSettings | None,
]:
    try:
        settings = orchestrator_config.load_settings()
    except Exception as exc:  # noqa: BLE001
        return (
            _section(
                False,
                api_token="missing",
                axiom_token="missing",
                tailscale_auth_key="unknown",
                error=_redact_error(exc),
            ),
            None,
        )

    needs_tailscale = bool(settings.slurm_cluster_configs) or bool(
        settings.salad_api_key
        and settings.salad_org
        and settings.salad_project
        and settings.salad_container_group
    )
    tailscale_state = _present(settings.tailscale_auth_key) if needs_tailscale else "not_required"
    return (
        _section(
            bool(settings.api_token.strip())
            and bool(settings.axiom_token.strip())
            and (tailscale_state in {"present", "not_required"}),
            api_token=_present(settings.api_token),
            axiom_token=_present(settings.axiom_token),
            tailscale_auth_key=tailscale_state,
            slurm_clusters=len(settings.slurm_cluster_configs),
        ),
        settings,
    )


def _secrets_section(
    cli_status: dict[str, Any],
    orchestrator_status: dict[str, Any],
) -> dict[str, Any]:
    token_present = bool(os.environ.get("INFISICAL_TOKEN", "").strip())
    hydration_ok = bool(cli_status["ok"] and orchestrator_status["ok"])
    errors = [
        status.get("error", "")
        for status in (cli_status, orchestrator_status)
        if status.get("error")
    ]
    return _section(
        token_present and hydration_ok,
        provider="infisical",
        token_present=token_present,
        hydration_ok=hydration_ok,
        error="; ".join(errors),
    )


def _release_section(paths: RelaymdPaths) -> dict[str, Any]:
    cli_executable = paths.current_link.joinpath("relaymd")
    orchestrator_sif = Path(
        os.environ.get(
            "RELAYMD_ORCHESTRATOR_SIF",
            str(paths.current_link / "relaymd-orchestrator.sif"),
        )
    ).expanduser()
    current_exists = paths.current_link.exists()
    cli_ok = cli_executable.is_file() and os.access(cli_executable, os.X_OK)
    sif_ok = orchestrator_sif.is_file()
    return _section(
        current_exists and cli_ok and sif_ok,
        current=str(paths.current_link),
        current_exists=current_exists,
        cli_executable=cli_ok,
        orchestrator_sif=sif_ok,
        orchestrator_sif_path=str(orchestrator_sif),
    )


def _proxy_auth_section() -> dict[str, Any]:
    api_token = _present(os.environ.get("RELAYMD_API_TOKEN"))
    username = _present(os.environ.get("RELAYMD_DASHBOARD_USERNAME"))
    password = _present(os.environ.get("RELAYMD_DASHBOARD_PASSWORD"))
    return _section(
        api_token == username == password == "present",
        api_token=api_token,
        username=username,
        password=password,
    )


def _scheduler_section(
    settings: orchestrator_config.OrchestratorSettings | None,
) -> dict[str, Any]:
    if settings is None:
        return _section(
            False,
            slurm_configured=False,
            sbatch="unknown",
            sif_paths=[],
            error="orchestrator settings unavailable",
        )

    clusters = settings.slurm_cluster_configs
    sbatch = "present" if shutil.which("sbatch") else "missing"
    sif_paths = [
        {
            "cluster": cluster.name,
            "path": cluster.sif_path,
            "exists": Path(cluster.sif_path).expanduser().is_file(),
        }
        for cluster in clusters
        if cluster.sif_path
    ]
    sif_paths_ok = all(item["exists"] for item in sif_paths)
    ok = (not clusters) or (sbatch == "present" and sif_paths_ok)
    return _section(
        ok,
        slurm_configured=bool(clusters),
        cluster_count=len(clusters),
        sbatch=sbatch,
        sif_paths=sif_paths,
    )


def _network_section(
    settings: orchestrator_config.OrchestratorSettings | None,
) -> dict[str, Any]:
    if settings is None:
        return _section(
            False,
            tailscale_socket="unknown",
            error="orchestrator settings unavailable",
        )

    socket_path = Path(settings.tailscale_socket).expanduser()
    exists = socket_path.exists()
    return _section(
        exists,
        tailscale_socket="present" if exists else "missing",
        tailscale_socket_path=str(socket_path),
    )


def _database_section(
    settings: orchestrator_config.OrchestratorSettings | None,
) -> dict[str, Any]:
    if settings is None:
        return _section(
            False,
            url="unknown",
            error="orchestrator settings unavailable",
        )

    database_url = settings.database_url
    parsed = urlparse(database_url)
    sqlite_path = _sqlite_path_from_url(database_url)
    if sqlite_path is None:
        return _section(
            bool(parsed.scheme),
            url=database_url,
            path="",
            parent_writable="not_checked",
        )

    parent = sqlite_path.parent if sqlite_path.parent != Path("") else Path(".")
    parent_exists = parent.exists()
    parent_writable = parent_exists and os.access(parent, os.W_OK)
    return _section(
        parent_exists and parent_writable,
        url=database_url,
        path=str(sqlite_path),
        parent=str(parent),
        parent_exists=parent_exists,
        parent_writable=parent_writable,
    )


def collect_readiness(paths: RelaymdPaths | None = None) -> dict[str, Any]:
    active_paths = paths or resolve_paths()
    env_file = _env_file_section(active_paths)
    config = _config_section(active_paths)
    cli_submit, _cli_settings = _cli_submit_section()
    orchestrator_status, orchestrator_settings = _orchestrator_section()
    readiness: dict[str, Any] = {
        "env_file": env_file,
        "config": config,
        "secrets": _secrets_section(cli_submit, orchestrator_status),
        "cli_submit": cli_submit,
        "orchestrator_config": orchestrator_status,
        "release": _release_section(active_paths),
        "proxy_auth": _proxy_auth_section(),
        "scheduler": _scheduler_section(orchestrator_settings),
        "network": _network_section(orchestrator_settings),
        "database": _database_section(orchestrator_settings),
    }
    readiness["_ok"] = all(
        value.get("ok") is True for value in readiness.values() if isinstance(value, dict)
    )
    return readiness
