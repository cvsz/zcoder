"""
Agent communication module for Phase 17.

Provides JSON-RPC message format, agent discovery registry,
and distributed task offloading capabilities.
"""

from zcoder.agent.communication.offloader import (
    OffloadedTask,
    TaskOffloader,
    TaskState,
)
from zcoder.agent.communication.protocol import (
    JSONRPCMessage,
    MessageType,
    Operation,
    RPCError,
    RPCNotification,
    RPCRequest,
    RPCResponse,
    create_error,
    create_notification,
    create_request,
    create_response,
    parse_message,
)
from zcoder.agent.communication.registry import AgentInfo, AgentRegistry

__all__ = [
    "MessageType",
    "Operation",
    "JSONRPCMessage",
    "RPCRequest",
    "RPCResponse",
    "RPCNotification",
    "RPCError",
    "create_request",
    "create_response",
    "create_notification",
    "create_error",
    "parse_message",
    "AgentRegistry",
    "AgentInfo",
    "OffloadedTask",
    "TaskOffloader",
    "TaskState",
]