"""policy_engine.py — Policy-as-Code Engine for ZCoder Enterprise.

Provides:
  • PolicyDecision with allow/deny and rich Obligations (require_approval, sandbox, max_budget)
  • Policy versioning, hashing, and effective timestamp tracking
  • Non-mutating policy explanation and dry-run evaluation
  • Unit-tested policy evaluator with fail-closed security guarantees
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any

from zcoder.domain.models.tenant import RequestContext


@dataclasses.dataclass
class PolicyObligation:
    type: str  # require_approval | require_sandbox | max_budget | allowed_runtime | deny_secret_access
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class PolicyDecision:
    allow: bool
    reason: str
    obligations: list[PolicyObligation] = dataclasses.field(default_factory=list)
    policy_version: str = "1.0.0"
    policy_hash: str = ""


@dataclasses.dataclass
class PolicyRule:
    id: str
    action_pattern: str  # e.g. "job.*", "repo.manage"
    condition: str  # pythonic boolean expr or rule type
    effect: str  # ALLOW | DENY
    obligations: list[PolicyObligation] = dataclasses.field(default_factory=list)


class EnterprisePolicyEngine:
    """Evaluates fine-grained access control policies and produces decisions with obligations."""

    def __init__(self, organization_id: str, version: str = "1.0.0"):
        self.organization_id = organization_id
        self.version = version
        self.rules: list[PolicyRule] = []
        self._compute_hash()

    def _compute_hash(self) -> None:
        # Hash rule *contents*, not just ids. Two engines with the same ids
        # but different patterns/conditions/effects must not collide.
        parts: list[str] = []
        for rule in sorted(self.rules, key=lambda r: (r.id, r.action_pattern)):
            parts.append(json.dumps(dataclasses.asdict(rule), sort_keys=True, default=str))
        raw = f"{self.organization_id}:{self.version}:" + "|".join(parts)
        self.policy_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def add_rule(self, rule: PolicyRule) -> None:
        self.rules.append(rule)
        self._compute_hash()

    def evaluate(self, ctx: RequestContext, action: str, resource: dict[str, Any]) -> PolicyDecision:
        """Evaluate action against policies. Fails closed (default DENY)."""
        ctx.validate_tenant_access(self.organization_id)

        # Baseline permission check
        if not ctx.has_permission(action):
            return PolicyDecision(
                allow=False,
                reason=f"Principal lacks role permission for '{action}'",
                policy_version=self.version,
                policy_hash=self.policy_hash,
            )

        # Check explicit rules. A rule only fires when BOTH its action
        # pattern and its condition match. A condition that cannot be
        # evaluated is fail-closed: deny instead of silently matching.
        obligations: list[PolicyObligation] = []
        for rule in self.rules:
            if not self._matches_action(rule.action_pattern, action):
                continue
            matched = self._matches_condition(rule.condition, resource)
            if matched is None:
                return PolicyDecision(
                    allow=False,
                    reason=f"Policy rule '{rule.id}' has an unevaluatable condition; denying",
                    policy_version=self.version,
                    policy_hash=self.policy_hash,
                )
            if not matched:
                continue
            if rule.effect == "DENY":
                return PolicyDecision(
                    allow=False,
                    reason=f"Explicitly denied by policy rule '{rule.id}'",
                    policy_version=self.version,
                    policy_hash=self.policy_hash,
                )
            if rule.effect == "ALLOW":
                obligations.extend(rule.obligations)

        # Extra risk obligations (e.g. untrusted repo requires sandbox)
        if resource.get("trust_level") == "UNTRUSTED":
            obligations.append(PolicyObligation(type="require_sandbox"))
        if resource.get("risk_level") == "high":
            obligations.append(PolicyObligation(type="require_approval", parameters={"min_approvers": 1}))

        return PolicyDecision(
            allow=True,
            reason="Authorized by organization enterprise policy",
            obligations=obligations,
            policy_version=self.version,
            policy_hash=self.policy_hash,
        )

    def explain(self, ctx: RequestContext, action: str, resource: dict[str, Any]) -> dict[str, Any]:
        """Explain policy evaluation without mutating any state."""
        decision = self.evaluate(ctx, action, resource)
        return {
            "organization_id": self.organization_id,
            "principal_id": ctx.principal_id,
            "action": action,
            "allow": decision.allow,
            "reason": decision.reason,
            "obligations": [{"type": o.type, "params": o.parameters} for o in decision.obligations],
            "policy_version": decision.policy_version,
            "policy_hash": decision.policy_hash,
        }

    def _matches_action(self, pattern: str, action: str) -> bool:
        if pattern == "*" or pattern == action:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return action.startswith(prefix + ".")
        return False

    # ── Condition evaluation (safe mini-parser, never eval()) ──────────

    _CONSIDERED_OPS = ("==", "!=", ">=", "<=", ">", "<", "=", " in ", " contains ")

    def _matches_condition(self, condition: str, resource: dict[str, Any]) -> bool | None:
        """Evaluate a rule condition against resource fields.

        Returns True/False, or None when the expression is not in the
        supported grammar (callers treat None as fail-closed deny).

        Supported: ``true``/``false``/empty, ``key <op> value`` with
        ``==, !=, >=, <=, >, <, =, in, contains``, ``key`` truthiness,
        and ``not``/`` and ``/`` or `` combinations thereof.
        """
        text = (condition or "").strip()
        if text in ("", "true", "True", "always"):
            return True
        if text in ("false", "False", "never"):
            return False
        try:
            if " or " in text:
                return any(self._matches_single(part, resource) for part in text.split(" or "))
            if " and " in text:
                return all(self._matches_single(part, resource) for part in text.split(" and "))
            return self._matches_single(text, resource)
        except (ValueError, TypeError, AttributeError):
            return None

    def _matches_single(self, expr: str, resource: dict[str, Any]) -> bool:
        text = expr.strip()
        if not text:
            raise ValueError("empty condition term")
        negate = False
        if text.startswith("not "):
            negate = True
            text = text[4:].strip()
        result = self._eval_term(text, resource)
        return (not result) if negate else result

    def _eval_term(self, text: str, resource: dict[str, Any]) -> bool:
        for op in self._CONSIDERED_OPS:
            if op in text:
                lhs, rhs = text.split(op, 1)
                key = lhs.strip()
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", key):
                    raise ValueError(f"bad condition key: {key!r}")
                lhs_value = self._lookup(key, resource)
                rhs_value = self._parse_scalar(rhs)
                if op in ("in",):
                    return lhs_value in (
                        rhs_value if isinstance(rhs_value, (list, tuple, set)) else {rhs_value}
                    )
                if op.strip() == "contains":
                    return isinstance(lhs_value, (str, list, tuple, set)) and rhs_value in lhs_value
                if op == "==":
                    return lhs_value == rhs_value
                if op == "!=":
                    return lhs_value != rhs_value
                if op == "=":
                    return lhs_value == rhs_value
                if not isinstance(lhs_value, (int, float)) or not isinstance(rhs_value, (int, float)):
                    raise ValueError(f"numeric comparison needs numbers: {text!r}")
                if op == ">":
                    return lhs_value > rhs_value
                if op == "<":
                    return lhs_value < rhs_value
                if op == ">=":
                    return lhs_value >= rhs_value
                if op == "<=":
                    return lhs_value <= rhs_value
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", text):
            return bool(self._lookup(text, resource))
        raise ValueError(f"unsupported condition: {text!r}")

    @staticmethod
    def _lookup(key: str, resource: dict[str, Any]) -> Any:
        current: Any = resource
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"condition key missing: {key!r}")
            current = current[part]
        return current

    @staticmethod
    def _parse_scalar(raw: str) -> Any:
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            items = [part.strip().strip("'\"") for part in s[1:-1].split(",") if part.strip()]
            # Try numeric items, else keep strings.
            out: list[Any] = []
            for item in items:
                try:
                    out.append(float(item) if "." in item else int(item))
                except ValueError:
                    out.append(item)
            return out
        if s in ("null", "None"):
            return None
        if s in ("true", "True"):
            return True
        if s in ("false", "False"):
            return False
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            return s[1:-1]
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            return s
