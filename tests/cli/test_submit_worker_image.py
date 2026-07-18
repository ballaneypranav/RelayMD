from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import typer

from relaymd.cli.commands import submit as submit_cmd


def test_submit_rejects_blank_worker_image_before_catalog_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "relaymd-worker.json").write_text('{"command": "run"}\n', encoding="utf-8")

    class FakeSubmitService:
        def __init__(self, context: object) -> None:
            _ = context

        def known_cluster_names(self) -> set[str]:
            return set()

    monkeypatch.setattr(submit_cmd, "SubmitService", FakeSubmitService)
    monkeypatch.setattr(submit_cmd, "create_cli_context", Mock(return_value=object()))
    catalog_lookup = Mock(side_effect=AssertionError("catalog lookup must not run"))
    monkeypatch.setattr(submit_cmd, "_catalog_for_explicit_worker_image", catalog_lookup)

    with pytest.raises(typer.Exit) as exc:
        submit_cmd.submit(input_dir=input_dir, title="blank-image", worker_image=" \t ")

    assert exc.value.exit_code == 1
    catalog_lookup.assert_not_called()
