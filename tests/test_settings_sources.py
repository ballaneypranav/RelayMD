from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from relaymd.settings_sources import _FilteredEnvSettingsSource


class _DummySettings(BaseSettings):
    foo: str = ""
    BAR: str = ""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


def test_filtered_env_settings_source_only_allows_configured_field_names(monkeypatch) -> None:
    monkeypatch.setenv("BAR", "unexpected")
    monkeypatch.setenv("foo", "expected")

    source = _FilteredEnvSettingsSource(_DummySettings, allowed_fields={"foo"})

    assert source() == {"foo": "expected"}
