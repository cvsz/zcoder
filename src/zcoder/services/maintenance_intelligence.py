"""maintenance_intelligence_service.py — Service to analyze signals and propose recommendations."""

from __future__ import annotations

from zcoder.domain.models.intelligence import MaintenanceRecommendation, MaintenanceSignal, SignalType


class MaintenanceIntelligenceService:
    def __init__(self):
        self.signals: list[MaintenanceSignal] = []

    def add_signal(self, signal: MaintenanceSignal):
        self.signals.append(signal)

    def generate_recommendations(self) -> list[MaintenanceRecommendation]:
        recommendations = []
        # Basic deterministic rules
        for signal in self.signals:
            if signal.type == SignalType.CI_FAILURE:
                recommendations.append(
                    MaintenanceRecommendation(
                        repository=signal.repository,
                        type="REPAIR_CI",
                        priority=2,
                        risk="medium",
                        reason=f"CI failure detected in source: {signal.source}",
                        evidence=[signal],
                    )
                )
            elif signal.type == SignalType.DEPENDENCY_OUTDATED:
                recommendations.append(
                    MaintenanceRecommendation(
                        repository=signal.repository,
                        type="PATCH_DEPENDENCY",
                        priority=1,
                        risk="low",
                        reason=f"Dependency outdated: {signal.evidence.get('package')}",
                        evidence=[signal],
                    )
                )
        return recommendations
