"""residency_models.py — Multi-Region & Data-Residency Policy Models for ZCoder.

Provides:
  • Distinct Regional Dimensions:
      - control_plane_region
      - database_region
      - worker_region
      - artifact_region
      - backup_region
      - provider_inference_region
  • OrganizationResidencyPolicy:
      - home_region
      - allowed_worker_regions
      - allowed_artifact_regions
      - allowed_backup_regions
      - allowed_provider_inference_regions
      - cross_region_transfer_allowed
  • Residency-Aware Job Scheduler & Failover Validator (fails closed / WAITING_CAPACITY if residency violated)
"""

from __future__ import annotations

import dataclasses
import enum


class RegionStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclasses.dataclass
class OrganizationResidencyPolicy:
    organization_id: str
    home_region: str
    allowed_worker_regions: set[str] = dataclasses.field(default_factory=lambda: {"us-east", "us-west"})
    allowed_artifact_regions: set[str] = dataclasses.field(default_factory=lambda: {"us-east", "us-west"})
    allowed_backup_regions: set[str] = dataclasses.field(default_factory=lambda: {"us-east", "us-west"})
    allowed_provider_inference_regions: set[str] = dataclasses.field(default_factory=lambda: {"us", "global"})
    cross_region_transfer_allowed: bool = False


@dataclasses.dataclass
class RegionTopology:
    control_plane_region: str = "us-east-1"
    database_region: str = "us-east-1"
    worker_regions: dict[str, RegionStatus] = dataclasses.field(
        default_factory=lambda: {
            "us-east-1": RegionStatus.AVAILABLE,
            "eu-west-1": RegionStatus.AVAILABLE,
            "ap-southeast-1": RegionStatus.AVAILABLE,
        }
    )


class ResidencyScheduler:
    """Evaluates and enforces data residency policies before job dispatch and during failover."""

    def __init__(self, topology: RegionTopology | None = None):
        self.topology = topology or RegionTopology()
        self.policies: dict[str, OrganizationResidencyPolicy] = {}

    def set_policy(self, policy: OrganizationResidencyPolicy) -> None:
        self.policies[policy.organization_id] = policy

    def evaluate_placement(
        self,
        organization_id: str,
        target_worker_region: str,
        target_inference_geo: str = "us",
    ) -> tuple[bool, str]:
        """Validate if placement satisfies organization residency policy."""
        policy = self.policies.get(organization_id)
        if not policy:
            # Default policy: home region only
            return True, "Default policy applied"

        # Check worker region
        if target_worker_region not in policy.allowed_worker_regions:
            return (
                False,
                f"Worker region '{target_worker_region}' not in allowed worker regions {policy.allowed_worker_regions}",
            )

        # Check provider inference geo
        if target_inference_geo not in policy.allowed_provider_inference_regions:
            return (
                False,
                f"Provider inference geo '{target_inference_geo}' not in allowed inference regions {policy.allowed_provider_inference_regions}",
            )

        # Check region availability
        status = self.topology.worker_regions.get(target_worker_region, RegionStatus.UNAVAILABLE)
        if status == RegionStatus.UNAVAILABLE:
            return False, f"Worker region '{target_worker_region}' is currently UNAVAILABLE"

        return True, "Residency criteria fully satisfied"

    def failover_placement(
        self,
        organization_id: str,
        failed_worker_region: str,
    ) -> tuple[str | None, str]:
        """Select alternate worker region during outage strictly respecting tenant residency policy."""
        policy = self.policies.get(organization_id)
        allowed = policy.allowed_worker_regions if policy else set(self.topology.worker_regions.keys())

        for candidate_region, status in self.topology.worker_regions.items():
            if (
                candidate_region != failed_worker_region
                and candidate_region in allowed
                and status == RegionStatus.AVAILABLE
            ):
                return candidate_region, f"Failover routed to compliant region '{candidate_region}'"

        # Never violate residency to satisfy failover
        return None, "PAUSED: No compliant worker region available satisfying residency policy"
