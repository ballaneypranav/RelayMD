from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SERVICE_ROOT = "/depot/plow/apps/relaymd"
DEFAULT_DATA_ROOT = "/depot/plow/data/pballane/relaymd-service"
DEFAULT_ORCHESTRATOR_PORT = "36158"
DEFAULT_PROXY_PORT = "36159"


@dataclass(frozen=True)
class RelaymdPaths:
    service_root: Path
    data_root: Path
    current_link: Path
    config_dir: Path
    yaml_config: Path
    env_file: Path
    status_file: Path
    service_log_dir: Path
    orchestrator_wrapper_log: Path
    proxy_wrapper_log: Path
    current_release: Path
    releases_dir: Path
    orchestrator_session: str
    proxy_session: str
    orchestrator_port: str
    proxy_port: str
    primary_host: str


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, comments=False, posix=True)
        except ValueError:
            parsed = [value.strip()]
        values[key] = parsed[0] if parsed else ""
    return values


def _merged_env() -> dict[str, str]:
    env = dict(os.environ)
    data_root = Path(env.get("RELAYMD_DATA_ROOT", DEFAULT_DATA_ROOT)).expanduser()
    env_file = Path(
        env.get("RELAYMD_ENV_FILE", str(data_root / "config" / "relaymd-service.env"))
    ).expanduser()
    env.update(_parse_env_file(env_file))
    return env


def resolve_paths() -> RelaymdPaths:
    env = _merged_env()
    service_root = Path(env.get("RELAYMD_SERVICE_ROOT", DEFAULT_SERVICE_ROOT)).expanduser()
    data_root = Path(env.get("RELAYMD_DATA_ROOT", DEFAULT_DATA_ROOT)).expanduser()
    current_link = Path(env.get("CURRENT_LINK", str(service_root / "current"))).expanduser()
    config_dir = data_root / "config"
    yaml_config = Path(
        env.get("RELAYMD_CONFIG", str(config_dir / "relaymd-config.yaml"))
    ).expanduser()
    env_file = Path(
        env.get("RELAYMD_ENV_FILE", str(config_dir / "relaymd-service.env"))
    ).expanduser()
    status_file = Path(
        env.get("RELAYMD_STATUS_FILE", str(data_root / "state" / "relaymd-service.status"))
    ).expanduser()
    service_log_dir = Path(
        env.get("RELAYMD_SERVICE_LOG_DIR", str(data_root / "logs" / "service"))
    ).expanduser()

    return RelaymdPaths(
        service_root=service_root,
        data_root=data_root,
        current_link=current_link,
        config_dir=config_dir,
        yaml_config=yaml_config,
        env_file=env_file,
        status_file=status_file,
        service_log_dir=service_log_dir,
        orchestrator_wrapper_log=Path(
            env.get(
                "ORCHESTRATOR_WRAPPER_LOG",
                str(service_log_dir / "orchestrator-wrapper.log"),
            )
        ).expanduser(),
        proxy_wrapper_log=Path(
            env.get("PROXY_WRAPPER_LOG", str(service_log_dir / "proxy-wrapper.log"))
        ).expanduser(),
        current_release=current_link,
        releases_dir=Path(env.get("RELEASES_DIR", str(service_root / "releases"))).expanduser(),
        orchestrator_session=env.get("SESSION_NAME", "relaymd-service"),
        proxy_session=env.get("PROXY_SESSION_NAME", "relaymd-service-proxy"),
        orchestrator_port=env.get("ORCHESTRATOR_PORT", DEFAULT_ORCHESTRATOR_PORT),
        proxy_port=env.get("PROXY_PORT", DEFAULT_PROXY_PORT),
        primary_host=env.get("RELAYMD_PRIMARY_HOST", ""),
    )


def named_path(name: str) -> Path:
    paths = resolve_paths()
    mapping = {
        "data": paths.data_root,
        "config": paths.config_dir,
        "logs": paths.data_root / "logs",
        "status": paths.status_file,
        "current": paths.current_link,
        "release": paths.current_release,
        "env": paths.env_file,
        "yaml": paths.yaml_config,
    }
    return mapping[name]
