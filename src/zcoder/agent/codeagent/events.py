"""Typed events streamed by the agent loop to any front end."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TextDelta:
    text: str
    type: str = "text"


@dataclass
class ToolStart:
    id: str
    name: str
    args: dict[str, Any]
    type: str = "tool_start"


@dataclass
class ToolEnd:
    id: str
    name: str
    output: str
    is_error: bool = False
    diff: str | None = None
    type: str = "tool_end"


@dataclass
class TodoUpdate:
    todos: list[dict[str, Any]]
    type: str = "todos"


@dataclass
class UsageUpdate:
    prompt_tokens: int
    completion_tokens: int
    type: str = "usage"


@dataclass
class Notice:
    text: str
    level: str = "info"  # info | warn | error
    type: str = "notice"


@dataclass
class TurnDone:
    stop_reason: str  # end | interrupted | max_turns | error
    type: str = "done"


@dataclass
class PermissionRequest:
    id: str
    tool: str
    args: dict[str, Any]
    summary: str
    diff: str | None = None
    reason: str = ""
    type: str = "permission"


@dataclass
class Decision:
    """User's answer to a permission prompt."""

    behavior: str  # allow | allow_session | deny
    feedback: str = ""

    def __post_init__(self) -> None:
        if self.behavior not in {"allow", "allow_session", "deny"}:
            raise ValueError(f"invalid decision: {self.behavior}")


@dataclass
class ModeChanged:
    mode: str
    type: str = "mode"


Event = TextDelta | ToolStart | ToolEnd | TodoUpdate | UsageUpdate | Notice | TurnDone | ModeChanged


def event_to_dict(event: Any) -> dict[str, Any]:
    return asdict(event)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    last_prompt_tokens: int = 0
    requests: int = 0
    _extra: dict[str, Any] = field(default_factory=dict)

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.last_prompt_tokens = prompt
        self.requests += 1
