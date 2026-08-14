"""Cross-process run lease contracts for bounded continuous engineering execution."""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Protocol


class RunLease(Protocol):
    """Minimal exclusive-run contract consumed by ContinuousEngineeringPipeline."""

    def acquire(self) -> None: ...

    def release(self) -> None: ...

    def __enter__(self) -> RunLease: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class UpgradeRunLeaseError(RuntimeError):
    """Raised when a continuous engineering run cannot safely acquire its lease."""


class UpgradeRunLease:
    """Exclusive filesystem lease that prevents overlapping upgrade runners.

    Acquisition uses O_EXCL, so only one process can create the lease. The lease
    is intentionally fail-closed: an existing lease is never silently stolen.
    A bounded wait may be configured for callers that expect a short overlap.
    """

    def __init__(self, path: str | Path, *, wait_seconds: float = 0.0, poll_seconds: float = 0.1) -> None:
        self.path = Path(path)
        self.wait_seconds = float(wait_seconds)
        self.poll_seconds = float(poll_seconds)
        self._token = uuid.uuid4().hex
        self._acquired = False
        if self.wait_seconds < 0:
            raise ValueError("wait_seconds must be >= 0")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be > 0")

    def acquire(self) -> None:
        deadline = time.monotonic() + self.wait_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "token": self._token,
                    "created_at": time.time(),
                },
                sort_keys=True,
            )
            + "\n"
        )
        while True:
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    try:
                        os.write(fd, payload.encode("utf-8"))
                        os.fsync(fd)
                    except OSError:
                        try:
                            self.path.unlink()
                        except OSError:
                            pass
                        raise
                finally:
                    os.close(fd)
                self._acquired = True
                return
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise UpgradeRunLeaseError(f"upgrade run lease already held: {self.path}") from exc
                time.sleep(min(self.poll_seconds, max(0.0, deadline - time.monotonic())))
            except OSError as exc:
                raise UpgradeRunLeaseError(f"unable to acquire upgrade run lease: {exc}") from exc

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("token") != self._token:
                raise UpgradeRunLeaseError("upgrade run lease ownership changed before release")
            self.path.unlink()
            self._acquired = False
        except (OSError, json.JSONDecodeError) as exc:
            raise UpgradeRunLeaseError(f"unable to release upgrade run lease: {exc}") from exc

    def __enter__(self) -> UpgradeRunLease:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
