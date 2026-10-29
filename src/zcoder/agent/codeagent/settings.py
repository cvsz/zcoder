"""Layered, trust-aware settings.

Precedence (later wins for scalars; list rules accumulate)::

    user      ~/.zcoder/settings.json
    project   <repo>/.zcoder/settings.json
    local     <repo>/.zcoder/settings.local.json
    managed   $ZCODER_MANAGED_SETTINGS or /etc/zcoder/managed-settings.json   (cannot be overridden)

Security model: a repository is untrusted input. Project/local files may only *tighten* the policy
(deny rules, a stricter default mode) unless the repo is trusted — listed in the user's ``trustedProjects``
or ``ZCODER_TRUST_PROJECT=1`` — because allow rules, hooks, and audit paths are code-execution surface.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zcoder.agent.codeagent.memory import zcoder_home

MANAGED_PATH = "/etc/zcoder/managed-settings.json"
_MODES = {"default", "acceptEdits", "plan", "bypass"}
_HOOK_EVENTS = {"PreToolUse", "PostToolUse"}
_STRICTNESS = {"plan": 0, "default": 1, "acceptEdits": 2, "bypass": 3}


@dataclass
class Settings:
    default_mode: str = "default"
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    model: str | None = None
    temperature: float = 0.2
    context_window: int = 32768
    max_steps: int = 40
    scrub_env: bool = True
    pass_env: list[str] = field(default_factory=list)
    audit_log: str | None = None
    hooks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    disable_bypass: bool = False
    trusted_projects: list[str] = field(default_factory=list)
    project_trusted: bool = False
    managed: bool = False
    warnings: list[str] = field(default_factory=list)


def _read_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        warnings.append(f"ignored {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        warnings.append(f"ignored {path}: top level must be an object")
        return {}
    return data


def _strs(value: Any, where: str, warnings: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        warnings.append(f"{where}: expected a list of non-empty strings")
        return []
    return [v.strip() for v in value]


def _hooks(value: Any, where: str, warnings: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if value is None:
        return out
    if not isinstance(value, dict):
        warnings.append(f"{where}.hooks: expected an object")
        return out
    for event, entries in value.items():
        if event not in _HOOK_EVENTS or not isinstance(entries, list):
            warnings.append(f"{where}.hooks.{event}: unsupported")
            continue
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("command"), str) and e["command"].strip():
                out.setdefault(event, []).append(
                    {
                        "matcher": str(e.get("matcher", "*")),
                        "command": e["command"],
                        "timeout": int(e.get("timeout", 30)),
                    }
                )
            else:
                warnings.append(f"{where}.hooks.{event}: entry needs a 'command'")
    return out


def _apply(s: Settings, raw: dict[str, Any], where: str, *, trusted: bool) -> None:
    perms: dict[str, Any] = raw["permissions"] if isinstance(raw.get("permissions"), dict) else {}
    s.deny += _strs(perms.get("deny"), f"{where}.permissions.deny", s.warnings)
    mode = raw.get("defaultMode", perms.get("defaultMode"))
    if mode is not None:
        if mode not in _MODES:
            s.warnings.append(f"{where}: invalid defaultMode {mode!r}")
        elif trusted or _STRICTNESS[mode] <= _STRICTNESS[s.default_mode]:
            s.default_mode = mode
        else:
            s.warnings.append(
                f"{where}: defaultMode {mode!r} ignored (untrusted project cannot loosen the mode)"
            )
    if raw.get("disableBypass") is True:
        s.disable_bypass = True
    if not trusted:
        restricted = [k for k in ("allow",) if perms.get(k)] + [
            k for k in ("hooks", "auditLog", "baseUrl", "passEnv") if raw.get(k)
        ]
        if restricted:
            s.warnings.append(f"{where}: ignored {', '.join(restricted)} (project is not trusted)")
    else:
        s.allow += _strs(perms.get("allow"), f"{where}.permissions.allow", s.warnings)
        for ev, items in _hooks(raw.get("hooks"), where, s.warnings).items():
            s.hooks.setdefault(ev, []).extend(items)
        if isinstance(raw.get("auditLog"), str):
            s.audit_log = raw["auditLog"]
        s.pass_env += _strs(raw.get("passEnv"), f"{where}.passEnv", s.warnings)
    for key, attr, typ in (
        ("model", "model", str),
        ("temperature", "temperature", (int, float)),
        ("contextWindow", "context_window", int),
        ("maxSteps", "max_steps", int),
    ):
        if key in raw:
            if isinstance(raw[key], typ) and not isinstance(raw[key], bool):
                setattr(s, attr, raw[key])
            else:
                s.warnings.append(f"{where}: invalid {key}")
    if isinstance(raw.get("scrubEnv"), bool) and (trusted or raw["scrubEnv"]):
        s.scrub_env = raw["scrubEnv"]  # untrusted projects may only turn scrubbing ON


def load_settings(root: Path, managed_path: str | None = None) -> Settings:
    s = Settings()
    root = Path(root).resolve()
    user = _read_json(zcoder_home() / "settings.json", s.warnings)
    s.trusted_projects = _strs(user.get("trustedProjects"), "user.trustedProjects", s.warnings)
    s.project_trusted = os.getenv("ZCODER_TRUST_PROJECT") == "1" or any(
        root == Path(t).expanduser().resolve() or Path(t).expanduser().resolve() in root.parents
        for t in s.trusted_projects
    )
    _apply(s, user, "user", trusted=True)
    _apply(
        s, _read_json(root / ".zcoder" / "settings.json", s.warnings), "project", trusted=s.project_trusted
    )
    _apply(
        s,
        _read_json(root / ".zcoder" / "settings.local.json", s.warnings),
        "local",
        trusted=s.project_trusted,
    )
    mpath = Path(managed_path or os.getenv("ZCODER_MANAGED_SETTINGS") or MANAGED_PATH)
    if mpath.is_file():
        managed = _read_json(mpath, s.warnings)
        # Managed policy always wins: replace allow-lists it constrains and force its scalars.
        s.managed = True
        _apply(s, managed, "managed", trusted=True)
        mp = managed.get("permissions")
        if isinstance(mp, dict) and mp.get("allowOnly") is True:
            s.allow = _strs(mp.get("allow"), "managed.permissions.allow", s.warnings)
        if isinstance(managed.get("defaultMode"), str) and managed["defaultMode"] in _MODES:
            s.default_mode = managed["defaultMode"]
    s.deny = list(dict.fromkeys(s.deny))
    s.allow = list(dict.fromkeys(s.allow))
    return s
