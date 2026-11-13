"""Hook event definitions for zcoder plugin system.

Compatible with claude-code's 30+ event types plus zcoder-specific events.
"""

from enum import StrEnum
from typing import Final


class HookEvent(StrEnum):
    """All supported hook events in tier precedence order."""

    # Session lifecycle
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    SESSION_COMPACT = "session.compact"
    SESSION_RESUME = "session.resume"
    SESSION_APPEND = "session.append"

    # Prompt composition
    PROMPT_SUBMIT = "prompt.submit"
    PROMPT_COMPOSE = "prompt.compose"
    PROMPT_SECTION = "prompt.section"
    PROMPT_CONTEXT = "prompt.context"
    PROMPT_ATTACHMENT = "prompt.attachment"
    PROMPT_FILL = "prompt.fill"
    PROMPT_SUGGEST = "prompt.suggest"
    PROMPT_EDIT = "prompt.edit"
    PROMPT_READ = "prompt.read"

    # Tool operations
    TOOL_CALL = "tool.call"
    TOOL_CHECK = "tool.check"
    TOOL_DESCRIBE = "tool.describe"
    TOOL_REGISTER = "tool.register"
    TOOL_LIST = "tool.list"

    # Agent operations
    AGENT_OFFER = "agent.offer"
    AGENT_SPAWN = "agent.spawn"
    AGENT_REGISTER = "agent.register"
    AGENT_LIST = "agent.list"

    # Command operations
    COMMAND_RUN = "command.run"
    COMMAND_DESCRIBE = "command.describe"
    COMMAND_REGISTER = "command.register"
    COMMAND_LIST = "command.list"

    # UI rendering
    UI_RENDER = "ui.render"
    UI_SCROLL = "ui.scroll"
    UI_FOCUS = "ui.focus"
    UI_CLOSE = "ui.close"
    UI_LOG = "ui.log"
    UI_STATUS = "ui.status"
    UI_OPEN = "ui.open"
    UI_INVALIDATE = "ui.invalidate"
    UI_RESOLVE = "ui.resolve"

    # Skill integration
    SKILL_PROMPT = "skill.prompt"

    # Attribution
    ATTRIBUTION_TEXT = "attribution.text"

    # Settings
    SETTINGS_READ = "settings.read"

    # Environment
    ENV_GET = "env.get"
    ENV_SET = "env.set"

    # Plugin management
    PLUGIN_REGISTER = "plugin.register"

    # MCP
    MCP_CALL = "mcp.call"

    # Telemetry
    TELEMETRY_LOG = "telemetry.log"
    TELEMETRY_MARK = "telemetry.mark"

    # Config
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"

    # FS/HTTP/Process/Clock/Store/Model/Audio
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_LIST = "fs.list"
    FS_STAT = "fs.stat"
    HTTP_FETCH = "http.fetch"
    PROCESS_RUN = "process.run"
    CLOCK_AFTER = "clock.after"
    CLOCK_EVERY = "clock.every"
    CLOCK_NOW = "clock.now"
    CLOCK_SLEEP = "clock.sleep"
    STORE_GET = "store.get"
    STORE_SET = "store.set"
    STORE_DELETE = "store.delete"
    MODEL_CALL = "model.call"
    AUDIO_CALL = "audio.call"

    # Additional lifecycle events (F05-21 to F05-27)
    INSTRUCTIONS_LOADED = "instructions.loaded"
    CWD_CHANGED = "cwd.changed"
    FILE_CHANGED = "file.changed"
    DIRECTORY_ADDED = "directory.added"
    PRE_MODEL_SWITCH = "model.pre_switch"
    POST_MODEL_SWITCH = "model.post_switch"
    MESSAGE_DISPLAY = "message.display"

    # Classic hooks (backward compat with claude-code)
    CLASSIC_PRE_TOOL_USE = "classic.pre_tool_use"
    CLASSIC_POST_TOOL_USE = "classic.post_tool_use"
    CLASSIC_NOTIFICATION = "classic.notification"
    CLASSIC_STOP = "classic.stop"
    CLASSIC_SUBAGENT_START = "classic.subagent_start"
    CLASSIC_SUBAGENT_STOP = "classic.subagent_stop"
    CLASSIC_PRE_COMPACT = "classic.pre_compact"
    CLASSIC_POST_COMPACT = "classic.post_compact"
    CLASSIC_WORKTREE_CREATE = "classic.worktree_create"
    CLASSIC_WORKTREE_REMOVE = "classic.worktree_remove"
    CLASSIC_ELICITATION = "classic.elicitation"

    # User prompt submit (claude-code compatible)
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    STOP = "stop"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    NOTIFICATION = "notification"
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    WORKTREE_CREATE = "worktree_create"
    WORKTREE_REMOVE = "worktree_remove"
    ELICITATION = "elicitation"


# Events that can block (exit code 2 prevents action)
BLOCKING_EVENTS: Final[frozenset[HookEvent]] = frozenset(
    {
        HookEvent.TOOL_CHECK,
        HookEvent.PROMPT_SUBMIT,
        HookEvent.ENV_SET,
        HookEvent.TOOL_REGISTER,
        HookEvent.CLASSIC_PRE_TOOL_USE,
        HookEvent.CLASSIC_ELICITATION,
        HookEvent.CLASSIC_WORKTREE_CREATE,
        HookEvent.USER_PROMPT_SUBMIT,
        HookEvent.PRE_TOOL_USE,
        HookEvent.ELICITATION,
        HookEvent.WORKTREE_CREATE,
    }
)

# Events that continue past user tier (org-controlled)
ORG_CONTROLLED_EVENTS: Final[frozenset[HookEvent]] = frozenset(
    {
        HookEvent.CLASSIC_PRE_TOOL_USE,
        HookEvent.CLASSIC_POST_TOOL_USE,
        HookEvent.CLASSIC_NOTIFICATION,
        HookEvent.CLASSIC_STOP,
        HookEvent.CLASSIC_SUBAGENT_START,
        HookEvent.CLASSIC_SUBAGENT_STOP,
        HookEvent.CLASSIC_PRE_COMPACT,
        HookEvent.CLASSIC_POST_COMPACT,
        HookEvent.CLASSIC_WORKTREE_CREATE,
        HookEvent.CLASSIC_WORKTREE_REMOVE,
        HookEvent.CLASSIC_ELICITATION,
        HookEvent.PROMPT_SECTION,
        HookEvent.PROMPT_CONTEXT,
        HookEvent.PROMPT_ATTACHMENT,
        HookEvent.SKILL_PROMPT,
        HookEvent.ATTRIBUTION_TEXT,
        HookEvent.SESSION_APPEND,
        HookEvent.SESSION_COMPACT,
        HookEvent.SETTINGS_READ,
        HookEvent.TOOL_DESCRIBE,
        HookEvent.COMMAND_DESCRIBE,
        HookEvent.AGENT_OFFER,
        HookEvent.AGENT_SPAWN,
        HookEvent.TOOL_REGISTER,
        HookEvent.TOOL_LIST,
        HookEvent.TOOL_CHECK,
        HookEvent.UI_LOG,
        HookEvent.ENV_GET,
        HookEvent.ENV_SET,
        HookEvent.PLUGIN_REGISTER,
        HookEvent.USER_PROMPT_SUBMIT,
        HookEvent.PRE_TOOL_USE,
        HookEvent.POST_TOOL_USE,
        HookEvent.STOP,
        HookEvent.SUBAGENT_START,
        HookEvent.SUBAGENT_STOP,
        HookEvent.NOTIFICATION,
        HookEvent.PRE_COMPACT,
        HookEvent.POST_COMPACT,
        HookEvent.WORKTREE_CREATE,
        HookEvent.WORKTREE_REMOVE,
        HookEvent.ELICITATION,
        # F05-21 to F05-27
        HookEvent.INSTRUCTIONS_LOADED,
        HookEvent.CWD_CHANGED,
        HookEvent.FILE_CHANGED,
        HookEvent.DIRECTORY_ADDED,
        HookEvent.PRE_MODEL_SWITCH,
        HookEvent.POST_MODEL_SWITCH,
        HookEvent.MESSAGE_DISPLAY,
    }
)


def get_all_events() -> list[str]:
    """Get all event names as strings."""
    return [e.value for e in HookEvent]


def is_blocking(event: str) -> bool:
    """Check if an event can block."""
    try:
        return HookEvent(event) in BLOCKING_EVENTS
    except ValueError:
        return False


def is_org_controlled(event: str) -> bool:
    """Check if an event is org-controlled (continues past user tier)."""
    try:
        return HookEvent(event) in ORG_CONTROLLED_EVENTS
    except ValueError:
        return False
