"""Single place that assembles a CodeAgent from settings — used by the CLI, TUI and web GUI."""

from __future__ import annotations

from pathlib import Path

from zcoder.agent.codeagent.audit import AuditLog
from zcoder.agent.codeagent.hooks import Hooks
from zcoder.agent.codeagent.llm import LLM, LocalLLM
from zcoder.agent.codeagent.loop import AskFn, CodeAgent
from zcoder.agent.codeagent.memory import zcoder_home
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.settings import Settings, load_settings
from zcoder.agent.codeagent.skills import SkillRegistry
from zcoder.agent.codeagent.workspace import Workspace


def _load_mcp_configs(ws: Workspace) -> list:
    """Load MCP server configs from .mcp.json files in project and user scopes."""
    configs: list = []
    try:
        from zcoder.agent.codeagent.mcp_client import MCPServerConfig
    except ImportError:
        return configs

    # Project scope: <repo>/.mcp.json
    project_path = ws.root / ".mcp.json"
    if project_path.is_file():
        try:
            data = __import__("json").loads(project_path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {}) if isinstance(data, dict) else {}
            for name, entry in servers.items():
                if not isinstance(entry, dict):
                    continue
                cmd = entry.get("command")
                url = entry.get("url")
                etype = entry.get("type", "stdio" if cmd else "http")
                configs.append(
                    MCPServerConfig(
                        name=name,
                        type=etype,
                        command=cmd,
                        args=entry.get("args", []),
                        env=entry.get("env", {}),
                        url=url,
                        headers=entry.get("headers", {}),
                        timeout_ms=entry.get("timeout", 30000),
                        always_load=entry.get("alwaysLoad", False),
                        scope="project",
                        source=str(project_path),
                    )
                )
        except Exception:
            pass

    # User scope: ~/.zcoder/mcp.json
    from zcoder.agent.codeagent.memory import zcoder_home

    user_path = zcoder_home() / "mcp.json"
    if user_path.is_file():
        try:
            data = __import__("json").loads(user_path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {}) if isinstance(data, dict) else {}
            for name, entry in servers.items():
                if not isinstance(entry, dict):
                    continue
                cmd = entry.get("command")
                url = entry.get("url")
                etype = entry.get("type", "stdio" if cmd else "http")
                configs.append(
                    MCPServerConfig(
                        name=name,
                        type=etype,
                        command=cmd,
                        args=entry.get("args", []),
                        env=entry.get("env", {}),
                        url=url,
                        headers=entry.get("headers", {}),
                        timeout_ms=entry.get("timeout", 30000),
                        always_load=entry.get("alwaysLoad", False),
                        scope="user",
                        source=str(user_path),
                    )
                )
        except Exception:
            pass

    return configs


def build_agent(
    root: str | Path = ".",
    *,
    ask: AskFn | None = None,
    llm: LLM | None = None,
    settings: Settings | None = None,
    mode: str | None = None,
    allow_bypass: bool = False,
    extra_allow: list[str] | None = None,
    store: SessionStore | None = None,
    discover_model: bool = True,
) -> CodeAgent:
    """Create an agent for ``root``. ``allow_bypass`` is honoured only if managed policy does not forbid it."""
    ws = Workspace(Path(root).expanduser().resolve())
    cfg = settings or load_settings(ws.root)
    if llm is None:
        local = LocalLLM(model=cfg.model, temperature=cfg.temperature)
        if discover_model:
            local.discover_model()
        llm = local
    policy = PermissionPolicy(
        allow_rules=[*cfg.allow, *(extra_allow or [])],
        deny_rules=list(cfg.deny),
        allow_bypass=allow_bypass and not cfg.disable_bypass,
        workspace=ws,
    )
    wanted = mode or cfg.default_mode
    try:
        policy.set_mode(Mode(wanted))
    except ValueError:
        policy.set_mode(Mode.DEFAULT)
    except Exception:  # bypass requested but not permitted -> stay safe
        policy.set_mode(Mode.DEFAULT)
    audit_path = cfg.audit_log or None
    agent = CodeAgent(
        llm,
        ws,
        policy=policy,
        store=store or SessionStore(),
        ask=ask,
        context_window=cfg.context_window,
        max_steps=cfg.max_steps,
        audit=AuditLog(audit_path) if audit_path else None,
        hooks=Hooks(cfg.hooks, ws.root) if cfg.hooks else None,
        scrub_env=cfg.scrub_env,
        pass_env=tuple(cfg.pass_env),
    )
    agent.settings = cfg
    agent.skills = SkillRegistry(ws.root)
    agent.skills.discover()
    from zcoder.agent.codeagent.subagents import SubagentRegistry

    agent.subagents = SubagentRegistry(ws.root)
    agent.subagents.discover()

    # MCP client — load .mcp.json configs
    try:
        from zcoder.agent.codeagent.mcp_client import MCPClient

        mcp_client = MCPClient(ws.root)
        for mcp_config in _load_mcp_configs(ws):
            mcp_client.add_server(mcp_config)
        agent.mcp = mcp_client
    except ImportError:
        agent.mcp = None

    return agent


def default_audit_path() -> Path:
    return zcoder_home() / "audit.jsonl"
