"""
zcoder.tools.registry — Tool registry with effect-based registration.

Tool registrations are effects (Registrations Are Effects pattern, Section 4.2).
Plugins call register_tool() at load time, and the registry returns a
disposer that unregisters the tool when the plugin unloads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from zcoder.tools.definition import ToolError, ToolProtocol


class ToolRegistry:
    """Registry of tool implementations keyed by tool name.

    Tools are registered as effects — plugins call register_tool() at load
    time and receive a disposer that unregisters the tool on plugin unload.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolProtocol] = {}
        self._disposers: list[Callable[[], None]] = []

    def register_tool(self, tool: ToolProtocol) -> Callable[[], None]:
        """Register a tool implementation as an effect.

        @param tool - tool implementation conforming to ToolProtocol
        @returns disposer function that unregisters the tool when called
        """
        if tool.name in self._tools:
            raise ToolError(
                f"Tool '{tool.name}' is already registered",
                tool=tool.name,
                details={"existing": self._tools[tool.name].__class__.__name__},
            )
        self._tools[tool.name] = tool

        def disposer() -> None:
            self._tools.pop(tool.name, None)

        self._disposers.append(disposer)
        return disposer

    def get_tool(self, name: str) -> ToolProtocol | None:
        """Get a tool by name, or None if not registered."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return sorted(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool by name. Returns True if unregistered."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get JSON Schema definitions for all registered tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]


# Default registry — plugins and consumers share this instance.
registry = ToolRegistry()


def register_tool(tool: ToolProtocol) -> Callable[[], None]:
    """Register a tool as an effect on the global registry.

    Call this from plugin bootstrap code (Registrations Are Effects pattern).
    Returns a disposer that unregisters the tool when called.
    """
    return registry.register_tool(tool)


__all__ = [
    "ToolRegistry",
    "registry",
    "register_tool",
]
