"""portfolio_scheduler.py — Dispatches campaign tasks to the EngineeringStore."""

from __future__ import annotations

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.interfaces.portfolio_store import PortfolioStore
from zcoder.domain.models.engineering import EngineeringTask
from zcoder.domain.models.portfolio import EngineeringCampaign


class PortfolioScheduler:
    def __init__(self, portfolio_store: PortfolioStore, eng_store: EngineeringStore):
        self.portfolio_store = portfolio_store
        self.eng_store = eng_store

    def plan_campaign(self, campaign: EngineeringCampaign) -> list[str]:
        task_ids = []
        for repo_id in campaign.repositories:
            task = EngineeringTask(task_description=f"Campaign {campaign.name} on repo {repo_id}")
            self.eng_store.save_task(task)
            task_ids.append(task.id)
        return task_ids
