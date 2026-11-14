"""Enterprise Audit Log for Phase 17.

Provides immutable audit logging with append-only storage,
search capabilities, and integration with the compliance system.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""

    MODEL_CALL = "model_call"
    POLICY_EVALUATION = "policy_evaluation"
    AGENT_ACTION = "agent_action"
    FILE_OPERATION = "file_operation"
    AUTHENTICATION = "authentication"
    CONFIGURATION_CHANGE = "configuration_change"
    SECURITY_EVENT = "security_event"


class AuditEventStatus(Enum):
    """Status of an audit event."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


@dataclass
class AuditEvent:
    """A single audit event record."""

    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: float = field(default_factory=time.time)
    event_type: AuditEventType = AuditEventType.MODEL_CALL
    status: AuditEventStatus = AuditEventStatus.SUCCESS
    user_id: str = ""
    agent_id: str = ""
    session_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    compliance_tag: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "status": self.status.value,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "details": self.details,
            "outcome": self.outcome,
            "compliance_tag": self.compliance_tag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        """Create from dictionary."""
        event = cls(
            id=data.get("id", ""),
            timestamp=data.get("timestamp", time.time()),
            event_type=AuditEventType(data.get("event_type", "model_call")),
            status=AuditEventStatus(data.get("status", "success")),
            user_id=data.get("user_id", ""),
            agent_id=data.get("agent_id", ""),
            session_id=data.get("session_id", ""),
            details=data.get("details", {}),
            outcome=data.get("outcome", {}),
            compliance_tag=data.get("compliance_tag", ""),
        )
        return event


def uuid4():
    """Generate a UUID4 string."""
    import uuid

    return str(uuid.uuid4())


class AuditLogger:
    """Logger that writes immutable audit events to disk."""

    def __init__(self, log_dir: str | None = None) -> None:
        if log_dir is not None:
            self.log_dir: str = log_dir
        else:
            self.log_dir = os.getenv("ZCODER_AUDIT_DIR", "~/.zcoder/audit")
        self._lock = threading.Lock()
        self._log_file: str = ""
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        """Ensure the audit log directory exists."""
        expanded = os.path.expanduser(self.log_dir)
        os.makedirs(expanded, exist_ok=True)
        # Use a rotating single-file approach with locking
        self._log_file = os.path.join(expanded, "audit.log")

    def _append_event(self, event: AuditEvent) -> None:
        """Append an event to the audit log file."""
        with self._lock:
            with open(self._log_file, "a", encoding="utf-8") as f:
                # Use file lock for consistency
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(event.to_dict()) + "\n")
                    f.flush()
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def log_event(
        self,
        event_type: AuditEventType,
        user_id: str = "",
        agent_id: str = "",
        session_id: str = "",
        details: dict[str, Any] | None = None,
        outcome: dict[str, Any] | None = None,
        compliance_tag: str = "",
    ) -> None:
        """Log an audit event."""
        event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            details=details or {},
            outcome=outcome or {},
            compliance_tag=compliance_tag,
        )
        self._append_event(event)

    def search_events(
        self,
        event_type: AuditEventType | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        compliance_tag: str | None = None,
    ) -> list[AuditEvent]:
        """Search audit events with filters."""
        events: list[AuditEvent] = []

        if self._log_file and os.path.exists(self._log_file):
            with open(self._log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        event = AuditEvent.from_dict(data)

                        # Apply filters
                        if event_type and event.event_type != event_type:
                            continue
                        if user_id and event.user_id != user_id:
                            continue
                        if agent_id and event.agent_id != agent_id:
                            continue
                        if start_time and event.timestamp < start_time:
                            continue
                        if end_time and event.timestamp > end_time:
                            continue
                        if compliance_tag and event.compliance_tag != compliance_tag:
                            continue

                        events.append(event)
                    except (json.JSONDecodeError, KeyError):
                        continue

        return events


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
