from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from relaymd.orchestrator import __version__
from relaymd.orchestrator.background_scheduler import build_background_scheduler
from relaymd.orchestrator.config import OrchestratorSettings, load_settings
from relaymd.orchestrator.db import create_db_and_tables, dispose_engine, init_engine
from relaymd.orchestrator.logging import configure_logging, get_logger
from relaymd.orchestrator.routers.config import router as config_router
from relaymd.orchestrator.routers.jobs_operator import router as jobs_operator_router
from relaymd.orchestrator.routers.jobs_worker import router as jobs_worker_router
from relaymd.orchestrator.routers.workers import router as workers_router

LOG = get_logger(__name__)


async def _ensure_tailscale_running(
    settings: OrchestratorSettings,
) -> asyncio.subprocess.Process | None:
    """Ensure tailscale is connected, starting tailscaled if needed.

    Returns the tailscaled subprocess if we started it (caller must stop it
    on shutdown), or None if it was already running.
    Calls os._exit(1) on any unrecoverable failure.
    """
    if await _check_tailscale_warning(settings.tailscale_socket) is None:
        LOG.info("tailscale_already_running")
        return None

    if not settings.tailscale_auth_key.strip():
        msg = (
            f"Tailscale is not running (socket: {settings.tailscale_socket}) "
            "and no TAILSCALE_AUTH_KEY is configured. "
            "Start tailscaled manually before starting the orchestrator."
        )
        LOG.error("tailscale_not_running", message=msg)
        print(f"\nFATAL: {msg}\n", file=sys.stderr)
        os._exit(1)

    socket_path = str(Path(settings.tailscale_socket).expanduser())
    state_dir = str(Path(socket_path).parent)
    Path(state_dir).mkdir(parents=True, exist_ok=True)

    LOG.info("tailscale_starting", socket=socket_path, state_dir=state_dir)
    tailscaled_proc = await asyncio.create_subprocess_exec(
        "tailscaled",
        "--tun=userspace-networking",
        f"--socket={socket_path}",
        f"--statedir={state_dir}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.sleep(1)

    up_proc = await asyncio.create_subprocess_exec(
        "tailscale",
        f"--socket={socket_path}",
        "up",
        f"--authkey={settings.tailscale_auth_key}",
        f"--hostname={settings.tailscale_hostname}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(up_proc.communicate(), timeout=30)
    except TimeoutError:
        tailscaled_proc.terminate()
        print("\nFATAL: 'tailscale up' timed out after 30s.\n", file=sys.stderr)
        os._exit(1)

    if up_proc.returncode != 0:
        tailscaled_proc.terminate()
        detail = stderr.decode(errors="replace").strip()
        print(f"\nFATAL: 'tailscale up' failed: {detail}\n", file=sys.stderr)
        os._exit(1)

    for attempt in range(15):
        await asyncio.sleep(2)
        if await _check_tailscale_warning(settings.tailscale_socket) is None:
            LOG.info("tailscale_connected", attempts=attempt + 1)
            return tailscaled_proc

    tailscaled_proc.terminate()
    print("\nFATAL: Tailscale did not reach Running state within 30s.\n", file=sys.stderr)
    os._exit(1)


async def _check_tailscale_warning(socket_path: str) -> str | None:
    """Return a warning string if tailscaled is not reachable or not connected."""
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
            return (
                f"tailscaled is not responding at {expanded}. "
                "Workers will be unable to reach the orchestrator via Tailscale."
            )
    except FileNotFoundError:
        return "tailscale binary not found; Tailscale connectivity cannot be verified."
    except OSError as exc:
        return (
            f"tailscaled is not responding at {expanded}: {exc}. "
            "Workers will be unable to reach the orchestrator via Tailscale."
        )

    # Non-zero exit or empty stdout means the daemon isn't running.
    if proc.returncode != 0 or not stdout.strip():
        detail = stderr.decode(errors="replace").strip() if stderr else "no output"
        return (
            f"tailscaled is not running (socket: {expanded}): {detail}. "
            "Workers will be unable to reach the orchestrator via Tailscale."
        )

    try:
        data = json.loads(stdout)
    except (ValueError, UnicodeDecodeError):
        return (
            f"tailscale status returned unexpected output (socket: {expanded}): "
            f"{stdout[:200].decode(errors='replace')!r}"
        )

    backend_state = data.get("BackendState", "")
    if backend_state != "Running":
        return (
            f"Tailscale is not connected (BackendState={backend_state!r}). "
            "Workers will be unable to reach the orchestrator via Tailscale."
        )
    return None


async def _get_tailscale_status(socket_path: str) -> dict[str, Any]:
    """Return a dict describing the current Tailscale connection state."""
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
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"connected": False, "error": "tailscaled not responding"}
    except (FileNotFoundError, OSError) as exc:
        return {"connected": False, "error": str(exc)}

    if proc.returncode != 0 or not stdout.strip():
        return {"connected": False, "error": "tailscaled not running"}

    try:
        data = json.loads(stdout)
    except (ValueError, UnicodeDecodeError):
        return {"connected": False, "error": "unexpected output"}

    if data.get("BackendState") != "Running":
        return {"connected": False, "error": f"BackendState={data.get('BackendState')!r}"}

    self_node = data.get("Self", {})
    ips: list[str] = self_node.get("TailscaleIPs", [])
    return {
        "connected": True,
        "hostname": self_node.get("HostName", ""),
        "dns_name": self_node.get("DNSName", "").rstrip("."),
        "ips": ips,
        "ip": ips[0] if ips else "",
    }


def _check_for_warnings(settings: OrchestratorSettings) -> list[str]:
    warnings = []
    if not settings.infisical_token.strip():
        has_slurm = len(settings.slurm_cluster_configs) > 0
        has_salad = bool(
            settings.salad_api_key
            and settings.salad_org
            and settings.salad_project
            and settings.salad_container_group
        )
        if has_slurm or has_salad:
            warn_msg = (
                "INFISICAL_TOKEN is missing. Automatic worker provisioning "
                "(SLURM/Salad) requires an Infisical token. Terminating."
            )
            LOG.error("missing_infisical_token", message=warn_msg)
            print(f"\nFATAL: {warn_msg}\n", file=sys.stderr)
            sys.exit(1)
    return warnings


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: OrchestratorSettings = app.state.settings
    LOG.info("orchestrator_starting")

    if settings.slurm_cluster_configs or bool(
        settings.salad_api_key
        and settings.salad_org
        and settings.salad_project
        and settings.salad_container_group
    ):
        has_provisioning = True
    else:
        has_provisioning = False

    tailscaled_proc: asyncio.subprocess.Process | None = None
    if has_provisioning:
        tailscaled_proc = await _ensure_tailscale_running(settings)

    init_engine(settings.database_url)
    await create_db_and_tables()

    app.state.scheduler = None
    if app.state.start_background_tasks:
        scheduler = build_background_scheduler(settings)
        scheduler.start()
        app.state.scheduler = scheduler

    try:
        yield
    finally:
        LOG.info("orchestrator_stopping")
        scheduler: AsyncIOScheduler | None = app.state.scheduler
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await dispose_engine()
        if tailscaled_proc is not None and tailscaled_proc.returncode is None:
            LOG.info("tailscale_stopping")
            tailscaled_proc.terminate()
            try:
                await asyncio.wait_for(tailscaled_proc.wait(), timeout=5)
            except TimeoutError:
                tailscaled_proc.kill()


def create_app(
    settings: OrchestratorSettings | None = None,
    *,
    start_background_tasks: bool = True,
) -> FastAPI:
    active_settings = settings or load_settings()
    configure_logging(active_settings)
    config_paths = OrchestratorSettings.config_paths()
    LOG.info(
        "orchestrator_config_yaml",
        paths=[str(path) for path in config_paths],
        loaded=[path.is_file() for path in config_paths],
    )
    app = FastAPI(lifespan=app_lifespan)
    app.state.settings = active_settings
    app.state.start_background_tasks = start_background_tasks
    app.state.warnings = _check_for_warnings(active_settings)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        warnings = list(app.state.warnings)
        ts_warning = await _check_tailscale_warning(app.state.settings.tailscale_socket)
        if ts_warning is not None:
            warnings.append(ts_warning)
        ts_status = await _get_tailscale_status(app.state.settings.tailscale_socket)
        return {
            "status": "ok",
            "version": __version__,
            "warnings": warnings,
            "tailscale": ts_status,
        }

    app.include_router(workers_router)
    app.include_router(jobs_worker_router)
    app.include_router(jobs_operator_router)
    app.include_router(config_router)

    return app


def start() -> None:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        uvicorn.main(
            args=["relaymd.orchestrator.main:create_app", "--factory", *sys.argv[1:]],
            prog_name="relaymd-orchestrator",
        )
        return
    uvicorn.run("relaymd.orchestrator.main:create_app", factory=True, host="0.0.0.0", port=36158)
