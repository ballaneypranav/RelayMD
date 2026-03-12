from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from relaymd.orchestrator import logging as orchestrator_logging
from relaymd.orchestrator.logging import _JsonFileProcessor


@dataclass
class _TestLoggingSettings:
    relaymd_env: str
    relaymd_log_level: str
    relaymd_log_format: str
    axiom_token: str
    axiom_dataset: str
    log_directory: str | None


def test_json_file_processor_appends_json_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "orchestrator.log.jsonl"
    processor = _JsonFileProcessor(log_path)

    processor(None, "info", {"event": "first", "value": 1})
    processor(None, "info", {"event": "second", "value": 2})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"event": "first", "value": 1}
    assert json.loads(lines[1]) == {"event": "second", "value": 2}


def test_configure_logging_strips_log_directory_before_path_build(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, Path] = {}

    class DummyJsonFileProcessor:
        def __init__(self, file_path: Path) -> None:
            captured["file_path"] = file_path

        def __call__(self, _logger, _method_name, event_dict):
            return event_dict

    class DummyAxiomProcessor:
        def __init__(self, *, axiom_token: str, dataset: str) -> None:
            _ = (axiom_token, dataset)

        def __call__(self, _logger, _method_name, event_dict):
            return event_dict

    orchestrator_logging._CONFIGURED = False
    monkeypatch.setattr(orchestrator_logging, "_JsonFileProcessor", DummyJsonFileProcessor)
    monkeypatch.setattr("relaymd.axiom_logging.AxiomProcessor", DummyAxiomProcessor)
    monkeypatch.setattr(orchestrator_logging.structlog, "configure", lambda **_: None)

    settings = _TestLoggingSettings(
        relaymd_env="production",
        relaymd_log_level="INFO",
        relaymd_log_format="json",
        axiom_token="test-token",
        axiom_dataset="relaymd",
        log_directory=f"  {tmp_path}  ",
    )

    orchestrator_logging.configure_logging(settings)

    assert captured["file_path"] == tmp_path / "orchestrator.log.jsonl"
    orchestrator_logging._CONFIGURED = False
