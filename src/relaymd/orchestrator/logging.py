from __future__ import annotations

import logging
import sys
from typing import Any, Protocol

import orjson
import structlog

_CONFIGURED = False


class _BrokenPipeSafePrintLogger:
    def __init__(self, file) -> None:
        self._logger = structlog.PrintLogger(file=file)

    def __getattr__(self, name: str):
        attr = getattr(self._logger, name)
        if not callable(attr):
            return attr

        def _safe(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            except BrokenPipeError:
                return None

        return _safe


class _BrokenPipeSafePrintLoggerFactory:
    def __init__(self, file) -> None:
        self._file = file

    def __call__(self, *args: Any) -> _BrokenPipeSafePrintLogger:
        _ = args
        return _BrokenPipeSafePrintLogger(file=self._file)


class _LoggingSettingsProtocol(Protocol):
    @property
    def relaymd_env(self) -> str: ...

    @property
    def relaymd_log_level(self) -> str: ...

    @property
    def relaymd_log_format(self) -> str: ...

    @property
    def axiom_token(self) -> str: ...

    @property
    def axiom_dataset(self) -> str: ...


def _orjson_dumps(event_dict: dict[str, Any], **_: Any) -> str:
    return orjson.dumps(event_dict, default=str).decode("utf-8")


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

    axiom_token = settings.axiom_token
    if not axiom_token.strip():
        raise RuntimeError(
            "AXIOM_TOKEN is required but missing or empty. "
            "Ensure it is set via AXIOM_TOKEN env var or Infisical."
        )
    from relaymd.axiom_logging import AxiomProcessor

    processors.append(
        AxiomProcessor(
            axiom_token=axiom_token,
            dataset=settings.axiom_dataset,
        )
    )

    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(_log_level(settings)),
        logger_factory=_BrokenPipeSafePrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
