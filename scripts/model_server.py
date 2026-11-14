"""Multi-sector GGUF model server controller for ZCoder local inference.

Starts/stops/restarts/reports status of llama-server instances, one per
sector, each serving a single GGUF model on a dedicated loopback port.

All traffic stays on loopback (127.0.0.1); no hosted model API is used.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

try:  # PyYAML is available in the project venv.
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover - environment guard
    raise SystemExit(f"PyYAML is required to read the model config: {exc}") from exc

DEFAULT_CONFIG = "/home/cvsz/zcoder/config/models.yaml"
HEALTH_PATH = "/health"


class ModelServerError(RuntimeError):
    """Raised for controllable model-server failures."""


@dataclass(frozen=True)
class Sector:
    name: str
    model: str
    alias: str
    host: str
    port: int
    ctx_size: int
    enabled: bool
    models_dir: str
    binary: str
    run_dir: str
    log_dir: str

    @property
    def model_path(self) -> str:
        return os.path.join(self.models_dir, self.model)

    @property
    def pidfile(self) -> str:
        return os.path.join(self.run_dir, f"{self.name}.pid")

    @property
    def logfile(self) -> str:
        return os.path.join(self.log_dir, f"{self.name}.log")

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ModelServerError(f"Invalid config {path}: expected a mapping")
    return data


def build_sectors(cfg: dict[str, Any]) -> list[Sector]:
    models_dir = str(cfg.get("models_dir", "/zdata/models"))
    binary = str(cfg.get("llama_server_binary", "/home/cvsz/.local/bin/llama-server"))
    run_dir = str(cfg.get("run_dir", "/home/cvsz/zcoder/run"))
    log_dir = str(cfg.get("log_dir", "/home/cvsz/zcoder/logs"))
    default_ctx = int(cfg.get("default_ctx_size", 4096))

    sectors: list[Sector] = []
    for entry in cfg.get("sectors", []) or []:
        name = str(entry["name"])
        sectors.append(
            Sector(
                name=name,
                model=str(entry["model"]),
                alias=str(entry.get("alias", name)),
                host=str(entry.get("host", "127.0.0.1")),
                port=int(entry["port"]),
                ctx_size=int(entry.get("ctx_size", default_ctx)),
                enabled=bool(entry.get("enabled", False)),
                models_dir=models_dir,
                binary=binary,
                run_dir=run_dir,
                log_dir=log_dir,
            )
        )
    return sectors


def sector_by_name(sectors: list[Sector], name: str) -> Sector:
    for sector in sectors:
        if sector.name == name:
            return sector
    raise ModelServerError(f"Unknown sector: {name}. Known: {', '.join(s.name for s in sectors)}")


def resolve_targets(sectors: list[Sector], target: str) -> list[Sector]:
    if target == "all":
        return [s for s in sectors if s.enabled]
    return [sector_by_name(sectors, target)]


def is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_pid(pidfile: str) -> int | None:
    try:
        with open(pidfile, encoding="utf-8") as fh:
            return int(fh.read().strip() or "0")
    except (OSError, ValueError):
        return None


def write_pid(pidfile: str, pid: int) -> None:
    os.makedirs(os.path.dirname(pidfile), exist_ok=True)
    with open(pidfile, "w", encoding="utf-8") as fh:
        fh.write(str(pid))


def remove_pidfile(pidfile: str) -> None:
    try:
        os.remove(pidfile)
    except FileNotFoundError:
        pass


def health_ok(sector: Sector, timeout: float = 3.0) -> bool:
    url = f"{sector.base_url}{HEALTH_PATH}"
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def sector_running(sector: Sector) -> tuple[bool, int | None]:
    """Return (alive, pid). A stale pidfile is cleaned up."""
    pid = read_pid(sector.pidfile)
    if pid is None or pid == 0:
        return False, None
    if is_process_alive(pid):
        return True, pid
    remove_pidfile(sector.pidfile)
    return False, None


def start_sector(sector: Sector, start_timeout: int) -> None:
    running, _pid = sector_running(sector)
    if running:
        print(f"[start] {sector.name}: already running (pid on port {sector.port})")
        return

    if not os.path.exists(sector.binary):
        raise ModelServerError(f"llama-server binary not found: {sector.binary}")
    if not os.path.exists(sector.model_path):
        raise ModelServerError(f"GGUF model not found: {sector.model_path}")

    os.makedirs(sector.run_dir, exist_ok=True)
    os.makedirs(sector.log_dir, exist_ok=True)

    cmd = [
        sector.binary,
        "--model",
        sector.model_path,
        "--alias",
        sector.alias,
        "--host",
        sector.host,
        "--port",
        str(sector.port),
        "--ctx-size",
        str(sector.ctx_size),
        "--threads",
        "-1",
    ]

    log_fh = open(sector.logfile, "ab")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        log_fh.close()

    write_pid(sector.pidfile, proc.pid)

    deadline = time.monotonic() + start_timeout
    while time.monotonic() < deadline:
        alive, _pid = sector_running(sector)
        if not alive:
            raise ModelServerError(f"{sector.name}: llama-server exited during startup; see {sector.logfile}")
        if health_ok(sector, timeout=2.0):
            print(
                f"[start] {sector.name}: running on {sector.base_url} "
                f"(pid {proc.pid}, model {sector.model})"
            )
            return
        time.sleep(1.0)

    raise ModelServerError(f"{sector.name}: did not become healthy within {start_timeout}s")


def stop_sector(sector: Sector, stop_timeout: int) -> None:
    running, pid = sector_running(sector)
    if not running or pid is None:
        print(f"[stop] {sector.name}: not running")
        remove_pidfile(sector.pidfile)
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_pidfile(sector.pidfile)
        print(f"[stop] {sector.name}: already gone")
        return
    except OSError as exc:
        raise ModelServerError(f"{sector.name}: cannot signal pid {pid}: {exc}") from exc

    deadline = time.monotonic() + stop_timeout
    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            remove_pidfile(sector.pidfile)
            print(f"[stop] {sector.name}: stopped (pid {pid})")
            return
        time.sleep(0.5)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise ModelServerError(f"{sector.name}: cannot kill pid {pid}: {exc}") from exc

    remove_pidfile(sector.pidfile)
    print(f"[stop] {sector.name}: killed (pid {pid})")


def restart_sector(sector: Sector, start_timeout: int, stop_timeout: int) -> None:
    stop_sector(sector, stop_timeout)
    start_sector(sector, start_timeout)


def status_sector(sector: Sector) -> str:
    running, pid = sector_running(sector)
    if not running:
        return f"[status] {sector.name}: stopped (port {sector.port})"
    healthy = health_ok(sector, timeout=2.0)
    state = "healthy" if healthy else "unhealthy"
    return f"[status] {sector.name}: running (pid {pid}, port {sector.port}, {state})"


def list_sectors(sectors: list[Sector]) -> None:
    print("Multi-sector GGUF model servers:")
    print(f"{'Sector':<14} {'Model':<26} {'Alias':<22} {'Port':<6} {'Enabled':<8} {'Status'}")
    print("-" * 90)
    for sector in sectors:
        running, _pid = sector_running(sector)
        status = "running" if running else "stopped"
        print(
            f"{sector.name:<14} {sector.model:<26} {sector.alias:<22} "
            f"{sector.port:<6} {str(sector.enabled):<8} {status}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Control ZCoder multi-sector GGUF model servers (llama-server)."
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("ZCODER_MODELS_CONFIG", DEFAULT_CONFIG),
        help="Path to models.yaml config",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in ("start", "stop", "restart", "status", "health"):
        p = sub.add_parser(cmd, help=f"{cmd} a model server sector")
        p.add_argument("target", help="Sector name, or 'all'")

    sub.add_parser("list", help="List configured sectors and their status")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config)
    sectors = build_sectors(cfg)
    start_timeout = int(cfg.get("start_timeout", 120))
    stop_timeout = int(cfg.get("stop_timeout", 15))

    if args.command == "list":
        list_sectors(sectors)
        return 0

    targets = resolve_targets(sectors, args.target)
    if not targets:
        print(f"Nothing to {args.command}: no enabled sectors match '{args.target}'")
        return 0

    failures = 0
    for sector in targets:
        try:
            if args.command == "start":
                start_sector(sector, start_timeout)
            elif args.command == "stop":
                stop_sector(sector, stop_timeout)
            elif args.command == "restart":
                restart_sector(sector, start_timeout, stop_timeout)
            elif args.command == "status":
                print(status_sector(sector))
            elif args.command == "health":
                ok = health_ok(sector, timeout=3.0)
                print(
                    f"[health] {sector.name}: {'OK' if ok else 'FAIL'} " f"({sector.base_url}{HEALTH_PATH})"
                )
                if not ok:
                    failures += 1
        except ModelServerError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
