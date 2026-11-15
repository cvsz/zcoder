"""
compliance.py — Compliance Report Generation

Provides compliance reporting and audit trail generation for enterprise governance.
Integrates with the policy engine and audit log systems.

ZCoder Enterprise Edition v1.60.3
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zcoder.enterprise.audit import AuditLogger
from zcoder.enterprise.policy import PolicyEngine


class ComplianceReporter:
    """Generates compliance reports and audit trails for enterprise governance."""

    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        audit_logger: AuditLogger | None = None,
        base_dir: str | None = None,
    ):
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit_logger = audit_logger or AuditLogger()
        self.base_dir = base_dir or str(Path.home() / ".zcoder" / "compliance")

    def generate_report(
        self,
        tenant_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        include_policy_violations: bool = True,
        include_audit_summary: bool = True,
    ) -> dict[str, Any]:
        """Generate a comprehensive compliance report.

        Args:
            tenant_id: Optional tenant identifier for multi-tenant reports
            date_from: Start date filter (ISO format, inclusive)
            date_to: End date filter (ISO format, inclusive)
            include_policy_violations: Whether to include policy violation details
            include_audit_summary: Whether to include audit summary statistics

        Returns:
            Dict containing the compliance report
        """
        report: dict[str, Any] = {
            "report_id": f"comp-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            "generated_at": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "date_range": {
                "from": date_from,
                "to": date_to,
            },
            "summary": {},
            "policy_violations": [],
            "audit_summary": {},
        }

        # Build audit summary
        if include_audit_summary:
            audit_summary = self._build_audit_summary(
                date_from, date_to, tenant_id
            )
            report["audit_summary"] = audit_summary

        # Build policy violations
        if include_policy_violations:
            violations = self._build_policy_violations()
            report["policy_violations"] = violations

        # Build overall summary
        report["summary"] = self._build_summary(report)

        # Write report to file
        self._write_report(report)

        return report

    def _build_audit_summary(
        self, date_from: str | None, date_to: str | None, tenant_id: str | None
    ) -> dict[str, Any]:
        """Build audit summary statistics.

        Note: Full audit search integration requires AuditLogger.search_events()
        with date-range filtering. Currently returns empty summary structure.
        """
        return {
            "total_records": 0,
            "by_type": {},
            "by_severity": {},
            "by_status": {},
            "period_days": self._date_range_to_days(date_from, date_to),
        }

    def _build_policy_violations(self) -> list[dict[str, Any]]:
        """Build policy violations list."""
        violations = self.policy_engine.get_violations()

        result = []
        for violation in violations:
            result.append(
                {
                    "violation_id": violation["rule_id"],
                    "timestamp": violation["timestamp"],
                    "policy_id": violation["rule_id"],
                    "severity": "high",  # Default severity from policy engine
                    "description": f"Policy rule {violation['rule_id']} denied",
                }
            )

        return result

    def _build_summary(self, report: dict[str, Any]) -> dict[str, Any]:
        """Build overall compliance summary."""
        violations = report.get("policy_violations", [])
        audit_summary = report.get("audit_summary", {})

        total_violations = len(violations)
        unresolved = sum(1 for v in violations if not v.get("resolved", False))
        by_severity: dict[str, int] = {}
        for v in violations:
            sev = v.get("severity", "info")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "total_violations": total_violations,
            "unresolved_violations": unresolved,
            "resolution_rate": round(
                (total_violations - unresolved) / total_violations * 100, 2
            )
            if total_violations > 0
            else 100.0,
            "total_audit_records": audit_summary.get("total_records", 0),
            "high_severity_violations": by_severity.get("high", 0),
            "critical_severity_violations": by_severity.get("critical", 0),
        }

    def _write_report(self, report: dict[str, Any]) -> None:
        """Write compliance report to storage."""
        Path(self.base_dir).mkdir(parents=True, exist_ok=True)
        report_path = Path(self.base_dir) / f"report_{report['report_id']}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

    def _date_range_to_days(
        self, date_from: str | None, date_to: str | None
    ) -> int | None:
        """Convert date range strings to number of days."""
        if not date_from and not date_to:
            return None
        # Simplified: return None for full range, or could parse dates
        return None


def cmd_compliance_report(
    tenant_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_violations: bool = True,
    include_summary: bool = True,
) -> None:
    """CLI command to generate a compliance report."""
    reporter = ComplianceReporter()
    report = reporter.generate_report(
        tenant_id=tenant_id,
        date_from=date_from,
        date_to=date_to,
        include_policy_violations=include_violations,
        include_audit_summary=include_summary,
    )
    print(f"Compliance report generated: {report['report_id']}")
    print(f"  Total violations: {report['summary']['total_violations']}")
    print(f"  Unresolved: {report['summary']['unresolved_violations']}")
    print(f"  Resolution rate: {report['summary']['resolution_rate']}%")