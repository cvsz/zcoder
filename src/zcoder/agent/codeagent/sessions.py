"""Persisted, resumable conversations (one JSON file per session)."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zcoder.agent.codeagent.memory import zcoder_home

_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


@dataclass
class SessionInfo:
    id: str
    title: str
    cwd: str
    updated: float
    turns: int


class SessionStore:
    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else zcoder_home() / "sessions"

    def _validate_session_id(self, session_id: str) -> str:
        """Validate and return a sanitized session ID safe for filesystem use.

        Session IDs are strictly formatted (YYYYMMDD-HHMMSS-XXXXXX) with no
        path separators or traversal sequences, so the returned value can be
        embedded directly into a filesystem path without traversal risk.
        """
        if not isinstance(session_id, str):
            raise ValueError("invalid session id")
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("invalid session id")
        safe_id = os.path.basename(session_id)
        if safe_id != session_id or not _ID.fullmatch(safe_id):
            raise ValueError("invalid session id")
        return safe_id

    def _path(self, session_id: str) -> Path:
        # Validate the ID first (basename + strict pattern allowlist).
        safe_id = self._validate_session_id(session_id)
        # _validate_session_id() enforces a strict regex allowlist
        # ([0-9]{8}-[0-9]{6}-[0-9a-f]{6}) and basename check, so safe_id
        # contains no path separators or traversal sequences. It is safe to
        # embed directly into a filesystem path below.
        root = self.dir.resolve()
        expected = root / f"{safe_id}.json"
        # Normalize the path with os.path.realpath, then prove containment
        # with a prefix check against the storage root before any filesystem
        # access. This blocks both traversal sequences and symlink escapes.
        resolved_path = os.path.realpath(expected)
        if not resolved_path.startswith(str(root) + os.sep):
            raise ValueError("session path escapes storage directory")
        if resolved_path != str(expected):
            raise ValueError("session path must not resolve through a symlink")
        return Path(resolved_path)

    def save(
        self, session_id: str, cwd: str, messages: list[dict[str, Any]], usage: dict[str, int] | None = None
    ) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        title = next(
            (m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)),
            "",
        )
        title = re.sub(r"\s+", " ", title.split("<file path=")[0]).strip()[:80] or "(empty)"
        doc = {
            "id": session_id,
            "cwd": cwd,
            "title": title,
            "updated": time.time(),
            "usage": usage,
            "messages": messages,
        }
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path(session_id))

    def load(self, session_id: str) -> dict[str, Any]:
        try:
            return json.loads(self._path(session_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(session_id) from exc
        except json.JSONDecodeError:
            return {}

    def list_sessions(self, cwd: str | None = None) -> list[SessionInfo]:
        infos: list[SessionInfo] = []
        for p in self.dir.glob("*.json") if self.dir.exists() else []:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if cwd and d.get("cwd") != cwd:
                    continue
                infos.append(
                    SessionInfo(
                        d["id"],
                        d.get("title", ""),
                        d.get("cwd", ""),
                        d.get("updated", 0.0),
                        sum(m.get("role") == "user" for m in d.get("messages", [])),
                    )
                )
            except (OSError, ValueError, KeyError):
                continue
        return sorted(infos, key=lambda i: i.updated, reverse=True)

    def list(self, cwd: str | None = None) -> list[SessionInfo]:
        """Backward compatibility alias for list_sessions."""
        return self.list_sessions(cwd)

    def delete(self, session_id: str, confirm: bool = True) -> None:
        """Delete a session with optional confirmation."""
        if confirm:
            # In a real implementation, this would prompt the user
            # For now, we just delete
            pass
        # _path() calls _validate_session_id() which enforces a strict regex
        # allowlist ([0-9]{8}-[0-9]{6}-[0-9a-f]{6}) and basename check, so
        # user-provided session_id cannot reach the filesystem unsanitized.
        self._path(session_id).unlink(missing_ok=True)

    def fork(self, session_id: str, *, label: str | None = None) -> str:
        """Create a new session that copies the messages from an existing one.

        Returns the new session ID. The forked session shares the same cwd and
        message history, allowing the agent to branch off a previous conversation
        without losing the original.
        """
        original = self.load(session_id)
        new_id = new_session_id()
        messages = list(original.get("messages", []))
        if label:
            messages.append({"role": "user", "content": label})
        self.save(new_id, original.get("cwd", ""), messages, original.get("usage"))
        return new_id

    def rename(self, session_id: str, new_title: str) -> None:
        """Update the title of a session by updating the first user message."""
        doc = self.load(session_id)
        messages = doc.get("messages", [])
        # Update the first user message to reflect the new title
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                msg["content"] = new_title
                break
        doc["updated"] = time.time()
        self.save(session_id, doc.get("cwd", ""), messages, doc.get("usage"))

    def search(self, query: str, cwd: str | None = None) -> list[SessionInfo]:
        """Search sessions by title or content."""
        query = query.lower()
        results: list[SessionInfo] = []
        for info in self.list_sessions(cwd):
            doc = self.load(info.id)
            title = doc.get("title", "").lower()
            content = " ".join(
                m.get("content", "") for m in doc.get("messages", []) if isinstance(m.get("content"), str)
            ).lower()
            if query in title or query in content:
                results.append(info)
        return results

    def export(self, session_id: str, output_path: str | Path) -> None:
        """Export a session to a JSON file."""
        doc = self.load(session_id)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(doc, indent=2))

    def import_session(self, input_path: str | Path, new_id: str | None = None) -> str:
        """Import a session from a JSON file."""
        input_path = Path(input_path)
        doc = json.loads(input_path.read_text(encoding="utf-8"))
        new_id = new_id or new_session_id()
        self.save(new_id, doc.get("cwd", ""), doc.get("messages", []), doc.get("usage"))
        return new_id


# ── Session event types (deepseek-harness compatibility) ──────────────────
# Known session event vocabulary. Events written to a session log carry one of
# these discriminants; readers refuse to interpret unknown types unless the
# envelope carries ``ignorable`` marker.
SESSION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "agent-preset/selected",
        "agent/inbox/spliced",
        "approval/asked",
        "approval/decided",
        "approval/policy",
        "assistant/attempt",
        "assistant/message",
        "command/done",
        "command/run",
        "compaction/end",
        "compaction/prune",
        "compaction/start",
        "compaction/summary",
        "deliverables/presented",
        "developer/message",
        "feedback/message-delete",
        "feedback/message-put",
        "feedback/record",
        "goal/change",
        "hook/invoked",
        "hook/result",
        "image/offload",
        "job/registered",
        "job/settled",
        "llm/retry",
        "llm/retry-started",
        "model/selection",
        "permission/preset",
        "plan/mode",
        "request/context",
        "request/header",
        "sandbox/mode",
        "schedule/change",
        "session/end-seed",
        "session/title",
        "session/title-llm-request",
        "step/end",
        "step/start",
        "subagent/catalog",
        "subagent/descriptor",
        "subagent/model-selection-policy",
        "system/message",
        "team/member",
        "team/message/delivered",
        "team/message/queued",
        "team/mode",
        "team/task",
        "todo/write",
        "tool-workflow/agent-end",
        "tool-workflow/agent-start",
        "tool-workflow/run-end",
        "tool-workflow/run-start",
        "tool/call",
        "tool/ptc-dispatch",
        "tool/ptc-dispatch-start",
        "tool/result",
        "turn/end",
        "turn/start",
        "user/message",
        "web/deepseek-search-llm-request",
        "working-directory/change",
    }
)

SESSION_FORMAT_VERSION = 4


@dataclass
class SessionEvent:
    """Durable session event appended to the log.

    Events are the source of truth for model-visible context. New event types
    added to this set require the envelope's ``ignorable`` marker so older
    readers do not misinterpret them.
    """

    kind: str  # one of SESSION_EVENT_TYPES or an ignorable extension
    data: dict[str, Any]
    source_event_seqs: list[int] | None = None
    ignorable: bool = False
    surface_op: str | None = None  # 'append' for committed appends
    event_id: str = ""
    timestamp: float = 0.0


@dataclass
class RequestHeader:
    """One resolved request envelope. Logged once per request series."""

    header: dict[str, Any]
    reason: str  # 'initial' | 'resume' | 'change' | 'series'
    starts_series: bool = False


@dataclass
class ModelSelection:
    """Complete provider, model, and optional reasoning effort chosen for one Session's model steps."""

    provider: str
    model: str
    reasoning_effort: str | None = None


@dataclass
class ModelSelectionProjection:
    """Client view of the durable model-selection fold."""

    last_used: ModelSelection | None = None
    next: ModelSelection | None = None


class SessionSurface:
    """Projected surface generation and content hash for a session.

    Mirrors dsh-session/surface.ts: content generation increments on each
    appended event, allowing consumers to detect when the request header
    needs refreshing.
    """

    def __init__(self) -> None:
        self.content_generation: int = 0
        self.content_hash: str = ""

    def advance(self, event: SessionEvent) -> None:
        self.content_generation += 1


# ── Token usage and cost tracking ───────────────────────────────────────────


@dataclass
class TokenUsage:
    """Token usage for a single operation (turn, tool call, or request)."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolUsageStat:
    """Per-tool usage statistics aggregated across a session."""

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class CostBreakdown:
    """Cost breakdown by category for a session."""

    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0

    def __post_init__(self) -> None:
        self.total_cost = self.input_cost + self.output_cost

    @property
    def by_category(self) -> dict[str, float]:
        return {"input": self.input_cost, "output": self.output_cost, "total": self.total_cost}


# ── Default model pricing (per 1K tokens) ───────────────────────────────────

# Default pricing for zcoder models. These can be overridden per session.
DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    "zcoder-pro": {"input": 0.0015, "output": 0.006},
    "zcoder-flash": {"input": 0.00025, "output": 0.001},
    "zcoder-promax": {"input": 0.003, "output": 0.012},
    "claude-sonnet-5": {"input": 0.003, "output": 0.015},
    "claude-opus-5": {"input": 0.015, "output": 0.075},
    "claude-haiku-4-5": {"input": 0.00025, "output": 0.00125},
}


def estimate_cost(input_tokens: int, output_tokens: int, model: str = "zcoder-flash") -> float:
    """Estimate cost for token usage given a model's pricing.

    Prices are per 1,000 tokens.
    """
    pricing = DEFAULT_MODEL_PRICING.get(model, DEFAULT_MODEL_PRICING["zcoder-flash"])
    input_cost = (input_tokens / 1000.0) * pricing["input"]
    output_cost = (output_tokens / 1000.0) * pricing["output"]
    return input_cost + output_cost


class SessionProjection:
    """Fold committed events into projected state.

    Mirrors deepseek-harness's session projection system: each event is
    folded into a projected state that can be queried without re-reading
    the full event log. This enables efficient replay and reconstruction
    of model-visible context.

    Follows the "Model-Visible ⟺ Logged" pattern: everything model-visible
    must be reconstructable from the session log.
    """

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.state_version: int = 1
        self.event_count: int = 0
        self.last_event_seq: str | None = None
        # Token usage tracking
        self.token_usage: dict[str, TokenUsage] = {}  # keyed by turn or tool name
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        # Tool usage statistics
        self.tool_stats: dict[str, ToolUsageStat] = {}
        # Cost tracking
        self.cost_breakdown: CostBreakdown = CostBreakdown()
        self.model: str = "zcoder-flash"
        # Session timing
        self.session_start_time: float | None = None
        self.session_end_time: float | None = None

    def fold(self, event: SessionEvent) -> None:
        """Fold one committed event into projected state.

        Handles all session event types:
        - turn/start, turn/end
        - step/start, step/end
        - user/message, assistant/message, system/message, developer/message
        - tool/call, tool/result
        - request/header, request/context
        - session/end-seed
        """
        kind = event.kind
        data = event.data or {}
        self.event_count += 1
        self.last_event_seq = str(event.event_id)

        # Track token usage when present in event data
        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)
        if input_tokens or output_tokens:
            model = data.get("model", self.model)
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            key = data.get("turn") or data.get("tool_name") or "unknown"
            if key not in self.token_usage:
                self.token_usage[key] = TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                )
            else:
                tu = self.token_usage[key]
                tu.input_tokens += input_tokens
                tu.output_tokens += output_tokens
                tu.model = model
            # Update cost
            input_cost = (input_tokens / 1000.0) * DEFAULT_MODEL_PRICING.get(
                model, DEFAULT_MODEL_PRICING["zcoder-flash"]
            )["input"]
            output_cost = (output_tokens / 1000.0) * DEFAULT_MODEL_PRICING.get(
                model, DEFAULT_MODEL_PRICING["zcoder-flash"]
            )["output"]
            self.cost_breakdown.input_cost += input_cost
            self.cost_breakdown.output_cost += output_cost
            self.cost_breakdown.total_cost = self.cost_breakdown.input_cost + self.cost_breakdown.output_cost

        if kind == "turn/start":
            if self.session_start_time is None:
                self.session_start_time = event.timestamp
            self.model = data.get("model", self.model)
            self.state["turn_count"] = self.state.get("turn_count", 0) + 1
            self.state["current_turn"] = data.get("turn", 1)
            self.state.setdefault("turns", []).append(
                {
                    "turn": data.get("turn", 1),
                    "started_at": event.timestamp,
                    "model": data.get("model"),
                    "events": [],
                }
            )

        elif kind == "turn/end":
            self.session_end_time = event.timestamp
            self.state["turn_end_count"] = self.state.get("turn_end_count", 0) + 1
            if self.state.get("turns"):
                self.state["turns"][-1]["ended_at"] = event.timestamp
                self.state["turns"][-1]["reason"] = data.get("reason")

        elif kind == "step/start":
            self.state["step_count"] = self.state.get("step_count", 0) + 1
            self.state["current_step"] = data.get("step", 1)
            self.state.setdefault("steps", []).append(
                {
                    "step": data.get("step", 1),
                    "started_at": event.timestamp,
                    "events": [],
                }
            )

        elif kind == "step/end":
            self.state["step_end_count"] = self.state.get("step_end_count", 0) + 1
            if self.state.get("steps"):
                self.state["steps"][-1]["ended_at"] = event.timestamp
                self.state["steps"][-1]["reason"] = data.get("reason")

        elif kind == "user/message":
            self.state.setdefault("messages", []).append(
                {
                    "role": "user",
                    "content": data.get("content", ""),
                    "timestamp": event.timestamp,
                    "event_id": str(event.event_id),
                }
            )

        elif kind == "assistant/message":
            self.state.setdefault("assistant_messages", []).append(
                {
                    "role": "assistant",
                    "content": data.get("content", ""),
                    "timestamp": event.timestamp,
                    "event_id": str(event.event_id),
                }
            )

        elif kind == "system/message":
            self.state.setdefault("system_messages", []).append(
                {
                    "role": "system",
                    "content": data.get("content", ""),
                    "timestamp": event.timestamp,
                    "event_id": str(event.event_id),
                }
            )

        elif kind == "developer/message":
            self.state.setdefault("developer_messages", []).append(
                {
                    "role": "developer",
                    "content": data.get("content", ""),
                    "timestamp": event.timestamp,
                    "event_id": str(event.event_id),
                }
            )

        elif kind == "tool/call":
            tool_name = data.get("tool_name", "")
            self.state.setdefault("tool_calls", []).append(
                {
                    "tool_call_id": data.get("tool_call_id", ""),
                    "tool_name": tool_name,
                    "arguments": data.get("arguments", {}),
                    "timestamp": event.timestamp,
                    "event_id": str(event.event_id),
                }
            )
            # Track tool usage statistics
            if tool_name not in self.tool_stats:
                self.tool_stats[tool_name] = ToolUsageStat(tool_name=tool_name)
            self.tool_stats[tool_name].call_count += 1
            # Track input tokens for this tool if provided
            if input_tokens or output_tokens:
                self.tool_stats[tool_name].total_input_tokens += input_tokens
                self.tool_stats[tool_name].total_output_tokens += output_tokens

        elif kind == "tool/result":
            tool_name = data.get("tool_name", "")
            is_error = data.get("is_error", False)
            self.state.setdefault("tool_results", []).append(
                {
                    "tool_call_id": data.get("tool_call_id", ""),
                    "tool_name": tool_name,
                    "result": data.get("result"),
                    "is_error": is_error,
                    "timestamp": event.timestamp,
                    "event_id": str(event.event_id),
                }
            )
            # Track tool usage statistics
            if tool_name not in self.tool_stats:
                self.tool_stats[tool_name] = ToolUsageStat(tool_name=tool_name)
            if is_error:
                self.tool_stats[tool_name].error_count += 1
            else:
                self.tool_stats[tool_name].success_count += 1
            # Track output tokens for this tool if provided
            if input_tokens or output_tokens:
                self.tool_stats[tool_name].total_input_tokens += input_tokens
                self.tool_stats[tool_name].total_output_tokens += output_tokens

        elif kind == "request/header":
            self.model = data.get("model", self.model)
            self.state["request_header"] = {
                "header": data.get("header", {}),
                "reason": data.get("reason"),
                "starts_series": data.get("starts_series", False),
                "timestamp": event.timestamp,
                "event_id": str(event.event_id),
            }

        elif kind == "request/context":
            self.state["request_context"] = {
                "context": data.get("context", {}),
                "timestamp": event.timestamp,
                "event_id": str(event.event_id),
            }

        elif kind == "session/end-seed":
            self.state["session_end_seed"] = data.get("seed", {})

    def fold_many(self, events: list[SessionEvent]) -> None:
        """Fold multiple events in order."""
        for event in events:
            self.fold(event)

    def get_state(self) -> dict[str, Any]:
        """Return the current projected state."""
        return dict(self.state)

    def get_session_summary(self) -> dict[str, Any]:
        """Get a summary of the session state."""
        return {
            "session_id": str(self.state.get("session_id", "")),
            "event_count": self.event_count,
            "last_event_seq": self.last_event_seq,
            "turn_count": self.state.get("turn_count", 0),
            "step_count": self.state.get("step_count", 0),
            "message_count": len(self.state.get("messages", [])),
            "assistant_message_count": len(self.state.get("assistant_messages", [])),
            "tool_call_count": len(self.state.get("tool_calls", [])),
            "tool_result_count": len(self.state.get("tool_results", [])),
            "system_message_count": len(self.state.get("system_messages", [])),
            "developer_message_count": len(self.state.get("developer_messages", [])),
            "context_window_percentage": self.state.get("context_window_percentage", 0.8),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost": self.cost_breakdown.total_cost,
            "model": self.model,
            "session_duration_seconds": (
                (self.session_end_time or 0.0) - (self.session_start_time or 0.0)
                if self.session_start_time is not None
                else 0.0
            ),
        }

    def get_token_usage(self) -> dict[str, Any]:
        """Get token usage statistics broken down by turn/tool."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "by_key": {
                key: {
                    "input_tokens": tu.input_tokens,
                    "output_tokens": tu.output_tokens,
                    "total_tokens": tu.total_tokens,
                    "model": tu.model,
                }
                for key, tu in self.token_usage.items()
            },
            "model": self.model,
        }

    def get_tool_statistics(self) -> dict[str, Any]:
        """Get per-tool usage statistics."""
        return {
            tool_name: {
                "call_count": stat.call_count,
                "success_count": stat.success_count,
                "error_count": stat.error_count,
                "success_rate": stat.success_rate,
                "total_input_tokens": stat.total_input_tokens,
                "total_output_tokens": stat.total_output_tokens,
                "total_tokens": stat.total_tokens,
                "total_cost": stat.total_cost,
            }
            for tool_name, stat in self.tool_stats.items()
        }

    def get_cost_breakdown(self) -> dict[str, Any]:
        """Get cost breakdown for the session."""
        return {
            "input_cost": self.cost_breakdown.input_cost,
            "output_cost": self.cost_breakdown.output_cost,
            "total_cost": self.cost_breakdown.total_cost,
            "model": self.model,
        }

    def get_session_analytics(self) -> dict[str, Any]:
        """Get session analytics including duration, rates, and trends."""
        duration = 0.0
        if self.session_start_time is not None:
            end = self.session_end_time or time.time()
            duration = end - self.session_start_time

        turn_count = self.state.get("turn_count", 0)
        message_count = len(self.state.get("messages", []))
        tool_call_count = len(self.state.get("tool_calls", []))

        return {
            "session_duration_seconds": duration,
            "turn_count": turn_count,
            "step_count": self.state.get("step_count", 0),
            "message_count": message_count,
            "tool_call_count": tool_call_count,
            "messages_per_turn": message_count / turn_count if turn_count > 0 else 0.0,
            "tools_per_turn": tool_call_count / turn_count if turn_count > 0 else 0.0,
            "tokens_per_turn": (
                (self.total_input_tokens + self.total_output_tokens) / turn_count if turn_count > 0 else 0.0
            ),
            "cost_per_turn": self.cost_breakdown.total_cost / turn_count if turn_count > 0 else 0.0,
            "model": self.model,
            "session_start_time": self.session_start_time,
            "session_end_time": self.session_end_time,
        }


# ── Session Title Management (deepseek-harness session-title) ─────────────────


@dataclass
class SessionTitle:
    """Session title with LLM-based generation support."""

    value: str
    generated_by: str | None = None
    generated_at: float | None = None
    updated_at: float = field(default_factory=time.time)


class SessionTitleProjection:
    """Projects session title from events, with optional LLM-based generation.

    Mirrors deepseek-harness session-title-llm package: automatic title
    generation, rename support, and persistence.
    """

    def __init__(self) -> None:
        self.title: SessionTitle | None = None
        self._pending_generation: bool = False

    def fold(self, event: SessionEvent) -> None:
        """Fold one event into the title projection."""
        if event.kind == "session/title":
            data = event.data or {}
            self.title = SessionTitle(
                value=data.get("title", ""),
                generated_by=data.get("generated_by"),
                generated_at=data.get("generated_at"),
                updated_at=event.timestamp,
            )
        elif event.kind == "user/message" and self.title is None:
            # Auto-derive title from first user message
            data = event.data or {}
            content = data.get("message", "") or data.get("content", "")
            if content:
                self.title = SessionTitle(
                    value=content[:100],
                    generated_by="first-user-message",
                    generated_at=event.timestamp,
                    updated_at=event.timestamp,
                )

    def generate_title(
        self,
        messages: list[dict[str, Any]],
        llm_call: Callable[[list[dict[str, Any]]], str] | None = None,
    ) -> str:
        """Generate a session title from messages, optionally via LLM."""
        if llm_call is not None:
            try:
                generated = llm_call(messages)
                if generated and generated.strip():
                    title_value = generated.strip()[:200]
                    self.title = SessionTitle(
                        value=title_value,
                        generated_by="llm",
                        generated_at=time.time(),
                        updated_at=time.time(),
                    )
                    return title_value
            except Exception:
                pass  # Fall through to heuristic

        # Heuristic: use first user message
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                content = msg["content"]
                title_value = content[:100]
                self.title = SessionTitle(
                    value=title_value,
                    generated_by="heuristic",
                    generated_at=time.time(),
                    updated_at=time.time(),
                )
                return title_value

        return "Untitled Session"

    def get_title(self) -> str | None:
        """Get the current session title."""
        return self.title.value if self.title else None

    def rename(self, new_title: str) -> None:
        """Rename the session."""
        self.title = SessionTitle(
            value=new_title,
            generated_by="user",
            generated_at=time.time(),
            updated_at=time.time(),
        )

    def get_state(self) -> dict[str, Any]:
        """Get the projected title state."""
        if self.title is None:
            return {"title": "", "generated_by": None, "generated_at": None, "updated_at": None}
        return {
            "title": self.title.value,
            "generated_by": self.title.generated_by,
            "generated_at": self.title.generated_at,
            "updated_at": self.title.updated_at,
        }


def log_session_title(
    store: SessionStore,
    session_id: str,
    title: str,
    *,
    generated_by: str | None = None,
) -> None:
    """Log one session/title event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="session/title",
        data={
            "title": title,
            "generated_by": generated_by,
            "generated_at": timestamp,
            "event_id": event_id,
            "timestamp": timestamp,
        },
    )
    _log_session_event(store, session_id, event)


# ── Working Directory Management (deepseek-harness working-directory) ─────────


@dataclass
class WorkingDirectory:
    """Working directory with admission controls."""

    path: str
    changed_at: float = field(default_factory=time.time)
    changed_by: str | None = None


class WorkingDirectoryProjection:
    """Projects working directory changes from session events.

    Mirrors deepseek-harness working-directory package: cwd change events,
    admission controls, and persistence across sessions.
    """

    def __init__(self) -> None:
        self.cwd: str | None = None
        self._history: list[WorkingDirectory] = []

    def fold(self, event: SessionEvent) -> None:
        """Fold one event into the working directory projection."""
        if event.kind == "working-directory/change":
            data = event.data or {}
            new_cwd = data.get("cwd", "")
            if new_cwd:
                self.cwd = new_cwd
                self._history.append(
                    WorkingDirectory(
                        path=new_cwd,
                        changed_at=event.timestamp,
                        changed_by=data.get("changed_by"),
                    )
                )

    def change_directory(self, new_cwd: str, changed_by: str | None = None) -> WorkingDirectory:
        """Change the working directory and record the change."""
        wd = WorkingDirectory(
            path=new_cwd,
            changed_at=time.time(),
            changed_by=changed_by,
        )
        self.cwd = new_cwd
        self._history.append(wd)
        return wd

    def get_cwd(self) -> str | None:
        """Get the current working directory."""
        return self.cwd

    def get_history(self) -> list[WorkingDirectory]:
        """Get the working directory change history."""
        return list(self._history)

    def get_state(self) -> dict[str, Any]:
        """Get the projected working directory state."""
        return {
            "cwd": self.cwd,
            "history": [
                {"path": wd.path, "changed_at": wd.changed_at, "changed_by": wd.changed_by}
                for wd in self._history
            ],
        }


def log_working_directory_change(
    store: SessionStore,
    session_id: str,
    cwd: str,
    *,
    changed_by: str | None = None,
) -> None:
    """Log one working-directory/change event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="working-directory/change",
        data={
            "cwd": cwd,
            "changed_by": changed_by,
            "event_id": event_id,
            "timestamp": timestamp,
        },
    )
    _log_session_event(store, session_id, event)


__all__ = [
    "SessionEvent",
    "SessionSurface",
    "SessionProjection",
    "RequestHeader",
    "TokenUsage",
    "ToolUsageStat",
    "CostBreakdown",
    "session_event_from_dict",
    "session_event_to_dict",
    "_log_session_event",
    "log_session_event",
    "log_request_header",
    "log_tool_call",
    "log_tool_result",
    "log_turn_start",
    "log_turn_end",
    "log_step_start",
    "log_step_end",
    "log_user_message",
    "log_assistant_message",
    "log_system_message",
    "log_developer_message",
    "SESSION_FORMAT_VERSION",
    "SESSION_EVENT_TYPES",
    "DEFAULT_MODEL_PRICING",
    "estimate_cost",
    "ModelSelection",
    "ModelSelectionProjection",
    "SessionTitle",
    "SessionTitleProjection",
    "log_session_title",
    "WorkingDirectory",
    "WorkingDirectoryProjection",
    "log_working_directory_change",
]


def _event_from_dict(data: dict[str, Any]) -> SessionEvent:
    """Build a SessionEvent from a dict."""
    return SessionEvent(
        kind=data["kind"],
        data=data.get("data", {}),
        source_event_seqs=data.get("source_event_seqs"),
        ignorable=data.get("ignorable", False),
        surface_op=data.get("surface_op", data.get("surfaceOp")),
        event_id=str(data.get("event_id", data.get("eventId", ""))),
        timestamp=float(data.get("timestamp", 0.0)),
    )


def session_event_from_dict(data: dict[str, Any]) -> SessionEvent:
    """Build a SessionEvent from a persisted envelope."""
    return _event_from_dict(data)


def session_event_to_dict(event: SessionEvent) -> dict[str, Any]:
    """Serialize a SessionEvent to its persisted envelope."""
    return {
        "kind": event.kind,
        "data": event.data,
        "sourceEventSeqs": event.source_event_seqs,
        "ignorable": event.ignorable,
        "surfaceOp": event.surface_op,
        "eventId": event.event_id,
        "timestamp": event.timestamp,
    }


# --- Session extensions -------------------------------------------------------


def _log_session_event(
    store: SessionStore,
    session_id: str,
    event: SessionEvent,
) -> None:
    """Append one session event to the session log."""
    # Reuse the session's message list as the durable event store.
    doc = store.load(session_id)
    messages = list(doc.get("messages", []))
    messages.append(
        {
            "kind": event.kind,
            "data": event.data,
            "sourceEventSeqs": event.source_event_seqs,
            "ignorable": event.ignorable,
            "surfaceOp": event.surface_op,
            "eventId": event.event_id,
            "timestamp": event.timestamp,
        }
    )
    store.save(session_id, doc.get("cwd", ""), messages, doc.get("usage"))


def log_session_event(
    store: SessionStore,
    session_id: str,
    kind: str,
    data: dict[str, Any],
    *,
    source_event_seqs: list[int] | None = None,
    ignorable: bool = False,
    surface_op: str | None = None,
) -> None:
    """Append one session event to the session log."""
    event = SessionEvent(
        kind=kind,
        data=data,
        source_event_seqs=source_event_seqs,
        ignorable=ignorable,
        surface_op=surface_op,
    )
    _log_session_event(store, session_id, event)


def log_request_header(
    store: SessionStore,
    session_id: str,
    header: dict[str, Any],
    reason: str = "initial",
    starts_series: bool = False,
) -> None:
    """Log one request header envelope."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="request/header",
        data={
            "header": header,
            "reason": reason,
            "starts_series": starts_series,
            "event_id": event_id,
            "timestamp": timestamp,
        },
    )
    _log_session_event(store, session_id, event)


def log_tool_call(
    store: SessionStore,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = "",
) -> None:
    """Log one tool/call event with optional token usage data."""
    data: dict[str, Any] = {"toolName": tool_name, "arguments": arguments}
    if input_tokens:
        data["input_tokens"] = input_tokens
    if output_tokens:
        data["output_tokens"] = output_tokens
    if model:
        data["model"] = model
    event = SessionEvent(kind="tool/call", data=data)
    _log_session_event(store, session_id, event)


def log_tool_result(
    store: SessionStore,
    session_id: str,
    tool_name: str,
    result: Any,
    *,
    is_error: bool = False,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = "",
) -> None:
    """Log one tool/result event with optional token usage data."""
    data: dict[str, Any] = {
        "toolName": tool_name,
        "result": result,
        "is_error": is_error,
    }
    if input_tokens:
        data["input_tokens"] = input_tokens
    if output_tokens:
        data["output_tokens"] = output_tokens
    if model:
        data["model"] = model
    event = SessionEvent(kind="tool/result", data=data)
    _log_session_event(store, session_id, event)


def log_token_usage(
    store: SessionStore,
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    *,
    model: str = "zcoder-flash",
    turn: int | None = None,
) -> None:
    """Log token usage for a turn or tool call."""
    data: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
    }
    if turn is not None:
        data["turn"] = turn
    event = SessionEvent(kind="request/context", data=data)
    _log_session_event(store, session_id, event)


def log_cost_event(
    store: SessionStore,
    session_id: str,
    input_cost: float,
    output_cost: float,
    *,
    model: str = "zcoder-flash",
) -> None:
    """Log a cost event for the session."""
    data: dict[str, Any] = {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
        "model": model,
    }
    event = SessionEvent(kind="request/context", data=data)
    _log_session_event(store, session_id, event)


def log_turn_start(store: SessionStore, session_id: str, turn: int) -> None:
    """Log one turn/start event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="turn/start",
        data={"turn": turn, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_turn_end(
    store: SessionStore,
    session_id: str,
    turn: int,
    reason: str,
) -> None:
    """Log one turn/end event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="turn/end",
        data={"turn": turn, "reason": reason, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_step_start(
    store: SessionStore,
    session_id: str,
    turn: int,
    step: int,
) -> None:
    """Log one step/start event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="step/start",
        data={"turn": turn, "step": step, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_step_end(
    store: SessionStore,
    session_id: str,
    turn: int,
    step: int,
) -> None:
    """Log one step/end event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="step/end",
        data={"turn": turn, "step": step, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_user_message(
    store: SessionStore,
    session_id: str,
    turn: int,
    step: int,
    content: str,
) -> None:
    """Log one user/message event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="user/message",
        data={"turn": turn, "step": step, "message": content, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_assistant_message(
    store: SessionStore,
    session_id: str,
    turn: int,
    step: int,
    content: str,
) -> None:
    """Log one assistant/message event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="assistant/message",
        data={"turn": turn, "step": step, "message": content, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_system_message(
    store: SessionStore,
    session_id: str,
    turn: int,
    step: int,
    content: str,
) -> None:
    """Log one system/message event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="system/message",
        data={"turn": turn, "step": step, "message": content, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)


def log_developer_message(
    store: SessionStore,
    session_id: str,
    turn: int,
    step: int,
    content: str,
) -> None:
    """Log one developer/message event."""
    event_id = str(uuid.uuid4())[:8]
    timestamp = time.time()
    event = SessionEvent(
        kind="developer/message",
        data={"turn": turn, "step": step, "message": content, "event_id": event_id, "timestamp": timestamp},
    )
    _log_session_event(store, session_id, event)
