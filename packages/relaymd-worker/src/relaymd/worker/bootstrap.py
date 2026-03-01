from __future__ import annotations

import atexit
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from infisical_client import ClientSettings, InfisicalClient
from infisical_client.schemas import GetSecretOptions
from pydantic import BaseModel

from relaymd.worker.logging import get_logger

INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "prod"
INFISICAL_SECRET_PATH = "/RelayMD"

TAILSCALE_RUNTIME_ROOT_ENV_VAR = "RELAYMD_TAILSCALE_RUNTIME_ROOT"
TAILSCALE_RUNTIME_DIR_ENV_VAR = "RELAYMD_TAILSCALE_RUNTIME_DIR"
TAILSCALE_SOCKET_ENV_VAR = "RELAYMD_TAILSCALE_SOCKET"
TAILSCALE_STATE_DIR_ENV_VAR = "RELAYMD_TAILSCALE_STATE_DIR"
TAILSCALE_SOCKS5_PORT_ENV_VAR = "RELAYMD_TAILSCALE_SOCKS5_PORT"
TAILSCALE_SOCKS5_LISTEN_ADDR_ENV_VAR = "RELAYMD_TAILSCALE_SOCKS5_LISTEN_ADDR"
TAILSCALE_SOCKS5_PROXY_URL_ENV_VAR = "RELAYMD_TAILSCALE_SOCKS5_PROXY_URL"

TAILSCALE_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "relaymd-tailscale"
TAILSCALE_RUNTIME_DIR = str(TAILSCALE_RUNTIME_ROOT / f"{os.getuid()}-{os.getpid()}")
TAILSCALE_SOCKET = str(Path(TAILSCALE_RUNTIME_DIR) / "tailscaled.sock")
TAILSCALE_STATE_DIR = str(Path(TAILSCALE_RUNTIME_DIR) / "state")
TAILSCALE_SOCKS5_PROXY_LISTEN_ADDR = "localhost:1055"
TAILSCALE_SOCKS5_PROXY_URL = f"socks5://{TAILSCALE_SOCKS5_PROXY_LISTEN_ADDR}"

LOG = get_logger(__name__)
_TAILSCALED_PROCESS: subprocess.Popen[bytes] | None = None
_TAILSCALE_RUNTIME_DIR_PATH: Path | None = None
_TAILSCALE_CLEANUP_REGISTERED = False


class WorkerConfig(BaseModel):
    b2_application_key_id: str
    b2_application_key: str
    b2_endpoint: str
    bucket_name: str
    download_bearer_token: str = ""
    tailscale_auth_key: str
    relaymd_api_token: str
    relaymd_orchestrator_url: str


def _runtime_root() -> Path:
    if env_value := os.getenv(TAILSCALE_RUNTIME_ROOT_ENV_VAR):
        return Path(env_value).expanduser()
    return TAILSCALE_RUNTIME_ROOT


def _runtime_dir() -> Path:
    if env_value := os.getenv(TAILSCALE_RUNTIME_DIR_ENV_VAR):
        return Path(env_value).expanduser()
    return _runtime_root() / f"{os.getuid()}-{os.getpid()}"


def tailscale_socket_path() -> str:
    if env_value := os.getenv(TAILSCALE_SOCKET_ENV_VAR):
        return str(Path(env_value).expanduser())
    return str(_runtime_dir() / "tailscaled.sock")


def tailscale_state_dir_path() -> str:
    if env_value := os.getenv(TAILSCALE_STATE_DIR_ENV_VAR):
        return str(Path(env_value).expanduser())
    return str(_runtime_dir() / "state")


def tailscale_socks5_listen_addr() -> str:
    if env_value := os.getenv(TAILSCALE_SOCKS5_LISTEN_ADDR_ENV_VAR):
        return env_value
    if env_value := os.getenv(TAILSCALE_SOCKS5_PORT_ENV_VAR):
        return f"localhost:{int(env_value)}"
    return TAILSCALE_SOCKS5_PROXY_LISTEN_ADDR


def tailscale_socks5_proxy_url() -> str:
    if env_value := os.getenv(TAILSCALE_SOCKS5_PROXY_URL_ENV_VAR):
        return env_value
    return f"socks5://{tailscale_socks5_listen_addr()}"


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_cmdline_contains(pid: int, token: str) -> bool:
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_text(encoding="utf-8")
    except OSError:
        return False
    return token in cmdline


def _stop_pid(pid: int) -> None:
    if not _pid_is_running(pid):
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    for _ in range(10):
        if not _pid_is_running(pid):
            return
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return


def _cleanup_stale_tailscaled(candidate_runtime_dir: Path) -> None:
    pid_file = candidate_runtime_dir / "tailscaled.pid"
    if not pid_file.exists():
        return

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return

    if not _process_cmdline_contains(pid, "tailscaled"):
        return

    _stop_pid(pid)


def _cleanup_stale_runtime_dirs(runtime_root: Path) -> None:
    try:
        if not runtime_root.exists():
            return
    except OSError:
        return

    uid_prefix = f"{os.getuid()}-"
    current_pid = os.getpid()

    try:
        entries = list(runtime_root.iterdir())
    except OSError:
        return

    for candidate in entries:
        try:
            is_dir = candidate.is_dir()
        except OSError:
            continue
        if not is_dir or not candidate.name.startswith(uid_prefix):
            continue
        pid_text = candidate.name[len(uid_prefix) :]
        if not pid_text.isdigit():
            continue

        pid = int(pid_text)
        if pid == current_pid or _pid_is_running(pid):
            continue

        _cleanup_stale_tailscaled(candidate)
        shutil.rmtree(candidate, ignore_errors=True)


def _find_available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_socks5_ready(
    listen_addr: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.25,
) -> None:
    """Block until the SOCKS5 proxy port accepts TCP connections."""
    host, _, port_str = listen_addr.rpartition(":")
    host = host or "localhost"
    port = int(port_str)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Tailscale SOCKS5 proxy at {listen_addr} did not become ready "
                f"within {timeout_seconds:.0f}s"
            )
        time.sleep(poll_interval_seconds)


def _wait_for_tailscale_running(
    socket_path: str,
    *,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 1.0,
) -> None:
    """Block until tailscale reports BackendState == 'Running'.

    The SOCKS5 port being open only means tailscaled is accepting connections;
    it does not mean the tailnet peer routes are established.  Polling
    ``tailscale status --json`` for BackendState == 'Running' ensures the node
    is fully authenticated and route advertisements have been received before
    the worker attempts to connect to the orchestrator.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Tailscale did not reach Running state within {timeout_seconds:.0f}s"
            )
        # Cap the per-call timeout so a hung process doesn't outlive the deadline.
        call_timeout = min(remaining, max(poll_interval_seconds * 2, 5.0))
        try:
            result = subprocess.run(  # noqa: S603
                ["tailscale", f"--socket={socket_path}", "status", "--json"],
                capture_output=True,
                text=True,
                check=False,
                timeout=call_timeout,
            )
        except subprocess.TimeoutExpired:
            pass
        else:
            if result.returncode == 0:
                try:
                    status = json.loads(result.stdout)
                    if status.get("BackendState") == "Running":
                        return
                except (ValueError, KeyError):
                    pass
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Tailscale did not reach Running state within {timeout_seconds:.0f}s"
            )
        time.sleep(poll_interval_seconds)


def _wait_for_peer_reachable(
    peer_ip: str,
    socket_path: str,
    *,
    timeout_seconds: float = 15.0,
) -> None:
    """Attempt to drive the WireGuard handshake for *peer_ip* to completion.

    In userspace-networking mode Tailscale establishes WireGuard sessions
    lazily on first contact.  Without priming the route, the SOCKS5 proxy may
    return ``General SOCKS server failure`` (0x01) if the worker tries to reach
    the orchestrator before the handshake completes.

    This is intentionally best-effort: if the ping times out or reports
    ``no reply`` (e.g. because the orchestrator is not currently on the
    tailnet), a warning is logged and execution continues.  The gateway retry
    loop will then surface a clear "failed to register after N attempts" error
    rather than failing here with a low-level tailscale message.
    """
    try:
        result = subprocess.run(  # noqa: S603
            [
                "tailscale",
                f"--socket={socket_path}",
                "ping",
                f"--timeout={int(timeout_seconds)}s",
                "--c=1",
                peer_ip,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds + 5.0,
        )
        if result.returncode != 0:
            # "no reply" means the peer is not (yet) on the tailnet — the
            # orchestrator may be starting up or temporarily unreachable.
            # Log and proceed; the gateway will retry the actual connection.
            LOG.warning(
                "tailscale_peer_ping_failed",
                peer_ip=peer_ip,
                output=(result.stderr.strip() or result.stdout.strip()),
            )
        else:
            LOG.info("tailscale_peer_reachable", peer_ip=peer_ip)
    except subprocess.TimeoutExpired:
        LOG.warning(
            "tailscale_peer_ping_timeout",
            peer_ip=peer_ip,
            timeout_seconds=timeout_seconds,
        )


def _initialize_tailscale_runtime() -> Path:
    runtime_dir = _runtime_dir()
    managed_runtime_root = _runtime_root()
    managed_runtime_root.mkdir(parents=True, exist_ok=True)
    if runtime_dir.parent == managed_runtime_root:
        _cleanup_stale_runtime_dirs(managed_runtime_root)

    runtime_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault(TAILSCALE_RUNTIME_DIR_ENV_VAR, str(runtime_dir))
    os.environ.setdefault(TAILSCALE_SOCKET_ENV_VAR, str(runtime_dir / "tailscaled.sock"))
    os.environ.setdefault(TAILSCALE_STATE_DIR_ENV_VAR, str(runtime_dir / "state"))

    if (
        os.getenv(TAILSCALE_SOCKS5_PORT_ENV_VAR) is None
        and os.getenv(TAILSCALE_SOCKS5_LISTEN_ADDR_ENV_VAR) is None
        and os.getenv(TAILSCALE_SOCKS5_PROXY_URL_ENV_VAR) is None
    ):
        os.environ[TAILSCALE_SOCKS5_PORT_ENV_VAR] = str(_find_available_local_port())

    os.environ.setdefault(TAILSCALE_SOCKS5_LISTEN_ADDR_ENV_VAR, tailscale_socks5_listen_addr())
    os.environ.setdefault(TAILSCALE_SOCKS5_PROXY_URL_ENV_VAR, tailscale_socks5_proxy_url())

    return runtime_dir


def _stop_tailscaled_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _cleanup_tailscale_runtime() -> None:
    global _TAILSCALED_PROCESS
    global _TAILSCALE_RUNTIME_DIR_PATH

    process = _TAILSCALED_PROCESS
    _TAILSCALED_PROCESS = None
    if process is not None:
        try:
            _stop_tailscaled_process(process)
        except Exception:  # noqa: BLE001
            LOG.warning("tailscaled_cleanup_failed", exc_info=True)

    runtime_dir = _TAILSCALE_RUNTIME_DIR_PATH
    _TAILSCALE_RUNTIME_DIR_PATH = None
    if runtime_dir is not None:
        shutil.rmtree(runtime_dir, ignore_errors=True)


def _register_cleanup_handler() -> None:
    global _TAILSCALE_CLEANUP_REGISTERED
    if _TAILSCALE_CLEANUP_REGISTERED:
        return

    atexit.register(_cleanup_tailscale_runtime)
    _TAILSCALE_CLEANUP_REGISTERED = True


def _parse_infisical_machine_token(raw_token: str | None) -> tuple[str, str]:
    if not raw_token:
        raise RuntimeError(
            "INFISICAL_TOKEN is required and must be in the format <client_id>:<client_secret>"
        )

    if ":" not in raw_token:
        raise RuntimeError(
            "INFISICAL_TOKEN is malformed; expected format <client_id>:<client_secret>"
        )

    client_id, client_secret = raw_token.split(":", 1)
    if not client_id or not client_secret:
        raise RuntimeError(
            "INFISICAL_TOKEN is malformed; expected non-empty <client_id>:<client_secret>"
        )
    return client_id, client_secret


def join_tailnet(auth_key: str, hostname: str) -> None:
    global _TAILSCALED_PROCESS
    global _TAILSCALE_RUNTIME_DIR_PATH

    if _TAILSCALED_PROCESS is not None and _TAILSCALED_PROCESS.poll() is None:
        _cleanup_tailscale_runtime()

    runtime_dir = _initialize_tailscale_runtime()
    state_dir = Path(tailscale_state_dir_path())
    state_dir.mkdir(parents=True, exist_ok=True)
    socket_path = tailscale_socket_path()
    socks5_listen_addr = tailscale_socks5_listen_addr()

    # In userspace mode, explicit SOCKS5 listener configuration guarantees proxy
    # availability for app traffic that must traverse the tailnet.
    tailscaled_process = subprocess.Popen(  # noqa: S603
        [
            "tailscaled",
            "--tun=userspace-networking",
            f"--socks5-server={socks5_listen_addr}",
            f"--statedir={state_dir}",
            f"--socket={socket_path}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (runtime_dir / "tailscaled.pid").write_text(f"{tailscaled_process.pid}\n", encoding="utf-8")

    time.sleep(0.2)
    exit_code = tailscaled_process.poll()
    if exit_code is not None and exit_code != 0:
        raise RuntimeError(f"tailscaled failed to start (exit code {exit_code})")

    tailscale_up = subprocess.run(  # noqa: S603
        [
            "tailscale",
            f"--socket={socket_path}",
            "up",
            f"--authkey={auth_key}",
            f"--hostname={hostname}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if tailscale_up.returncode != 0:
        _stop_tailscaled_process(tailscaled_process)
        shutil.rmtree(runtime_dir, ignore_errors=True)
        raise RuntimeError(
            "tailscale up failed with exit code "
            f"{tailscale_up.returncode}: {tailscale_up.stderr.strip()}"
        )

    try:
        _wait_for_socks5_ready(socks5_listen_addr)
        _wait_for_tailscale_running(socket_path)
    except Exception:
        _stop_tailscaled_process(tailscaled_process)
        shutil.rmtree(runtime_dir, ignore_errors=True)
        raise

    _TAILSCALED_PROCESS = tailscaled_process
    _TAILSCALE_RUNTIME_DIR_PATH = runtime_dir
    _register_cleanup_handler()


def run_bootstrap() -> WorkerConfig:
    machine_token = os.getenv("INFISICAL_TOKEN")
    client_id, client_secret = _parse_infisical_machine_token(machine_token)

    try:
        client = InfisicalClient(
            settings=ClientSettings(
                client_id=client_id,
                client_secret=client_secret,
                site_url=INFISICAL_BASE_URL,
            )
        )

        def get(name: str) -> str:
            return client.getSecret(
                GetSecretOptions(
                    secret_name=name,
                    project_id=INFISICAL_WORKSPACE_ID,
                    environment=INFISICAL_ENVIRONMENT,
                    path=INFISICAL_SECRET_PATH,
                )
            ).secret_value

        def get_optional(name: str) -> str:
            try:
                return get(name)
            except Exception:  # noqa: BLE001
                return ""

        config = WorkerConfig(
            b2_application_key_id=get("B2_APPLICATION_KEY_ID"),
            b2_application_key=get("B2_APPLICATION_KEY"),
            b2_endpoint=get("B2_ENDPOINT"),
            bucket_name=get("BUCKET_NAME"),
            download_bearer_token=get_optional("DOWNLOAD_BEARER_TOKEN"),
            tailscale_auth_key=get("TAILSCALE_AUTH_KEY"),
            relaymd_api_token=get("RELAYMD_API_TOKEN"),
            relaymd_orchestrator_url=get("RELAYMD_ORCHESTRATOR_URL"),
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to bootstrap worker from Infisical") from exc

    hostname = os.getenv("HOSTNAME", "relaymd-worker")
    join_tailnet(config.tailscale_auth_key, hostname)

    orchestrator_host = urlparse(config.relaymd_orchestrator_url).hostname or ""
    if orchestrator_host:
        LOG.info(
            "tailscale_waiting_for_peer",
            peer_ip=orchestrator_host,
            tailscale_socket=tailscale_socket_path(),
        )
        _wait_for_peer_reachable(orchestrator_host, tailscale_socket_path())

    LOG.info(
        "tailscale_userspace_proxy_ready",
        socks5_proxy_url=tailscale_socks5_proxy_url(),
        tailscale_socket=tailscale_socket_path(),
    )
    return config
