from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, EnvSettingsSource, YamlConfigSettingsSource
from pydantic_settings.sources import DefaultSettingsSource, PydanticBaseSettingsSource

DEFAULT_RELAYMD_CONFIG_ENV_VAR = "RELAYMD_CONFIG"
DEFAULT_RELAYMD_DATA_ROOT_ENV_VAR = "RELAYMD_DATA_ROOT"


def relaymd_config_paths(
    *,
    default_home_config_path: str,
    config_env_var: str = DEFAULT_RELAYMD_CONFIG_ENV_VAR,
    data_root_env_var: str = DEFAULT_RELAYMD_DATA_ROOT_ENV_VAR,
) -> list[Path]:
    if explicit := os.getenv(config_env_var):
        return [Path(explicit).expanduser()]
    if data_root := os.getenv(data_root_env_var):
        return [Path(data_root).expanduser() / "config" / "relaymd-config.yaml"]
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
    env_source = _FilteredEnvSettingsSource(
        settings_cls,
        allowed_fields=set(env_override_map.keys()),
    )
    return (
        init_settings,
        yaml_source,
        env_source,
        DefaultSettingsSource(settings_cls),
    )


class _FilteredEnvSettingsSource(EnvSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings], allowed_fields: set[str]) -> None:
        super().__init__(settings_cls)
        self._allowed_fields = allowed_fields

    def __call__(self) -> dict[str, object]:
        values: dict[str, Any] = {}
        for field_name in self._allowed_fields:
            field = self.settings_cls.model_fields[field_name]
            field_value, _, value_is_complex = self._get_resolved_field_value(field, field_name)
            field_value = self.prepare_field_value(
                field_name,
                field,
                field_value,
                value_is_complex,
            )
            if field_value is not None:
                values[field_name] = field_value
        return values


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
            keys_to_drop = [field_name, *env_keys]
            for config_dict in config_dicts:
                for key in keys_to_drop:
                    config_dict.pop(key, None)
