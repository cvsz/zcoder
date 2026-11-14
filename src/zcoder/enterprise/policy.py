"""Enterprise Policy Engine for Phase 17.

Provides policy enforcement, RBAC integration, and compliance
governance for the ZCoder enterprise platform.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PolicyAction(Enum):
    """Allowed policy actions."""

    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"
    REQUIRE_APPROVAL = "require_approval"


class PolicyScope(Enum):
    """Policy scope levels."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    WORKSPACE = "workspace"
    USER = "user"


@dataclass
class PolicyRule:
    """A single policy rule."""

    id: str
    name: str
    description: str
    scope: PolicyScope
    conditions: dict[str, Any]
    action: PolicyAction
    created_at: float = field(default_factory=time.time)
    created_by: str = ""
    last_evaluated: float = 0.0
    enabled: bool = True


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    allowed: bool
    action: PolicyAction
    reason: str
    rule_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PolicyEngine:
    """Enterprise policy engine for governance and compliance."""

    def __init__(self) -> None:
        self._rules: dict[str, PolicyRule] = {}
        self._evaluation_count: int = 0
        self._deny_count: int = 0
        self._allow_count: int = 0

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule."""
        self._rules[rule.id] = rule
        logger.info(f"Added policy rule: {rule.id} - {rule.name}")

    def remove_rule(self, rule_id: str) -> None:
        """Remove a policy rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            logger.info(f"Removed policy rule: {rule_id}")

    def evaluate(
        self,
        context: dict[str, Any],
        rule_ids: list[str] | None = None,
    ) -> PolicyResult:
        """Evaluate policies against a given context."""
        self._evaluation_count += 1

        # Determine which rules to evaluate
        rules_to_evaluate = (
            [self._rules[rid] for rid in rule_ids if rid in self._rules]
            if rule_ids
            else list(self._rules.values())
        )

        # Filter to enabled rules
        enabled_rules = [r for r in rules_to_evaluate if r.enabled]

        # Evaluate each rule
        for rule in enabled_rules:
            self._last_evaluated = time.time()
            result = self._evaluate_rule(rule, context)
            if not result.allowed:
                self._deny_count += 1
                return result
            self._allow_count += 1

        # All rules passed
        return PolicyResult(
            allowed=True,
            action=PolicyAction.ALLOW,
            reason="All policy rules passed",
            rule_id="",
            metadata={"evaluated_rules": len(enabled_rules)},
        )

    def _evaluate_rule(self, rule: PolicyRule, context: dict[str, Any]) -> PolicyResult:
        """Evaluate a single policy rule against context."""
        conditions = rule.conditions

        # Check required conditions
        for condition_key, condition_value in conditions.items():
            actual_value = context.get(condition_key)

            # Type-specific comparison
            if not self._check_condition(actual_value, condition_value):
                # Rule condition not met - depending on policy logic,
                # this could mean deny or allow
                # For safety defaults, we'll allow if condition doesn't match
                # (condition not triggered)
                continue

        # If we get here, the rule's conditions are satisfied
        # Apply the rule's action
        return PolicyResult(
            allowed=rule.action == PolicyAction.ALLOW,
            action=rule.action,
            reason=rule.name,
            rule_id=rule.id,
            metadata={"scope": rule.scope.value, "condition_count": len(conditions)},
        )

    def _check_condition(self, actual: Any, expected: Any) -> bool:
        """Check if a condition matches."""
        if actual == expected:
            return True
        return False

    def get_statistics(self) -> dict[str, Any]:
        """Get policy engine statistics."""
        total = self._allow_count + self._deny_count
        return {
            "total_evaluations": self._evaluation_count,
            "allow_count": self._allow_count,
            "deny_count": self._deny_count,
            "allow_ratio": self._allow_count / total if total > 0 else 0.0,
            "rule_count": len(self._rules),
        }


# Global policy engine instance
_policy_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    """Get the global policy engine instance."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
