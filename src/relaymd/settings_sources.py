from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, EnvSettingsSource, YamlConfigSettingsSource
from pydantic_settings.sources import DefaultSettingsSource, PydanticBaseSettingsSource

DEFAULT_RELAYMD_CONFIG_ENV_VAR = "RELAYMD_CONFIG"


def relaymd_config_paths(
    *,
    default_home_config_path: str,
    config_env_var: str = DEFAULT_RELAYMD_CONFIG_ENV_VAR,
) -> list[Path]:
    if explicit := os.getenv(config_env_var):
        return [Path(explicit).expanduser()]
    return [
        Path(default_home_config_path).expanduser(),
        Path.cwd() / "relaymd-config.yaml",
    ]


def relaymd_settings_sources(
    *,
    settings_cls: type[BaseSettings],
    init_settings: PydanticBaseSettingsSource,
    env_override_map: dict[str, tuple[str, ...]],
    config_paths: list[Path],
) -> tuple[PydanticBaseSettingsSource, ...]:
    yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=config_paths)
    _drop_yaml_keys_with_env_overrides(yaml_source=yaml_source, env_override_map=env_override_map)
    return (
        init_settings,
        yaml_source,
        EnvSettingsSource(settings_cls),
        DefaultSettingsSource(settings_cls),
    )


def _drop_yaml_keys_with_env_overrides(
    *,
    yaml_source: YamlConfigSettingsSource,
    env_override_map: dict[str, tuple[str, ...]],
) -> None:
    raw_init_kwargs: object = getattr(yaml_source, "init_kwargs", None)
    if isinstance(raw_init_kwargs, dict):
        config_dicts = [raw_init_kwargs]
    elif isinstance(raw_init_kwargs, list):
        config_dicts = [item for item in raw_init_kwargs if isinstance(item, dict)]
    else:
        config_dicts = []

    for field_name, env_keys in env_override_map.items():
        if any(os.getenv(env_key) is not None for env_key in env_keys):
            for config_dict in config_dicts:
                config_dict.pop(field_name, None)
