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
from zcoder.agent.codeagent.mcp_client import MCPClient, MCPServerConfig
from zcoder.agent.codeagent.mcp_server import MCPServer
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.review import ReviewFinding, UltraReview, format_review
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.skills import Skill, SkillRegistry, inject_dynamic_context, render_skill
from zcoder.agent.codeagent.subagents import (
    BUILTIN_SUBAGENTS,
    SubagentDef,
    SubagentRegistry,
    SubagentResult,
    SubagentRunner,
)
from zcoder.agent.codeagent.workflows import (
    WorkflowEngine,
    default_workflow_script,
    is_ultracode_prompt,
    strip_ultracode_keyword,
)
from zcoder.agent.codeagent.workspace import Workspace

__all__ = [
    "BUILTIN_SUBAGENTS",
    "CodeAgent",
    "Decision",
    "MCPClient",
    "MCPServer",
    "MCPServerConfig",
    "Mode",
    "Notice",
    "PermissionPolicy",
    "PermissionRequest",
    "ReviewFinding",
    "SessionStore",
    "Skill",
    "SkillRegistry",
    "SubagentDef",
    "SubagentRegistry",
    "SubagentResult",
    "SubagentRunner",
    "TextDelta",
    "TodoUpdate",
    "ToolEnd",
    "ToolStart",
    "TurnDone",
    "UltraReview",
    "UsageUpdate",
    "WorkflowEngine",
    "Workspace",
    "default_workflow_script",
    "format_review",
    "inject_dynamic_context",
    "is_ultracode_prompt",
    "render_skill",
    "strip_ultracode_keyword",
]
