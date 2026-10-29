"""codeagent — frontend-agnostic agentic coding engine (Claude Code-style).

Shared by the Textual TUI (`zcoder.interfaces.cli.agent_tui`) and the web GUI
(`webapp/backend/agent_api.py`). Contains no presentation logic.

    tools        Read / Write / Edit / Glob / Grep / LS / Bash / TodoWrite / ExitPlanMode
    permissions  default | acceptEdits | plan | bypass modes, allow/deny rules, hard-deny list
    loop         CodeAgent: streaming tool-use loop yielding typed events
    sessions     persisted, resumable conversations
    commands     slash commands shared by every front end
    memory       ZCODER.md / AGENTS.md project memory and @Makefile mentions
    llm          loopback-only OpenAI-compatible streaming client (llama-server)
"""

from zcoder.agent.codeagent.events import (
    Decision,
    Notice,
    PermissionRequest,
    TextDelta,
    TodoUpdate,
    ToolEnd,
    ToolStart,
    TurnDone,
    UsageUpdate,
)
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.workspace import Workspace

__all__ = [
    "CodeAgent",
    "Decision",
    "Mode",
    "Notice",
    "PermissionPolicy",
    "PermissionRequest",
    "SessionStore",
    "TextDelta",
    "TodoUpdate",
    "ToolEnd",
    "ToolStart",
    "TurnDone",
    "UsageUpdate",
    "Workspace",
]
