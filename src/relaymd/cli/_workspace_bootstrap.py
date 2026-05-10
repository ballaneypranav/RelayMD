from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_workspace_imports() -> None:
    """Allow CLI execution from a workspace checkout without separate package installs."""
    module_path = Path(__file__).resolve()
    workspace_root = next(
        (parent for parent in module_path.parents if (parent / "packages").is_dir()),
        None,
    )
    if workspace_root is None:
        return

    for package_src in (
        workspace_root / "packages" / "relaymd-api-client" / "src",
        workspace_root / "packages" / "relaymd-core" / "src",
    ):
        if package_src.is_dir():
            src = str(package_src)
            if src not in sys.path:
                sys.path.insert(0, src)


_bootstrap_workspace_imports()
