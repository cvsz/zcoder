"""portfolio_scheduler.py — Dispatches campaign tasks to the EngineeringStore."""

from __future__ import annotations

from engineering_models import EngineeringTask
from engineering_store_interface import EngineeringStore
from portfolio_models import EngineeringCampaign
from portfolio_store import PortfolioStore


class PortfolioScheduler:
    def __init__(self, portfolio_store: PortfolioStore, eng_store: EngineeringStore):
        self.portfolio_store = portfolio_store
        self.eng_store = eng_store

    def plan_campaign(self, campaign: EngineeringCampaign) -> List[str]:
        task_ids = []
        for repo_id in campaign.repositories:
            # Create a task for each repo
            task = EngineeringTask(task_description=f"Campaign {campaign.name} on repo {repo_id}")
            self.eng_store.save_task(task)
            task_ids.append(task.id)
        return task_ids
