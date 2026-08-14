"""intelligence_models.py — Signals and recommendations for autonomous maintenance."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class SignalType(str, enum.Enum):
    CI_FAILURE = "CI_FAILURE"
    DEPENDENCY_OUTDATED = "DEPENDENCY_OUTDATED"
    SECURITY_FINDING = "SECURITY_FINDING"


@dataclass
class MaintenanceSignal:
    id: str = field(default_factory=lambda: f"sig_{uuid.uuid4().hex}")
    repository: str = ""
    type: SignalType = SignalType.CI_FAILURE
    severity: str = "medium"
    source: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_at: float = field(default_factory=time.time)


@dataclass
class MaintenanceRecommendation:
    id: str = field(default_factory=lambda: f"rec_{uuid.uuid4().hex}")
    repository: str = ""
    type: str = ""
    priority: int = 1
    risk: str = "low"
    reason: str = ""
    evidence: list[MaintenanceSignal] = field(default_factory=list)
    status: str = "NEW"
