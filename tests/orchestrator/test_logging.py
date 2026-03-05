from __future__ import annotations

import json
from pathlib import Path

from relaymd.orchestrator.logging import _JsonFileProcessor


def test_json_file_processor_appends_json_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "orchestrator.log.jsonl"
    processor = _JsonFileProcessor(log_path)

    processor(None, "info", {"event": "first", "value": 1})
    processor(None, "info", {"event": "second", "value": 2})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"event": "first", "value": 1}
    assert json.loads(lines[1]) == {"event": "second", "value": 2}
