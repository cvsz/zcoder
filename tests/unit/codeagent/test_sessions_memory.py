from __future__ import annotations

import os
import stat

import pytest

from zcoder.agent.codeagent.memory import (
    build_system_prompt,
    expand_mentions,
    load_project_memory,
    mention_candidates,
    zcoder_home,
)
from zcoder.agent.codeagent.sessions import SessionStore, new_session_id
from zcoder.agent.codeagent.workspace import Workspace


def test_session_save_load_list_delete(tmp_path):
    st = SessionStore(tmp_path / "s")
    sid = new_session_id()
    msgs = [
        {"role": "user", "content": 'build a thing\n\n<file path="a">secret</file>'},
        {"role": "assistant", "content": "ok"},
    ]
    st.save(sid, "/proj", msgs, {"prompt": 3})
    assert st.load(sid)["messages"] == msgs
    info = st.list("/proj")[0]
    assert info.id == sid and info.title == "build a thing" and info.turns == 1
    assert st.list("/other") == []
    assert stat.S_IMODE(os.stat(st._path(sid)).st_mode) == 0o600
    st.delete(sid)
    st.delete(sid)  # idempotent
    with pytest.raises(KeyError):
        st.load(sid)


@pytest.mark.parametrize(
    "bad", ["../../etc/passwd", "x", "20240101-000000-ZZZZZZ", "", "20240101-000000-abcdef/../x"]
)
def test_session_ids_cannot_traverse(tmp_path, bad):
    with pytest.raises(ValueError):
        SessionStore(tmp_path)._path(bad)


def test_session_path_rejects_symlink(tmp_path):
    st = SessionStore(tmp_path / "sessions")
    st.dir.mkdir(parents=True)
    session_id = "20240101-000000-aaaaaa"
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    try:
        os.symlink(outside, st.dir / f"{session_id}.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported")
    with pytest.raises(ValueError, match="symlink"):
        st._path(session_id)


def test_list_skips_corrupt_files_and_sorts_newest_first(tmp_path):
    st = SessionStore(tmp_path)
    a, b = "20240101-000000-aaaaaa", "20240102-000000-bbbbbb"
    st.save(a, "/p", [{"role": "user", "content": "old"}])
    st.save(b, "/p", [{"role": "user", "content": "new"}])
    (tmp_path / "broken.json").write_text("{not json")
    assert [i.id for i in st.list()] == [b, a]


def test_project_memory_order_and_cap(tmp_path):
    home = zcoder_home()
    home.mkdir(parents=True)
    (home / "ZCODER.md").write_text("GLOBAL")
    (tmp_path / "ZCODER.md").write_text("PROJECT")
    (tmp_path / "AGENTS.md").write_text("A" * 50_000)
    found = load_project_memory(tmp_path)
    assert [t for _, t in found][:2] == ["GLOBAL", "PROJECT"]
    assert len(found[2][1]) == 20_000


def test_system_prompt_contents(tmp_path):
    ws = Workspace(tmp_path)
    prompt = build_system_prompt(ws, "plan", [("ZCODER.md", "use tabs")], ["Read", "Edit"])
    assert (
        "PLAN MODE" in prompt and "use tabs" in prompt and str(tmp_path) in prompt and "Read, Edit" in prompt
    )
    assert "PLAN MODE" not in build_system_prompt(ws, "default", [], ["Read"])


def test_mentions_are_sandboxed_deduped_and_limited(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "ok.py").write_text("x=1")
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01")
    (tmp_path / "big.txt").write_text("y" * 300_000)
    out, attached = expand_mentions("see @ok.py @ok.py @bin.dat @big.txt @/etc/passwd @missing.py", ws)
    assert attached == ["ok.py"] and out.count("<file ") == 1
    assert ws.read_state  # mentioned files count as read


def test_mention_candidates_skip_ignored_dirs(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "app.js").write_text("")
    assert mention_candidates(ws, "app") == ["src/app.py"]
    assert mention_candidates(ws, "") != []
