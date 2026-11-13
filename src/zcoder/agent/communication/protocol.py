"""
Agent communication protocol for Phase 17.

Defines the JSON-RPC message format for agent-to-agent communication.
Enables distributed task offloading, discovery, and consensus protocols.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class MessageType(Enum):
    """Types of JSON-RPC messages between agents."""

    REQUEST = auto()
    RESPONSE = auto()
    NOTIFICATION = auto()
    ERROR = auto()


class Operation(Enum):
    """Operations supported in agent communication."""

    # Discovery
    DISCOVER = "discover"
    GET_CAPABILITIES = "get_capabilities"

    # Task offloading
    OFFLOAD = "offload"
    CANCEL_OFFLOAD = "cancel_offload"
    GET_TASK_STATUS = "get_task_status"
    CANCEL_TASK = "cancel_task"

    # Consensus
    PROPOSE = "propose"
    VOTE = "vote"
    ACCEPT = "accept"
    REJECT = "reject"

    # Session management
    SHARE_SESSION = "share_session"
    SYNC_STATE = "sync_state"


@dataclass
class JSONRPCMessage:
    """Base JSON-RPC 2.0 message structure."""

    jsonrpc: str = "2.0"
    id: str | None = None
    method: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: dict[str, Any] | None = None
    type: MessageType | None = None


@dataclass
class RPCRequest(JSONRPCMessage):
    """A JSON-RPC request message."""

    def __post_init__(self) -> None:
        self.type = MessageType.REQUEST
        if self.id is None:
            self.id = str(uuid.uuid4())


@dataclass
class RPCResponse(JSONRPCMessage):
    """A JSON-RPC response message."""

    def __post_init__(self) -> None:
        self.type = MessageType.RESPONSE
        if self.id is None and self.jsonrpc == "2.0":
            # ID must match request for correlation
            pass


@dataclass
class RPCNotification(JSONRPCMessage):
    """A JSON-RPC notification message (no response expected)."""

    def __post_init__(self) -> None:
        self.type = MessageType.NOTIFICATION
        self.id = None  # Notifications don't have an ID


@dataclass
class RPCError(JSONRPCMessage):
    """A JSON-RPC error message."""

    code: int = -32600
    message: str = "Invalid request"
    data: Any = None

    def __post_init__(self) -> None:
        self.type = MessageType.ERROR
        self.id = None


def create_request(
    method: str,
    params: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> RPCRequest:
    """Create a new RPC request message."""
    return RPCRequest(
        method=method,
        params=params or {},
        id=message_id,
    )


def create_response(
    result: Any = None,
    error: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> RPCResponse:
    """Create a new RPC response message."""
    return RPCResponse(
        result=result,
        error=error,
        id=message_id,
    )


def create_notification(
    method: str,
    params: dict[str, Any] | None = None,
) -> RPCNotification:
    """Create a new RPC notification message."""
    return RPCNotification(method=method, params=params or {})


def create_error(
    code: int = -32600,
    message: str = "Invalid request",
    data: Any = None,
    message_id: str | None = None,
) -> RPCError:
    """Create a new RPC error message."""
    return RPCError(
        code=code,
        message=message,
        data=data,
        id=message_id,
    )


def parse_message(data: str | dict[str, Any]) -> JSONRPCMessage:
    """Parse a JSON-RPC message from JSON data."""
    if isinstance(data, str):
        parsed = json.loads(data)
    else:
        parsed = data

    msg_type = parsed.get("type", "2.0")
    message = JSONRPCMessage(
        jsonrpc=parsed.get("jsonrpc", "2.0"),
        id=parsed.get("id"),
        method=parsed.get("method"),
        params=parsed.get("params", {}),
        result=parsed.get("result"),
        error=parsed.get("error"),
    )

    if msg_type == "2.0" or msg_type == "jsonrpc2":
        # Validate required fields for 2.0
        if message.method is None and message.result is None and message.error is None:
            # Notification (no method, result, or error)
            message.type = MessageType.NOTIFICATION

    return message