from __future__ import annotations

import pytest


class _NoopAxiomThread:
    def enqueue(self, event_dict):  # noqa: ANN001
        _ = event_dict
        return None


@pytest.fixture(autouse=True)
def _disable_axiom_network_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "relaymd.axiom_logging.get_axiom_thread",
        lambda axiom_token, dataset: _NoopAxiomThread(),
    )
