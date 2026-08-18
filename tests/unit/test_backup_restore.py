"""tests/test_backup_restore.py — Tests for backup and restore functionality."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from zcoder.services.backup_restore import BackupManager, BackupRecord, RestoreDrillResult


@pytest.fixture
def backup_manager(tmp_path):
    """Create a BackupManager with a temp destination directory."""
    return BackupManager(
        database_url="",  # No real DB for unit tests
        backup_destination=str(tmp_path / "backups"),
        strategy="pg_dump",
        retention_days_daily=7,
        retention_days_weekly=30,
    )


class TestBackupRecord:
    def test_backup_record_to_dict(self):
        record = BackupRecord(
            backup_id="pgdump_123",
            backup_type="pg_dump",
            started_at=1000.0,
            success=True,
            size_bytes=1024,
        )
        d = record.to_dict()
        assert d["backup_id"] == "pgdump_123"
        assert d["success"] is True
        assert d["size_bytes"] == 1024

    def test_backup_record_failed_state(self):
        record = BackupRecord(
            backup_id="pgdump_456",
            backup_type="pg_dump",
            started_at=1000.0,
            success=False,
            error="Connection refused",
        )
        assert record.success is False
        assert record.error == "Connection refused"


class TestBackupManagerInit:
    def test_destination_created_on_init(self, tmp_path):
        dest = tmp_path / "new_backup_dir"
        assert not dest.exists()
        BackupManager(
            database_url="",
            backup_destination=str(dest),
        )
        assert dest.exists()

    def test_default_strategy_is_pg_dump(self, backup_manager):
        assert backup_manager.strategy == "pg_dump"


class TestPgDumpBackup:
    def test_backup_fails_without_database_url(self, backup_manager):
        """Backup must fail gracefully without a database URL."""
        backup_manager.database_url = ""
        record = backup_manager.run_pg_dump_backup()
        assert record.success is False
        assert record.error is not None
        assert "DATABASE_URL" in record.error

    def test_backup_fails_without_pg_dump_binary(self, backup_manager):
        """Backup fails gracefully if pg_dump binary not available."""
        backup_manager.database_url = "postgresql://localhost/testdb"

        with patch("subprocess.run", side_effect=FileNotFoundError("pg_dump not found")):
            record = backup_manager.run_pg_dump_backup()

        assert record.success is False
        assert "pg_dump" in record.error.lower() or "not found" in record.error.lower()

    def test_backup_timeout_handling(self, backup_manager):
        """Backup handles subprocess timeout correctly."""
        import subprocess

        backup_manager.database_url = "postgresql://localhost/testdb"

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pg_dump", 3600)):
            record = backup_manager.run_pg_dump_backup()

        assert record.success is False
        assert "timed out" in record.error.lower()

    def test_backup_creates_manifest(self, backup_manager, tmp_path):
        """Successful backup should write a JSON manifest."""
        backup_manager.database_url = "postgresql://localhost/testdb"

        # Create a fake dump file
        dest = Path(backup_manager.backup_destination)
        backup_id = "pgdump_test_manifest"
        fake_file = dest / f"{backup_id}.sql.gz"
        fake_file.write_bytes(b"fake dump data")

        # Call manifest writer directly
        record = BackupRecord(
            backup_id=backup_id,
            backup_type="pg_dump",
            started_at=time.time(),
            success=True,
            size_bytes=14,
            sha256="abc123",
        )
        backup_manager._write_manifest(backup_id, record)

        manifest_path = dest / f"{backup_id}.json"
        assert manifest_path.exists()
        with open(manifest_path) as f:
            data = json.load(f)
        assert data["backup_id"] == backup_id
        assert data["success"] is True


class TestRestoreDrill:
    def test_restore_fails_without_backup_file(self, backup_manager):
        result = backup_manager.run_restore_drill("nonexistent_backup_id_xyz")
        assert result.success is False
        assert result.error is not None

    def test_restore_fails_without_target_database(self, backup_manager, tmp_path):
        """Restore drill must fail if no target (restore) database is provided."""
        # Create a fake backup file
        dest = Path(backup_manager.backup_destination)
        backup_id = "pgdump_restore_test"
        fake_file = dest / f"{backup_id}.sql.gz"
        fake_file.write_bytes(b"fake dump")

        # No target URL — must fail
        os.environ.pop("RESTORE_DRILL_DATABASE_URL", None)
        result = backup_manager.run_restore_drill(backup_id, target_database_url="")
        assert result.success is False
        assert "RESTORE_DRILL_DATABASE_URL" in result.error or "never restore" in result.error.lower()

    def test_restore_drill_result_fields(self):
        result = RestoreDrillResult(
            drill_id="drill_001",
            backup_id="pgdump_001",
            started_at=1000.0,
            completed_at=1060.0,
            success=True,
            jobs_verified=5,
            repos_verified=2,
            rto_seconds=60.0,
        )
        assert result.success is True
        assert result.rto_seconds == 60.0
        assert result.jobs_verified == 5


class TestRetentionPolicy:
    def test_enforce_retention_deletes_old_backups(self, backup_manager, tmp_path):
        """Old backup files should be deleted based on retention policy."""
        dest = Path(backup_manager.backup_destination)
        backup_manager.retention_days_daily = 0  # Everything older than 0 days

        # Create a fake backup file
        old_backup = dest / "pgdump_old_backup.sql.gz"
        old_backup.write_bytes(b"old backup")

        # Make it "old" by manipulating mtime
        old_mtime = time.time() - (1 * 86400)  # 1 day old
        os.utime(old_backup, (old_mtime, old_mtime))

        deleted = backup_manager.enforce_retention()
        assert deleted >= 1
        assert not old_backup.exists()

    def test_enforce_retention_keeps_recent_backups(self, backup_manager):
        """Recent backups should NOT be deleted."""
        dest = Path(backup_manager.backup_destination)
        backup_manager.retention_days_daily = 7

        # Create a recent backup
        recent_backup = dest / "pgdump_recent.sql.gz"
        recent_backup.write_bytes(b"recent backup")
        # mtime is now (very recent)

        backup_manager.enforce_retention()
        assert recent_backup.exists()


class TestWalArchiveConfig:
    def test_wal_config_has_required_settings(self):
        config = BackupManager.get_wal_archive_config("/var/lib/zcoder/wal")
        assert "archive_mode" in config
        assert config["archive_mode"] == "on"
        assert "archive_command" in config
        assert "restore_command" in config
        assert "wal_level" in config

    def test_wal_config_warning_in_docstring(self):
        """WAL config docs must warn that archive_mode alone is not sufficient for PITR."""
        doc = BackupManager.get_wal_archive_config.__doc__
        assert doc is not None
        assert "PITR" in doc or "pitr" in doc.lower()
        # Must not let callers claim PITR just from setting archive_mode
        assert "not sufficient" in doc or "NOT sufficient" in doc


class TestFreshnessReport:
    def test_freshness_report_no_backups(self, backup_manager):
        report = backup_manager.get_freshness_report()
        assert report["backup_count"] == 0
        assert report["status"] == "NO_BACKUPS"

    def test_freshness_report_with_recent_backup(self, backup_manager, tmp_path):
        dest = Path(backup_manager.backup_destination)
        recent_backup = dest / "pgdump_12345.sql.gz"
        recent_backup.write_bytes(b"recent backup")

        report = backup_manager.get_freshness_report()
        assert report["backup_count"] >= 1
        assert report["last_backup_age_hours"] is not None
        assert report["status"] == "OK"  # Recent backup

    def test_freshness_report_stale_backup(self, backup_manager, tmp_path):
        dest = Path(backup_manager.backup_destination)
        old_backup = dest / "pgdump_99999.sql.gz"
        old_backup.write_bytes(b"old backup")

        # Set mtime to 30 hours ago (> 26h threshold)
        old_mtime = time.time() - (30 * 3600)
        os.utime(old_backup, (old_mtime, old_mtime))

        report = backup_manager.get_freshness_report()
        assert report["status"] == "STALE"
