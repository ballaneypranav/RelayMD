from __future__ import annotations

import logging
import sys
from typing import Any, Literal

import orjson
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIGURED = False


class LoggingSettings(BaseSettings):
    relaymd_env: Literal["development", "production"] = "production"
    relaymd_log_level: str = "INFO"
    relaymd_log_format: Literal["auto", "json", "console"] = "auto"

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


def _orjson_dumps(event_dict: dict[str, Any], **_: Any) -> str:
    return orjson.dumps(event_dict).decode("utf-8")


def _log_level(settings: LoggingSettings) -> int:
    return logging.getLevelNamesMapping().get(
        settings.relaymd_log_level.upper(),
        logging.INFO,
    )


def configure_logging(settings: LoggingSettings | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    active_settings = settings or LoggingSettings()
    renderer: structlog.types.Processor
    if active_settings.relaymd_log_format == "console" or (
        active_settings.relaymd_log_format == "auto"
        and active_settings.relaymd_env == "development"
    ):
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer(serializer=_orjson_dumps)

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if getattr(active_settings, "axiom_token", None):
        from relaymd.axiom_logging import AxiomProcessor

        processors.append(
            AxiomProcessor(
                axiom_token=active_settings.axiom_token,  # type: ignore[attr-defined]
                dataset=active_settings.axiom_dataset,  # type: ignore[attr-defined]
            )
        )

    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(_log_level(active_settings)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> structlog.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
