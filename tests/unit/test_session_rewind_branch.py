"""Regression tests for Slice E.7 — session rewind and branch."""

import tempfile

import pytest

from zcoder.claude.capabilities.code import CodeSession


def _save(session):
    session.save()


def _load(session_id):
    return CodeSession.load(session_id)


def test_rewind_truncates_turns_and_checkpoints():
    with tempfile.TemporaryDirectory() as tmp:
        s = CodeSession(cwd=tmp)
        s.add_turn("user", "t1")
        s.add_turn("assistant", "t2")
        cp = s.checkpoint("after-t2")
        s.add_turn("user", "t3")
        s.add_turn("assistant", "t4")
        _save(s)

        s2 = _load(s.id)
        s2.rewind(cp["id"])
        _save(s2)

        s3 = _load(s.id)
        assert len(s3.turns) == 2
        assert s3.turns[0]["content"] == "t1"
        assert s3.turns[1]["content"] == "t2"
        assert len(s3.checkpoints) == 1
        assert s3.checkpoints[0]["id"] == cp["id"]


def test_rewind_missing_checkpoint_raises():
    with tempfile.TemporaryDirectory() as tmp:
        s = CodeSession(cwd=tmp)
        s.add_turn("user", "t1")
        with pytest.raises(KeyError):
            s.rewind("missing")


def test_branch_creates_new_session_from_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        s = CodeSession(cwd=tmp, model="test-model")
        s.add_turn("user", "t1")
        s.add_turn("assistant", "t2")
        cp = s.checkpoint("after-t2")
        s.add_turn("user", "t3")
        _save(s)

        branched = s.branch(cp["id"], name="branch-1")
        assert branched.id == "branch-1"
        assert len(branched.turns) == 2
        assert branched.turns[0]["content"] == "t1"
        assert branched.turns[1]["content"] == "t2"
        assert branched.model == "test-model"
        assert branched.cwd == tmp
        assert branched.permission_mode == s.permission_mode
        assert branched.system_prompt == s.system_prompt
        assert len(branched.checkpoints) == 1
        assert branched.checkpoints[0]["id"] == cp["id"]


def test_branch_independent_from_parent():
    with tempfile.TemporaryDirectory() as tmp:
        s = CodeSession(cwd=tmp)
        s.add_turn("user", "t1")
        s.add_turn("assistant", "t2")
        cp = s.checkpoint("after-t2")
        s.add_turn("user", "t3")
        _save(s)

        branched = s.branch(cp["id"])
        branched.add_turn("user", "branch-only")
        _save(branched)

        parent = _load(s.id)
        assert len(parent.turns) == 3
        assert parent.turns[-1]["content"] == "t3"

        child = _load(branched.id)
        assert len(child.turns) == 3
        assert child.turns[-1]["content"] == "branch-only"


def test_branch_preserves_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        s = CodeSession(cwd=tmp, model="test-model", permission_mode="acceptEdits", system_prompt="sys")
        s.add_turn("user", "t1")
        s.add_tool_call("Read", {"path": "foo"}, "ok")
        s.add_turn("assistant", "t2")
        cp = s.checkpoint("after-t2")
        s.add_tool_call("Write", {"path": "bar"}, "ok")
        _save(s)

        branched = s.branch(cp["id"])
        assert branched.model == "test-model"
        assert branched.permission_mode == "acceptEdits"
        assert branched.system_prompt == "sys"
        assert branched.cwd == tmp
        assert len(branched.tool_calls) == 2
