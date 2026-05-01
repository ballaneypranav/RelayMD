from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

FALLBACK_VERSION = "0.1.10"


def get_version() -> str:
    try:
        return version("relaymd")
    except PackageNotFoundError:
        return FALLBACK_VERSION


__version__ = get_version()
