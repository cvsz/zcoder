"""
claude_sessions.py — Persistent conversation sessions with resume,
checkpoints (named rewind points), and an "away summary" that shows
what changed in the project directory while you were away.
ZCoder CLI v1.10.0
"""

import json
import os
import re
import shutil
import subprocess  # nosec B404  # fixed read-only git log invocation
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

GIT_BIN = shutil.which("git") or "git"
SESSIONS_DIR = Path.home() / ".zcoder" / "sessions"
CHECKPOINTS_DIR = Path.home() / ".zcoder" / "checkpoints"
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}

# Session/checkpoint ids are the last line of defense against path traversal
# (SEC-002/SEC-004). They are always server-generated; any id reaching the
# filesystem must match this allowlist or the path helpers fail closed.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_id(value: str, kind: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.match(value):
        raise ValueError(f"Invalid {kind} id: must match [A-Za-z0-9_-] and be 1-64 chars")
    return value


def _safe_child_path(base_dir: Path, filename: str) -> Path:
    name = _validate_id(filename, "file")
    base_dir.mkdir(parents=True, exist_ok=True)
    base = Path(os.path.realpath(base_dir))
    candidate = Path(os.path.realpath(base / f"{name}.json"))
    if candidate.parent != base:
        raise ValueError("Resolved path escapes the allowed directory")
    return candidate


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class Turn:
    role: str
    content: str
    ts: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return {"role": self.role, "content": self.content, "ts": self.ts}

    @staticmethod
    def from_dict(d):
        return Turn(role=d["role"], content=d["content"], ts=d.get("ts", ""))


@dataclass
class Session:
    sid: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    mode: str = "interactive"
    title: str | None = None
    model: str = "claude-sonnet-5"
    persona: str | None = None
    turns: list[Turn] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_turn(self, role: str, content: str):
        self.turns.append(Turn(role=role, content=content))
        self.updated = datetime.now().isoformat()

    def to_dict(self):
        return {
            "sid": self.sid,
            "mode": self.mode,
            "title": self.title,
            "model": self.model,
            "persona": self.persona,
            "turns": [t.to_dict() for t in self.turns],
            "created": self.created,
            "updated": self.updated,
        }

    @staticmethod
    def from_dict(d):
        s = Session(
            sid=d["sid"],
            mode=d.get("mode", "interactive"),
            title=d.get("title"),
            model=d.get("model", "claude-sonnet-5"),
            persona=d.get("persona"),
            created=d.get("created", ""),
            updated=d.get("updated", ""),
        )
        s.turns = [Turn.from_dict(t) for t in d.get("turns", [])]
        return s

    def recap(self, n: int = 3) -> str:
        if not self.turns:
            return f"[{self.sid}] empty"
        lines = [f"Session [{self.sid}] — {len(self.turns)} turns, {self.mode}"]
        for t in self.turns[-n:]:
            preview = t.content[:100].replace("\n", " ")
            lines.append(f"  {t.role}: {preview}{'…' if len(t.content) > 100 else ''}")
        return "\n".join(lines)


@dataclass
class Checkpoint:
    cpid: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    sid: str = ""
    label: str = ""
    n_turns: int = 0
    snap: list[dict] = field(default_factory=list)
    ts: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return {
            "cpid": self.cpid,
            "sid": self.sid,
            "label": self.label,
            "n_turns": self.n_turns,
            "snap": self.snap,
            "ts": self.ts,
        }

    @staticmethod
    def from_dict(d):
        cp = Checkpoint()
        cp.cpid = d["cpid"]
        cp.sid = d["sid"]
        cp.label = d.get("label", "")
        cp.n_turns = d.get("n_turns", 0)
        cp.snap = d.get("snap", [])
        cp.ts = d.get("ts", "")
        return cp


# ── Storage helpers ───────────────────────────────────────────────────────────


def _sess_path(sid: str) -> Path:
    return _safe_child_path(SESSIONS_DIR, _validate_id(sid, "session"))


def _cp_path(cpid: str) -> Path:
    return _safe_child_path(CHECKPOINTS_DIR, _validate_id(cpid, "checkpoint"))


def save_session(s: Session):
    _sess_path(s.sid).write_text(json.dumps(s.to_dict(), indent=2))


def load_session(sid: str) -> Session | None:
    p = _sess_path(sid)
    if not p.exists():
        return None
    return Session.from_dict(json.loads(p.read_text()))


def latest_session(mode: str | None = None) -> Session | None:
    if not SESSIONS_DIR.exists():
        return None
    sessions = []
    for p in SESSIONS_DIR.glob("*.json"):
        try:
            s = Session.from_dict(json.loads(p.read_text()))
            if mode is None or s.mode == mode:
                sessions.append(s)
        except Exception:
            # File may be malformed; skip it.
            pass
    return max(sessions, key=lambda s: s.updated) if sessions else None


def list_sessions(mode: str | None = None) -> list[Session]:
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for p in SESSIONS_DIR.glob("*.json"):
        try:
            s = Session.from_dict(json.loads(p.read_text()))
            if mode is None or s.mode == mode:
                out.append(s)
        except Exception:
            # File may be malformed; skip it.
            pass
    return sorted(out, key=lambda s: s.updated, reverse=True)


def capture_checkpoint(s: Session, label: str) -> Checkpoint:
    cp = Checkpoint(sid=s.sid, label=label, n_turns=len(s.turns), snap=[t.to_dict() for t in s.turns])
    _cp_path(cp.cpid).write_text(json.dumps(cp.to_dict(), indent=2))
    return cp


def rewind_to_checkpoint(s: Session, cpid: str) -> Session:
    p = _cp_path(cpid)
    if not p.exists():
        raise ValueError(f"Checkpoint not found: {cpid}")
    cp = Checkpoint.from_dict(json.loads(p.read_text()))
    if cp.sid != s.sid:
        raise ValueError("Checkpoint belongs to a different session")
    s.turns = [Turn.from_dict(t) for t in cp.snap]
    s.updated = datetime.now().isoformat()
    save_session(s)
    return s


def list_checkpoints(sid: str) -> list[Checkpoint]:
    if not CHECKPOINTS_DIR.exists():
        return []
    out = []
    for p in CHECKPOINTS_DIR.glob("*.json"):
        try:
            cp = Checkpoint.from_dict(json.loads(p.read_text()))
            if cp.sid == sid:
                out.append(cp)
        except Exception:
            # File may be malformed; skip it.
            pass
    return sorted(out, key=lambda c: c.ts)


# ── Away summary ──────────────────────────────────────────────────────────────


def away_summary(cwd: str, since_iso: str) -> str:
    from datetime import datetime

    since_dt = datetime.fromisoformat(since_iso)

    # git commits since
    commits: list[str] = []
    try:
        r = subprocess.run(  # nosec B603  # fixed argv git log, no shell
            [GIT_BIN, "log", f"--since={since_iso}", "--oneline"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        commits = [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        # Git may not be available in all environments; safe to ignore.
        pass

    # files modified since
    modified: list[str] = []
    root = Path(cwd)
    ts = since_dt.timestamp()
    count = 0
    for path in root.rglob("*"):
        if count > 5000:
            break
        count += 1
        if any(p in SKIP_DIRS for p in path.parts):
            continue
        if path.is_file():
            try:
                if path.stat().st_mtime > ts:
                    modified.append(str(path.relative_to(root)))
                    if len(modified) >= 50:
                        break
            except OSError:
                # Checkpoint file may be malformed; skip it.
                pass

    if not commits and not modified:
        return "No changes detected in the project since this session was last active."
    lines = ["While you were away:"]
    if commits:
        lines.append(f"  {len(commits)} commit(s):")
        for c in commits[:8]:
            lines.append(f"    · {c}")
    if modified:
        lines.append(f"  {len(modified)} file(s) modified:")
        for f in modified[:10]:
            lines.append(f"    · {f}")
    return "\n".join(lines)


# ── CLI commands ──────────────────────────────────────────────────────────────


def cmd_sessions_list():
    ss = list_sessions()
    if not ss:
        print("No saved sessions.")
        return
    print(f"{'ID':<14} {'Mode':<14} {'Turns':<7} {'Title / Updated'}")
    print("─" * 60)
    for s in ss[:20]:
        title = (s.title or "")[:24]
        upd = s.updated[:16]
        print(f"{s.sid:<14} {s.mode:<14} {len(s.turns):<7} {title or upd}")


def cmd_session_show(sid: str):
    s = load_session(sid)
    if not s:
        print(f"Session not found: {sid}")
        return
    print(s.recap(n=10))


def cmd_checkpoint_list(sid: str):
    cps = list_checkpoints(sid)
    if not cps:
        print(f"No checkpoints for session {sid}")
        return
    for cp in cps:
        print(f"  [{cp.cpid}] '{cp.label}' — {cp.n_turns} turns, {cp.ts[:16]}")


def cmd_away_summary(sid: str, cwd: str = "."):
    s = load_session(sid)
    if not s:
        print(f"Session not found: {sid}")
        return
    print(away_summary(cwd, s.updated))
