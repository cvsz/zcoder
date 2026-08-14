"""portfolio_models.py — Repository Portfolio & Campaign Management Entities."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field


class RepoStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ManagedRepository:
    id: str = field(default_factory=lambda: f"repo_{uuid.uuid4().hex}")
    portfolio_id: str = ""
    name: str = ""
    local_path: str = ""
    status: RepoStatus = RepoStatus.DISCOVERED
    created_at: float = field(default_factory=time.time)


@dataclass
class EngineeringCampaign:
    id: str = field(default_factory=lambda: f"camp_{uuid.uuid4().hex}")
    name: str = ""
    status: CampaignStatus = CampaignStatus.DRAFT
    repositories: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
