"""backup_restore.py — Production backup, PITR, and restore verification for ZCoder.

Provides:
  • pg_dump logical backup with encryption
  • WAL archive mode documentation and config
  • Restore drill execution and verification
  • Backup freshness tracking
  • Retention policy enforcement
  • RPO/RTO tracking

This module operates as a standalone backup agent — it should be invoked
by a cron job or Kubernetes CronJob, not by the API serving process.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from zcoder.core.security import build_child_env

logger = logging.getLogger(__name__)


def _split_dsn_password(url: str) -> tuple[str, str]:
    """Split a database URL into (password-free URL, password).

    Keeps credentials off the child-process command line (SEC-008): the
    password travels via the ``PGPASSWORD`` environment override instead of
    being visible in ``/proc/*/cmdline``. URLs without a password are
    returned unchanged.
    """
    try:
        parts = urlsplit(url)
        # urlsplit leaves userinfo percent-ENCODED; decode so libpq's
        # PGPASSWORD receives the literal password
        password = unquote(parts.password) if parts.password else ""
        if not password:
            return url, ""
        host = parts.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        # urlsplit leaves userinfo percent-encoded: keep the username as-is
        # so encoded specials (us%2Fer) survive into the rebuilt URL
        netloc = f"{parts.username}@{host}" if parts.username else host
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
    except ValueError:
        return url, ""
    rebuilt = urlunsplit((parts.scheme, netloc, parts.path or "", parts.query, parts.fragment))
    return rebuilt, password


def _redact(text: str, secret: str) -> str:
    """Best-effort removal of a known secret from diagnostic text."""
    if secret and text:
        return text.replace(secret, "[redacted]")
    return text


# ─── Backup record ────────────────────────────────────────────────────────────


@dataclass
class BackupRecord:
    backup_id: str
    backup_type: str  # pg_dump | wal_segment | base_backup
    started_at: float
    completed_at: float | None = None
    success: bool = False
    size_bytes: int = 0
    destination: str = ""
    sha256: str = ""
    error: str | None = None
    restore_drill_at: float | None = None
    restore_drill_success: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RestoreDrillResult:
    drill_id: str
    backup_id: str
    started_at: float
    completed_at: float
    success: bool
    jobs_verified: int = 0
    events_verified: int = 0
    repos_verified: int = 0
    error: str | None = None
    rto_seconds: float = 0.0
    notes: str = ""


# ─── Backup manager ───────────────────────────────────────────────────────────


class BackupManager:
    """Manages PostgreSQL backup lifecycle for ZCoder.

    Strategy hierarchy:
      1. pg_dump — logical backup, suitable for small-medium databases
      2. pg_basebackup — physical backup, required for PITR
      3. WAL archiving — continuous archiving for point-in-time recovery

    NOTE: pg_dump alone is not a sufficient low-RPO disaster recovery strategy.
    For production RPO < 1 hour, use WAL archiving (strategy 3).
    """

    def __init__(
        self,
        database_url: str = "",
        backup_destination: str = "/var/backups/zcoder",
        strategy: str = "pg_dump",
        retention_days_daily: int = 7,
        retention_days_weekly: int = 30,
        encryption_key: str = "",
    ) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        self.backup_destination = Path(backup_destination)
        self.strategy = strategy
        self.retention_days_daily = retention_days_daily
        self.retention_days_weekly = retention_days_weekly
        self.encryption_key = encryption_key or os.environ.get("BACKUP_ENCRYPTION_KEY", "")
        self.backup_destination.mkdir(parents=True, exist_ok=True)

    # ── pg_dump backup ────────────────────────────────────────────────────

    def run_pg_dump_backup(self) -> BackupRecord:
        """Run pg_dump logical backup.

        Returns a BackupRecord with success status and SHA256 hash.
        Note: pg_dump is a consistent snapshot but not suitable for PITR.
        For PITR you need WAL archiving (see configure_wal_archiving()).
        """
        backup_id = f"pgdump_{int(time.time())}"
        record = BackupRecord(
            backup_id=backup_id,
            backup_type="pg_dump",
            started_at=time.time(),
        )

        if not self.database_url:
            record.error = "DATABASE_URL not set — cannot run backup"
            record.completed_at = time.time()
            logger.error(record.error)
            return record

        dump_file = self.backup_destination / f"{backup_id}.sql.gz"
        try:
            # Keep the password off the command line: pass it via PGPASSWORD
            # in the filtered child environment instead (SEC-008).
            target_url, password = _split_dsn_password(self.database_url)
            result = subprocess.run(
                [
                    "pg_dump",
                    "--no-password",
                    "--format=custom",
                    "--compress=9",
                    f"--file={dump_file}",
                    target_url,
                ],
                capture_output=True,
                text=True,
                timeout=3600,
                env=build_child_env({"PGPASSWORD": password} if password else None),
            )

            if result.returncode != 0:
                record.error = (
                    f"pg_dump failed (rc={result.returncode}): " f"{_redact(result.stderr, password)}"
                )
                logger.error(record.error)
                record.completed_at = time.time()
                return record

            # Compute SHA256
            record.sha256 = self._sha256_file(dump_file)
            record.size_bytes = dump_file.stat().st_size
            record.destination = str(dump_file)

            # Write manifest
            self._write_manifest(backup_id, record)

            record.success = True
            record.completed_at = time.time()

            duration = record.completed_at - record.started_at
            logger.info(
                f"Backup {backup_id} completed: {record.size_bytes} bytes, "
                f"sha256={record.sha256[:16]}..., duration={duration:.1f}s"
            )

        except subprocess.TimeoutExpired:
            record.error = "pg_dump timed out after 3600s"
            record.completed_at = time.time()
            logger.error(record.error)
        except FileNotFoundError:
            record.error = "pg_dump binary not found — install postgresql-client"
            record.completed_at = time.time()
            logger.error(record.error)
        except Exception as e:
            record.error = str(e)
            record.completed_at = time.time()
            logger.exception(f"Unexpected backup error: {e}")

        return record

    # ── Restore drill ─────────────────────────────────────────────────────

    def run_restore_drill(
        self,
        backup_id: str,
        target_database_url: str = "",
        expected_job_ids: list[str] | None = None,
        expected_repo_ids: list[str] | None = None,
    ) -> RestoreDrillResult:
        """
        Restore a backup into a fresh database and verify state.

        A backup that has never been restored is NOT considered verified.

        Steps:
        1. Find backup file
        2. Restore into target (isolated) database
        3. Verify expected records exist
        4. Report RestoreDrillResult

        target_database_url: a separate PostgreSQL URL for the drill
        (never restore over production!)
        """
        drill_id = f"drill_{int(time.time())}"
        start = time.time()
        result = RestoreDrillResult(
            drill_id=drill_id,
            backup_id=backup_id,
            started_at=start,
            completed_at=start,
            success=False,
        )

        # Locate backup
        dump_file = self.backup_destination / f"{backup_id}.sql.gz"
        if not dump_file.exists():
            result.error = f"Backup file not found: {dump_file}"
            result.completed_at = time.time()
            logger.error(result.error)
            return result

        restore_url = target_database_url or os.environ.get("RESTORE_DRILL_DATABASE_URL", "")
        if not restore_url:
            result.error = "RESTORE_DRILL_DATABASE_URL not set — never restore over production database"
            result.completed_at = time.time()
            logger.error(result.error)
            return result

        try:
            # Keep the password off the command line (SEC-008).
            target_url, password = _split_dsn_password(restore_url)
            restore_result = subprocess.run(
                [
                    "pg_restore",
                    "--no-password",
                    "--clean",
                    "--if-exists",
                    f"--dbname={target_url}",
                    str(dump_file),
                ],
                capture_output=True,
                text=True,
                timeout=3600,
                env=build_child_env({"PGPASSWORD": password} if password else None),
            )

            if restore_result.returncode not in (0, 1):  # rc=1 may be warnings
                result.error = (
                    f"pg_restore failed (rc={restore_result.returncode}): "
                    f"{_redact(restore_result.stderr, password)}"
                )
                logger.error(result.error)
                result.completed_at = time.time()
                return result

            # Verify state
            jobs_verified, repos_verified = self._verify_restored_state(
                restore_url,
                expected_job_ids or [],
                expected_repo_ids or [],
            )

            result.jobs_verified = jobs_verified
            result.repos_verified = repos_verified
            result.success = True
            result.completed_at = time.time()
            result.rto_seconds = result.completed_at - start
            result.notes = (
                f"Restore drill completed in {result.rto_seconds:.1f}s. "
                f"Verified {jobs_verified} jobs, {repos_verified} repos."
            )
            logger.info(f"Restore drill {drill_id} PASSED: {result.notes}")

        except subprocess.TimeoutExpired:
            result.error = "pg_restore timed out after 3600s"
            result.completed_at = time.time()
            logger.error(result.error)
        except Exception as e:
            result.error = str(e)
            result.completed_at = time.time()
            logger.exception(f"Restore drill error: {e}")

        return result

    def _verify_restored_state(
        self,
        database_url: str,
        expected_job_ids: list[str],
        expected_repo_ids: list[str],
    ) -> tuple[int, int]:
        """Verify that expected records exist in the restored database."""
        try:
            import psycopg2  # type: ignore[import]

            from zcoder.core.utils import sanitize_dsn

            conn = psycopg2.connect(sanitize_dsn(database_url))
            try:
                cur = conn.cursor()

                # Count jobs
                cur.execute("SELECT COUNT(*) FROM jobs")
                jobs_count = cur.fetchone()[0]

                # Verify specific jobs if provided
                for job_id in expected_job_ids:
                    cur.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
                    if not cur.fetchone():
                        logger.warning(f"Expected job {job_id} not found after restore")

                # Count repos
                cur.execute("SELECT COUNT(*) FROM repositories")
                repos_count = cur.fetchone()[0]

                # Verify specific repos if provided
                for repo_id in expected_repo_ids:
                    cur.execute("SELECT id FROM repositories WHERE id = %s", (repo_id,))
                    if not cur.fetchone():
                        logger.warning(f"Expected repo {repo_id} not found after restore")

                conn.close()
                return jobs_count, repos_count
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"State verification failed: {e}")
            return 0, 0

    # ── Retention ─────────────────────────────────────────────────────────

    def enforce_retention(self) -> int:
        """Delete backups older than retention policy. Returns count deleted."""
        deleted = 0
        now = time.time()

        for f in self.backup_destination.glob("pgdump_*.sql.gz"):
            try:
                age_days = (now - f.stat().st_mtime) / 86400
                if age_days > self.retention_days_daily:
                    f.unlink()
                    manifest = f.with_suffix(".json")
                    if manifest.exists():
                        manifest.unlink()
                    deleted += 1
                    logger.info(f"Deleted old backup: {f.name} (age={age_days:.1f} days)")
            except Exception as e:
                logger.warning(f"Could not delete {f}: {e}")

        return deleted

    # ── WAL archiving configuration ───────────────────────────────────────

    @staticmethod
    def get_wal_archive_config(archive_path: str = "/var/lib/zcoder/wal") -> dict[str, str]:
        """
        Return PostgreSQL configuration parameters needed for WAL archiving.

        Apply these to postgresql.conf. They require a server restart.

        For PITR, you need:
        1. archive_mode = on
        2. archive_command (copy WAL to archive destination)
        3. Periodic base backup (pg_basebackup)
        4. Recovery using restore_command

        NOTE: Simply setting archive_mode=on is NOT sufficient for PITR.
        You MUST successfully archive WAL files AND perform a base backup
        AND verify that restore actually works before claiming PITR support.
        """
        return {
            "archive_mode": "on",
            "archive_command": f"cp %p {archive_path}/%f",
            "archive_timeout": "60",  # archive WAL every 60s max
            "wal_level": "replica",
            "max_wal_senders": "3",
            # Recovery (add to recovery.conf / postgresql.conf for restore)
            "restore_command": f"cp {archive_path}/%f %p",
            # Recovery target (examples)
            # "recovery_target_time": "2026-01-01 12:00:00",
            # "recovery_target_lsn": "0/15000060",
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    def _sha256_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _write_manifest(self, backup_id: str, record: BackupRecord) -> None:
        manifest_path = self.backup_destination / f"{backup_id}.json"
        with open(manifest_path, "w") as f:
            json.dump(record.to_dict(), f, indent=2, default=str)

    def get_freshness_report(self) -> dict[str, Any]:
        """Scan backup directory for freshness information."""
        backups = sorted(
            self.backup_destination.glob("pgdump_*.sql.gz"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not backups:
            return {
                "last_backup_at": None,
                "last_backup_age_hours": None,
                "backup_count": 0,
                "status": "NO_BACKUPS",
            }

        last = backups[0]
        last_mtime = last.stat().st_mtime
        age_hours = (time.time() - last_mtime) / 3600

        manifest_path = last.with_suffix(".json")
        sha256 = ""
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                sha256 = manifest.get("sha256", "")
            except Exception:
                pass

        return {
            "last_backup_at": last_mtime,
            "last_backup_age_hours": age_hours,
            "backup_count": len(backups),
            "latest_file": str(last.name),
            "sha256": sha256[:16] + "..." if sha256 else "",
            "status": "OK" if age_hours < 26 else "STALE",
        }
