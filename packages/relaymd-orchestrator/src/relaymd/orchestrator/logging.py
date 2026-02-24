from __future__ import annotations

import logging
import sys
from typing import Any, Protocol

import orjson
import structlog

_CONFIGURED = False


class _LoggingSettingsProtocol(Protocol):
    relaymd_env: str
    relaymd_log_level: str
    relaymd_log_format: str


def _orjson_dumps(event_dict: dict[str, Any], **_: Any) -> str:
    return orjson.dumps(event_dict).decode("utf-8")


def _log_level(settings: _LoggingSettingsProtocol) -> int:
    return logging.getLevelNamesMapping().get(
        settings.relaymd_log_level.upper(),
        logging.INFO,
    )


def configure_logging(settings: _LoggingSettingsProtocol) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    renderer: structlog.types.Processor
    if settings.relaymd_log_format == "console" or (
        settings.relaymd_log_format == "auto" and settings.relaymd_env == "development"
    ):
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer(serializer=_orjson_dumps)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_log_level(settings)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
