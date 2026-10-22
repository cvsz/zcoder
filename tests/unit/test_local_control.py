"""Offline control plane regressions; no network or Anthropic dependencies."""

import sqlite3

import pytest

from zcoder.services.local_control import LocalControlStore


def test_bootstrap_roles_and_independent_approval(tmp_path):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    with pytest.raises(PermissionError):
        store.bootstrap_admin("intruder")
    store.grant_role("admin", "worker", "operator")
    store.grant_role("admin", "inspector", "auditor")
    store.create_task("worker", "job-1", "Review local compiler")
    with pytest.raises(PermissionError):
        store.decide_task("worker", "job-1", True)
    store.decide_task("admin", "job-1", True)
    with pytest.raises(ValueError):
        store.decide_task("admin", "job-1", True)
    with pytest.raises(PermissionError):
        store.audit_records("worker")
    assert store.verify_audit_chain("inspector")


def test_owner_cannot_self_approve(tmp_path):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    store.create_task("admin", "job-2", "Sensitive operation")
    with pytest.raises(PermissionError):
        store.decide_task("admin", "job-2", True)


def test_audit_tampering_detected(tmp_path):
    path = tmp_path / "control.sqlite"
    store = LocalControlStore(path)
    store.bootstrap_admin("admin")
    store.grant_role("admin", "auditor", "auditor")
    assert store.verify_audit_chain("auditor")
    with sqlite3.connect(path) as db:
        db.execute("UPDATE audit SET subject='tampered' WHERE seq=1")
    assert not store.verify_audit_chain("auditor")


def test_fail_closed_roles(tmp_path):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    with pytest.raises(ValueError):
        store.grant_role("admin", "other", "root")
    with pytest.raises(PermissionError):
        store.create_task("unknown", "job", "Task")
