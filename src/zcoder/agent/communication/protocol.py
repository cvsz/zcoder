"""
Agent communication protocol for Phase 17.

Defines the JSON-RPC 2.0 message format used for agent-to-agent communication.
Supports task offloading, agent discovery, and consensus operations.

Message lifecycle
-----------------
1. ``create_request`` / ``create_response`` / ``create_notification`` /
   ``create_error`` build messages with correct ``type`` values.
2. ``message.to_dict()`` / ``message.to_json()`` serialize a message to the
   wire format; ``type`` is written as its lowercase name (``"request"``,
   ``"response"``, ``"notification"`` or ``"error"``).
3. ``parse_message`` validates the wire format against the JSON-RPC 2.0 spec
   and returns the matching RPC* subclass. Malformed input raises
   :class:`ProtocolError` instead of silently returning an half-populated
   message.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

JSONRPC_VERSION = "2.0"


class ProtocolError(ValueError):
    """Raised when a wire message is not valid JSON-RPC 2.0."""


class MessageType(Enum):
    """Types of JSON-RPC messages between agents."""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


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

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire value of every supported operation."""
        return [member.value for member in cls]

    @classmethod
    def from_value(cls, value: str) -> Operation:
        """Resolve an operation from its wire value."""
        try:
            return cls(value)
        except ValueError as exc:
            raise ProtocolError(f"Unknown operation: {value!r}") from exc


def _json_default(obj: Any) -> Any:
    """JSON serializer for values dataclasses cannot encode natively."""
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@dataclass
class JSONRPCMessage:
    """Base JSON-RPC 2.0 message structure."""

    jsonrpc: str = JSONRPC_VERSION
    id: str | None = None
    method: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: dict[str, Any] | None = None
    type: MessageType | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this message to a plain JSON-serializable mapping."""
        data = asdict(self)
        if data["type"] is not None:
            data["type"] = str(data["type"].value)  # MessageType stored as its wire value
        return data

    def to_json(self) -> str:
        """Serialize message to JSON string."""
        return json.dumps(self.to_dict(), default=_json_default)

    def model_dump_json(self) -> str:
        """Pydantic-compatible alias for to_json."""
        return self.to_json()


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


@dataclass
class RPCNotification(JSONRPCMessage):
    """A JSON-RPC notification message (no response expected)."""

    def __post_init__(self) -> None:
        self.type = MessageType.NOTIFICATION
        self.id = None  # Notifications don't have an ID


@dataclass
class RPCError(JSONRPCMessage):
    """A JSON-RPC error message.

    The structured error payload lives in ``self.error`` (``code`` /
    ``message`` / ``data`` per JSON-RPC 2.0). The ``code``, ``message`` and
    ``data`` properties are convenience aliases over that payload.
    """

    def __post_init__(self) -> None:
        self.type = MessageType.ERROR
        if self.error is None:
            self.error = {"code": -32600, "message": "Invalid request", "data": None}
        else:
            # Normalize the error payload so code/message/data are always present.
            self.error = {
                "code": int(self.error.get("code", -32600)),
                "message": str(self.error.get("message", "Invalid request")),
                "data": self.error.get("data"),
            }

    @property
    def code(self) -> int:
        """JSON-RPC error code."""
        return int((self.error or {}).get("code", -32600))

    @property
    def message(self) -> str:
        """Human-readable error message."""
        return str((self.error or {}).get("message", "Invalid request"))

    @property
    def data(self) -> Any:
        """Optional error-specific data."""
        return (self.error or {}).get("data")


def create_request(
    method: str,
    params: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> RPCRequest:
    """Create a new RPC request message."""
    if not method:
        raise ProtocolError("JSON-RPC request requires a non-empty method")
    return RPCRequest(method=method, params=params or {}, id=message_id)


def create_response(
    result: Any = None,
    error: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> RPCResponse:
    """Create a new RPC response message."""
    if result is not None and error is not None:
        raise ProtocolError("JSON-RPC response cannot carry both result and error")
    return RPCResponse(result=result, error=error, id=message_id)


def create_notification(
    method: str,
    params: dict[str, Any] | None = None,
) -> RPCNotification:
    """Create a new RPC notification message."""
    if not method:
        raise ProtocolError("JSON-RPC notification requires a non-empty method")
    return RPCNotification(method=method, params=params or {})


def create_error(
    code: int = -32600,
    message: str = "Invalid request",
    data: Any = None,
    message_id: str | None = None,
) -> RPCError:
    """Create a new RPC error message."""
    return RPCError(id=message_id, error={"code": code, "message": message, "data": data})


def parse_message(data: str | dict[str, Any]) -> JSONRPCMessage:
    """Parse and validate a JSON-RPC 2.0 message.

    Args:
        data: Either a JSON string or the already-decoded mapping.

    Returns:
        The matching RPC* subclass instance.

    Raises:
        ProtocolError: If the payload is structurally invalid JSON-RPC 2.0.
    """
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"Invalid JSON-RPC payload: {exc}") from exc
    else:
        parsed = data

    if not isinstance(parsed, dict):
        raise ProtocolError(f"JSON-RPC payload must be an object, got {type(parsed).__name__}")

    if parsed.get("jsonrpc") != JSONRPC_VERSION:
        raise ProtocolError(f"Expected jsonrpc == {JSONRPC_VERSION!r}, got {parsed.get('jsonrpc')!r}")

    method = parsed.get("method")
    params = parsed.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ProtocolError("JSON-RPC params must be an object")

    if "id" not in parsed and method is not None:
        msg_type = MessageType.NOTIFICATION
    elif method is not None:
        msg_type = MessageType.REQUEST
    elif parsed.get("error") is not None:
        msg_type = MessageType.ERROR
    else:
        msg_type = MessageType.RESPONSE

    message_id = parsed.get("id")
    result = parsed.get("result")
    error = parsed.get("error")

    if msg_type is MessageType.REQUEST:
        message: JSONRPCMessage = RPCRequest(
            jsonrpc=JSONRPC_VERSION,
            id=message_id,
            method=method,
            params=params,
            result=result,
            error=error,
        )
    elif msg_type is MessageType.NOTIFICATION:
        message = RPCNotification(
            jsonrpc=JSONRPC_VERSION,
            id=None,
            method=method,
            params=params,
            result=result,
            error=error,
        )
    elif msg_type is MessageType.ERROR:
        message = RPCError(
            jsonrpc=JSONRPC_VERSION,
            id=message_id,
            method=method,
            params=params,
            result=result,
            error=error,
        )
    else:
        message = RPCResponse(
            jsonrpc=JSONRPC_VERSION,
            id=message_id,
            method=method,
            params=params,
            result=result,
            error=error,
        )
    # Normalize params so explicit wire payloads round-trip deterministically.
    if parsed.get("params") is None:
        message.params = {}
    return message
