from __future__ import annotations

from pathlib import Path

_GH_API_PAGINATED_ENDPOINTS = 2


def test_latest_fallback_paginates_named_worker_image_versions() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "deploy" / "hpc" / "relaymd-service-pull").read_text()

    assert script.count("gh api --paginate") == _GH_API_PAGINATED_ENDPOINTS
    assert "versions?per_page=100" in script
