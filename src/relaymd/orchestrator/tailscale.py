from __future__ import annotations

import asyncio
import json
from pathlib import Path

from relaymd.orchestrator.logging import get_logger

LOG = get_logger(__name__)


async def check_tailscale_running(socket_path: str) -> tuple[bool, str | None]:
    """Check whether tailscaled is running and connected.

    Returns ``(True, None)`` when Tailscale is healthy.
    Returns ``(False, reason)`` with a human-readable reason otherwise.
    """
    expanded = str(Path(socket_path).expanduser())
    try:
        proc = await asyncio.create_subprocess_exec(
            "tailscale",
            f"--socket={expanded}",
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return False, f"tailscaled is not responding at {expanded}"
    except FileNotFoundError:
        return False, "tailscale binary not found"
    except OSError as exc:
        return False, f"tailscaled is not responding at {expanded}: {exc}"

    if proc.returncode != 0 or not stdout.strip():
        detail = stderr.decode(errors="replace").strip() if stderr else "no output"
        return False, f"tailscaled is not running (socket: {expanded}): {detail}"

    try:
        data = json.loads(stdout)
    except (ValueError, UnicodeDecodeError):
        snippet = stdout[:200].decode(errors="replace")
        return False, f"tailscale status returned unexpected output: {snippet!r}"

    backend_state = data.get("BackendState", "")
    if backend_state != "Running":
        return False, f"Tailscale is not connected (BackendState={backend_state!r})"

    return True, None
