"""Build runtime-only ZCoder container configuration from mounted secrets."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote


def configure_database_url(environ: dict[str, str] | None = None) -> str | None:
    """Set DATABASE_URL from the dedicated mounted password file when configured."""
    env = os.environ if environ is None else environ
    existing = env.get("DATABASE_URL", "").strip()
    if existing:
        return existing

    password_file = env.get("ZCODER_POSTGRES_PASSWORD_FILE", "").strip()
    if not password_file:
        return None
    try:
        password = Path(password_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError("ZCoder PostgreSQL secret file is unavailable") from exc
    if re.fullmatch(r"[0-9a-f]{64}", password) is None:
        raise RuntimeError("ZCoder PostgreSQL secret file has an invalid format")

    host = env.get("ZCODER_POSTGRES_HOST", "zpostgresql").strip()
    port = env.get("ZCODER_POSTGRES_PORT", "5432").strip()
    if re.fullmatch(r"[A-Za-z0-9.-]+", host) is None or ".." in host:
        raise RuntimeError("ZCODER_POSTGRES_HOST must be a DNS name or IPv4 address")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RuntimeError("ZCODER_POSTGRES_PORT must be between 1 and 65535")

    database_url = f"postgresql://zcoder:{quote(password, safe='')}@{host}:{int(port)}/zcoder_db"
    env["DATABASE_URL"] = database_url
    return database_url


def main() -> None:
    configure_database_url()
    command = sys.argv[1:]
    if not command:
        raise SystemExit("container entrypoint requires a command")
    os.execvpe(
        command[0], command, os.environ
    )  # nosec B606  # intentional shell-less exec to avoid injection


if __name__ == "__main__":
    main()
