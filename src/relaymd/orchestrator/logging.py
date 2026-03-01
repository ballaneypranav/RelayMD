from __future__ import annotations

import logging
import sys
from typing import Any, Protocol

import orjson
import structlog

_CONFIGURED = False


class _LoggingSettingsProtocol(Protocol):
    @property
    def relaymd_env(self) -> str: ...

    @property
    def relaymd_log_level(self) -> str: ...

    @property
    def relaymd_log_format(self) -> str: ...

    @property
    def axiom_token(self) -> str | None: ...

    @property
    def axiom_dataset(self) -> str: ...


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

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if getattr(settings, "axiom_token", None):
        from relaymd.axiom_logging import AxiomProcessor

        processors.append(
            AxiomProcessor(
                axiom_token=settings.axiom_token,  # type: ignore[attr-defined]
                dataset=settings.axiom_dataset,  # type: ignore[attr-defined]
            )
        )

    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(_log_level(settings)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
