"""Agent-to-Agent Communication Protocol for Phase 17.

Provides inter-agent communication capabilities including:
- JSON-RPC message format for standardized messaging
- Agent discovery and registry service
- Distributed task offloading
- Consensus protocols
"""

from zcoder.agent.communication.offloader import OffloadResult, OffloadStatus, TaskOffloader
from zcoder.agent.communication.protocol import (
    AgentMessage,
    MessageType,
    Operation,
    deserialize_message,
    make_notification,
    make_request,
    make_response,
    serialize_message,
)
from zcoder.agent.communication.registry import (
    AgentDescription,
    AgentRegistry,
    RegistryState,
    create_default_registry,
)

__all__ = [
    "AgentMessage",
    "MessageType",
    "Operation",
    "make_request",
    "make_response",
    "make_notification",
    "serialize_message",
    "deserialize_message",
    "AgentRegistry",
    "AgentDescription",
    "RegistryState",
    "create_default_registry",
    "OffloadResult",
    "TaskOffloader",
    "OffloadStatus",
]
