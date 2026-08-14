"""portfolio_store.py — Persistent storage for managed repositories and campaigns."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from portfolio_models import EngineeringCampaign, ManagedRepository

class PortfolioStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path.home() / ".zcoder" / "portfolio.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS managed_repositories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS engineering_campaigns (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    repositories TEXT NOT NULL
                )
            """)

    def add_repository(self, repo: ManagedRepository) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO managed_repositories VALUES (?, ?, ?, ?)",
                         (repo.id, repo.name, repo.local_path, repo.status.value))

    def create_campaign(self, campaign: EngineeringCampaign) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO engineering_campaigns VALUES (?, ?, ?, ?)",
                         (campaign.id, campaign.name, campaign.status.value, json.dumps(campaign.repositories)))
