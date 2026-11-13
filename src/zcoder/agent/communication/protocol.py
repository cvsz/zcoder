"""Agent-to-Agent JSON-RPC Protocol for Phase 17.

Provides a standardized message format for inter-agent communication,
enabling distributed task offloading, consensus, and session sharing.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MessageType(Enum):
    """Types of agent-to-agent messages."""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"


class Operation(Enum):
    """Types of operations that can be performed."""

    EXECUTE = "execute"
    QUERY = "query"
    TRANSFER = "transfer"
    CONSENSUS = "consensus"
    SYNC = "sync"


@dataclass
class AgentMessage:
    """Base agent message format."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.REQUEST
    operation: Operation = Operation.EXECUTE
    sender: str = ""
    recipient: str = ""
    timestamp: float = field(default_factory=time.time)
    target_agent: str = ""  # Target agent ID for routing
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None  # For matching requests/responses


def make_request(
    operation: Operation,
    target_agent: str,
    payload: dict[str, Any],
    recipient: str = "",
) -> AgentMessage:
    """Create a new agent request message."""
    return AgentMessage(
        type=MessageType.REQUEST,
        operation=operation,
        target_agent=target_agent,
        recipient=recipient,
        payload=payload,
    )


def make_response(
    correlation_id: str,
    success: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> AgentMessage:
    """Create a new agent response message."""
    return AgentMessage(
        type=MessageType.RESPONSE,
        operation=Operation.EXECUTE,
        correlation_id=correlation_id,
        payload={
            "success": success,
            "result": result or {},
            "error": error or "",
        },
    )


def make_notification(
    operation: Operation,
    payload: dict[str, Any],
    recipient: str = "",
) -> AgentMessage:
    """Create a new agent notification message."""
    return AgentMessage(
        type=MessageType.NOTIFICATION,
        operation=operation,
        recipient=recipient,
        payload=payload,
    )


def serialize_message(msg: AgentMessage) -> str:
    """Serialize an agent message to JSON string."""
    return json.dumps(asdict(msg))


def deserialize_message(text: str) -> AgentMessage:
    """Deserialize a JSON string to an AgentMessage."""
    data = json.loads(text)
    return AgentMessage(
        id=data.get("id", ""),
        type=MessageType(data.get("type", "request")),
        operation=Operation(data.get("operation", "execute")),
        sender=data.get("sender", ""),
        recipient=data.get("recipient", ""),
        timestamp=data.get("timestamp", 0.0),
        target_agent=data.get("target_agent", ""),
        payload=data.get("payload", {}),
        correlation_id=data.get("correlation_id"),
    )
