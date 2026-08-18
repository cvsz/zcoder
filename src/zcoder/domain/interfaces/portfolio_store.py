"""portfolio_store_interface.py — Abstract Interface for Portfolio Storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

from zcoder.domain.models.portfolio import EngineeringCampaign, ManagedRepository


class PortfolioStore(ABC):
    """Abstract base class for managed-repository and campaign storage."""

    @abstractmethod
    def add_repository(self, repo: ManagedRepository) -> None:
        """Persist a managed repository."""
        pass

    @abstractmethod
    def create_campaign(self, campaign: EngineeringCampaign) -> None:
        """Persist an engineering campaign."""
        pass
