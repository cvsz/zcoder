"""Regression guards for the cross-process Upgrade-26 run lease."""

import json

import pytest

from zcoder.services.upgrade_lease import UpgradeRunLease, UpgradeRunLeaseError


def test_run_lease_is_exclusive_and_fail_closed(tmp_path):
    path = tmp_path / "upgrade.lock"
    first = UpgradeRunLease(path)
    first.acquire()

    with pytest.raises(UpgradeRunLeaseError, match="already held"):
        UpgradeRunLease(path).acquire()

    assert path.exists()
    first.release()
    assert not path.exists()


def test_run_lease_releases_after_context_exit(tmp_path):
    path = tmp_path / "upgrade.lock"

    with UpgradeRunLease(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pid"] > 0
        assert payload["host"]
        assert payload["token"]

    assert not path.exists()


def test_run_lease_does_not_delete_foreign_ownership(tmp_path):
    path = tmp_path / "upgrade.lock"
    lease = UpgradeRunLease(path)
    lease.acquire()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["token"] = "different-owner"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UpgradeRunLeaseError, match="ownership changed"):
        lease.release()

    assert path.exists()


def test_run_lease_validates_bounded_wait_configuration(tmp_path):
    with pytest.raises(ValueError, match="wait_seconds"):
        UpgradeRunLease(tmp_path / "upgrade.lock", wait_seconds=-1)
    with pytest.raises(ValueError, match="poll_seconds"):
        UpgradeRunLease(tmp_path / "upgrade.lock", poll_seconds=0)
