"""Plugin manifest schema for zcoder.

Defines the structure and validation for plugin manifests (manifest.json).
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class HookConfig(BaseModel):
    """Configuration for a single hook."""

    matcher: str = "*"
    command: str
    timeout: int = Field(default=30, ge=1, le=300)

    # Pydantic's Field constraints handle clamping automatically
    # ge=1, le=300 will raise validation error for out-of-range values


class ToolConfig(BaseModel):
    """Configuration for a tool provided by the plugin."""

    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CommandConfig(BaseModel):
    """Configuration for a command provided by the plugin."""

    description: str
    handler: str


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server provided by the plugin."""

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class PluginManifest(BaseModel):
    """Complete plugin manifest."""

    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$")
    tier: str = "user"
    description: str = ""
    author: str = ""
    homepage: str = ""
    hooks: dict[str, list[HookConfig]] = Field(default_factory=dict)
    tools: dict[str, ToolConfig] = Field(default_factory=dict)
    commands: dict[str, CommandConfig] = Field(default_factory=dict)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        from zcoder.agent.plugin.tier import PluginTier

        try:
            PluginTier.from_string(v)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return v

    @field_validator("hooks")
    @classmethod
    def validate_hooks(cls, v: dict[str, list[HookConfig]]) -> dict[str, list[HookConfig]]:
        from zcoder.agent.plugin.events import HookEvent

        valid_events = {e.value for e in HookEvent}
        for event_name in v:
            if event_name not in valid_events:
                # Allow unknown events for forward compatibility but warn
                pass
        return v

    @model_validator(mode="after")
    def validate_mcp_tool_names(self) -> "PluginManifest":
        """Validate MCP tool names follow convention."""
        for server_name in self.mcp_servers:
            if not server_name.isidentifier():
                raise ValueError(f"MCP server name must be valid identifier: {server_name}")
        return self

    def get_hooks_for_event(self, event: str) -> list[HookConfig]:
        """Get all hooks registered for an event."""
        return self.hooks.get(event, [])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_file(cls, path: str) -> "PluginManifest":
        """Load manifest from JSON file."""
        import json

        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)
