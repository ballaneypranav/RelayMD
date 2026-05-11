from __future__ import annotations

from relaymd.axiom_logging import AxiomProcessor


def test_axiom_processor_skips_upload_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_DISABLE_AXIOM_UPLOAD", "1")

    called = {"value": False}

    def _unexpected_get_thread(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("get_axiom_thread should not be called when upload is disabled")

    monkeypatch.setattr("relaymd.axiom_logging.get_axiom_thread", _unexpected_get_thread)

    processor = AxiomProcessor(axiom_token="test-token", dataset="relaymd")
    returned = processor(None, "info", {"event": "hello"})

    assert returned == {"event": "hello"}
    assert called["value"] is False
