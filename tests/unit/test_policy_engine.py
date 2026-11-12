"""Tests for policy_engine.py — Policy-as-Code Engine."""

from __future__ import annotations

import pytest

from zcoder.domain.models.tenant import EnterpriseRole, RequestContext
from zcoder.domain.services.policy_engine import (
    EnterprisePolicyEngine,
    PolicyDecision,
    PolicyObligation,
    PolicyRule,
)


class TestPolicyObligation:
    """Tests for PolicyObligation dataclass."""

    def test_default_parameters(self) -> None:
        """Test default empty parameters dict."""
        obl = PolicyObligation(type="require_approval")
        assert obl.type == "require_approval"
        assert obl.parameters == {}

    def test_with_parameters(self) -> None:
        """Test with custom parameters."""
        obl = PolicyObligation(
            type="max_budget",
            parameters={"amount": 100.0, "currency": "USD"},
        )
        assert obl.parameters == {"amount": 100.0, "currency": "USD"}


class TestPolicyDecision:
    """Tests for PolicyDecision dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        decision = PolicyDecision(allow=True, reason="OK")
        assert decision.allow is True
        assert decision.reason == "OK"
        assert decision.obligations == []
        assert decision.policy_version == "1.0.0"
        assert decision.policy_hash == ""

    def test_with_obligations(self) -> None:
        """Test with obligations."""
        obl = PolicyObligation(type="require_sandbox")
        decision = PolicyDecision(allow=True, reason="OK", obligations=[obl])
        assert len(decision.obligations) == 1
        assert decision.obligations[0].type == "require_sandbox"


class TestPolicyRule:
    """Tests for PolicyRule dataclass."""

    def test_basic_rule(self) -> None:
        """Test basic rule creation."""
        rule = PolicyRule(
            id="rule1",
            action_pattern="job.*",
            condition="true",
            effect="ALLOW",
        )
        assert rule.id == "rule1"
        assert rule.action_pattern == "job.*"
        assert rule.condition == "true"
        assert rule.effect == "ALLOW"

    def test_rule_with_obligations(self) -> None:
        """Test rule with obligations."""
        obl = PolicyObligation(type="require_approval", parameters={"min_approvers": 2})
        rule = PolicyRule(
            id="rule2",
            action_pattern="repo.manage",
            condition="resource.trust_level == 'UNTRUSTED'",
            effect="ALLOW",
            obligations=[obl],
        )
        assert len(rule.obligations) == 1
        assert rule.obligations[0].parameters["min_approvers"] == 2


class TestEnterprisePolicyEngine:
    """Tests for EnterprisePolicyEngine."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )
        self.engine = EnterprisePolicyEngine(organization_id="org1")

    def test_init(self) -> None:
        """Test engine initialization."""
        assert self.engine.organization_id == "org1"
        assert self.engine.version == "1.0.0"
        assert self.engine.rules == []
        assert self.engine.policy_hash != ""

    def test_add_rule(self) -> None:
        """Test adding a rule."""
        rule = PolicyRule(
            id="test_rule",
            action_pattern="job.create",
            condition="true",
            effect="ALLOW",
        )
        self.engine.add_rule(rule)
        assert len(self.engine.rules) == 1
        assert self.engine.rules[0].id == "test_rule"

    def test_evaluate_allow_by_role_permission(self) -> None:
        """Test evaluation allows when role has permission."""
        # OPERATOR has job.create permission
        decision = self.engine.evaluate(self.ctx, "job.create", {})
        assert decision.allow is True
        assert "Authorized" in decision.reason

    def test_evaluate_deny_no_permission(self) -> None:
        """Test evaluation denies when role lacks permission."""
        # OPERATOR does NOT have org.manage permission
        decision = self.engine.evaluate(self.ctx, "org.manage", {})
        assert decision.allow is False
        assert "lacks role permission" in decision.reason

    def test_evaluate_explicit_deny_rule(self) -> None:
        """Test explicit DENY rule takes precedence."""
        deny_rule = PolicyRule(
            id="deny_job_create",
            action_pattern="job.create",
            condition="true",
            effect="DENY",
        )
        self.engine.add_rule(deny_rule)

        decision = self.engine.evaluate(self.ctx, "job.create", {})
        assert decision.allow is False
        assert "Explicitly denied" in decision.reason

    def test_evaluate_explicit_allow_rule_with_obligations(self) -> None:
        """Test explicit ALLOW rule adds obligations."""
        allow_rule = PolicyRule(
            id="allow_job_create",
            action_pattern="job.create",
            condition="true",
            effect="ALLOW",
            obligations=[PolicyObligation(type="require_sandbox")],
        )
        self.engine.add_rule(allow_rule)

        decision = self.engine.evaluate(self.ctx, "job.create", {})
        assert decision.allow is True
        assert len(decision.obligations) == 1
        assert decision.obligations[0].type == "require_sandbox"

    def test_evaluate_condition_match(self) -> None:
        """Test condition matching."""
        rule = PolicyRule(
            id="conditional",
            action_pattern="job.create",
            condition="priority == 'high'",
            effect="ALLOW",
            obligations=[PolicyObligation(type="require_approval")],
        )
        self.engine.add_rule(rule)

        # Condition matches
        decision = self.engine.evaluate(self.ctx, "job.create", {"priority": "high"})
        assert decision.allow is True
        assert len(decision.obligations) == 1

        # Condition doesn't match
        decision = self.engine.evaluate(self.ctx, "job.create", {"priority": "low"})
        assert decision.allow is True  # Role permission allows
        assert len(decision.obligations) == 0  # No obligation from rule

    def test_evaluate_condition_untrusted_repo_requires_sandbox(self) -> None:
        """Test UNTRUSTED trust_level adds sandbox obligation."""
        decision = self.engine.evaluate(self.ctx, "job.create", {"trust_level": "UNTRUSTED"})
        assert decision.allow is True
        assert any(o.type == "require_sandbox" for o in decision.obligations)

    def test_evaluate_condition_high_risk_requires_approval(self) -> None:
        """Test high risk_level adds approval obligation."""
        decision = self.engine.evaluate(self.ctx, "job.create", {"risk_level": "high"})
        assert decision.allow is True
        assert any(o.type == "require_approval" for o in decision.obligations)
        assert decision.obligations[0].parameters.get("min_approvers") == 1

    def test_explain_returns_detailed_dict(self) -> None:
        """Test explain method returns detailed explanation."""
        rule = PolicyRule(
            id="explain_rule",
            action_pattern="job.create",
            condition="true",
            effect="ALLOW",
            obligations=[PolicyObligation(type="require_sandbox")],
        )
        self.engine.add_rule(rule)

        explanation = self.engine.explain(self.ctx, "job.create", {})
        assert explanation["organization_id"] == "org1"
        assert explanation["principal_id"] == "user1"
        assert explanation["action"] == "job.create"
        assert explanation["allow"] is True
        assert explanation["reason"] == "Authorized by organization enterprise policy"
        assert len(explanation["obligations"]) == 1
        assert explanation["obligations"][0]["type"] == "require_sandbox"
        assert "policy_version" in explanation
        assert "policy_hash" in explanation

    def test_matches_action_wildcard(self) -> None:
        """Test action pattern matching with wildcard."""
        engine = EnterprisePolicyEngine("org1")
        assert engine._matches_action("*", "any.action") is True
        assert engine._matches_action("job.*", "job.create") is True
        assert engine._matches_action("job.*", "job.delete") is True
        assert engine._matches_action("job.*", "project.create") is False
        assert engine._matches_action("exact.match", "exact.match") is True
        assert engine._matches_action("exact.match", "different") is False

    def test_matches_condition_supported_operators(self) -> None:
        """Test condition evaluation with supported operators."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"count": 5, "name": "test", "tags": ["a", "b"], "enabled": True}

        # Equality
        assert engine._matches_condition("count == 5", resource) is True
        assert engine._matches_condition("count != 5", resource) is False
        assert engine._matches_condition("name == 'test'", resource) is True

        # Comparison
        assert engine._matches_condition("count > 3", resource) is True
        assert engine._matches_condition("count < 10", resource) is True
        assert engine._matches_condition("count >= 5", resource) is True
        assert engine._matches_condition("count <= 5", resource) is True

        # In (requires spaces around 'in')
        assert engine._matches_condition("name in ['test', 'other']", resource) is True
        assert engine._matches_condition("count in [5, 10]", resource) is True

        # Contains
        assert engine._matches_condition("tags contains 'a'", resource) is True
        assert engine._matches_condition("name contains 'es'", resource) is True

        # Truthiness
        assert engine._matches_condition("enabled", resource) is True
        # Missing key in truthiness check is fail-closed (returns None)
        assert engine._matches_condition("missing_key", resource) is None

    def test_matches_condition_logical_operators(self) -> None:
        """Test condition evaluation with logical operators."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"a": 1, "b": 2, "c": 3}

        assert engine._matches_condition("a == 1 and b == 2", resource) is True
        assert engine._matches_condition("a == 1 and b == 3", resource) is False
        assert engine._matches_condition("a == 1 or b == 3", resource) is True
        assert engine._matches_condition("a == 9 or b == 9", resource) is False
        assert engine._matches_condition("not a == 1", resource) is False
        assert engine._matches_condition("not a == 9", resource) is True

    def test_matches_condition_fail_closed_on_error(self) -> None:
        """Test fail-closed behavior on unevaluatable condition."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"count": 5}

        # Invalid key format
        assert engine._matches_condition("invalid-key == 5", resource) is None

        # Missing key
        assert engine._matches_condition("missing == 5", resource) is None

        # Type error in comparison
        assert engine._matches_condition("count > 'string'", resource) is None

    def test_evaluate_fail_closed_on_bad_condition(self) -> None:
        """Test evaluation fails closed when condition cannot be evaluated."""
        rule = PolicyRule(
            id="bad_condition",
            action_pattern="job.create",
            condition="invalid-condition-syntax",
            effect="ALLOW",
        )
        self.engine.add_rule(rule)

        decision = self.engine.evaluate(self.ctx, "job.create", {})
        assert decision.allow is False
        assert "unevaluatable condition" in decision.reason

    def test_policy_hash_changes_with_rules(self) -> None:
        """Test policy hash changes when rules change."""
        engine = EnterprisePolicyEngine("org1")
        hash1 = engine.policy_hash

        rule = PolicyRule(
            id="rule1",
            action_pattern="job.*",
            condition="true",
            effect="ALLOW",
        )
        engine.add_rule(rule)
        hash2 = engine.policy_hash

        assert hash1 != hash2

        # Same rules should produce same hash
        engine2 = EnterprisePolicyEngine("org1")
        engine2.add_rule(rule)
        assert engine2.policy_hash == hash2

    def test_evaluate_tenant_mismatch_raises(self) -> None:
        """Test evaluation fails with wrong tenant."""
        from zcoder.domain.models.tenant import CrossTenantViolationError

        wrong_ctx = RequestContext(
            principal_id="user1",
            organization_id="org2",  # Different org
            role=EnterpriseRole.OPERATOR,
        )
        with pytest.raises(CrossTenantViolationError):
            self.engine.evaluate(wrong_ctx, "job.create", {})

    def test_explain_tenant_mismatch_raises(self) -> None:
        """Test explain fails with wrong tenant."""
        from zcoder.domain.models.tenant import CrossTenantViolationError

        wrong_ctx = RequestContext(
            principal_id="user1",
            organization_id="org2",
            role=EnterpriseRole.OPERATOR,
        )
        with pytest.raises(CrossTenantViolationError):
            self.engine.explain(wrong_ctx, "job.create", {})

    def test_complex_condition_with_nested_keys(self) -> None:
        """Test condition evaluation with nested dictionary keys."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"job": {"priority": "high", "metadata": {"owner": "team1"}}}

        assert engine._matches_condition("job.priority == 'high'", resource) is True
        assert engine._matches_condition("job.metadata.owner == 'team1'", resource) is True
        assert engine._matches_condition("job.priority == 'low'", resource) is False

    def test_parse_scalar_various_formats(self) -> None:
        """Test _parse_scalar with various input formats."""
        engine = EnterprisePolicyEngine("org1")

        # Numbers
        assert engine._parse_scalar("42") == 42
        assert engine._parse_scalar("3.14") == 3.14

        # Strings
        assert engine._parse_scalar("'hello'") == "hello"
        assert engine._parse_scalar('"world"') == "world"

        # Booleans
        assert engine._parse_scalar("true") is True
        assert engine._parse_scalar("false") is False

        # Null
        assert engine._parse_scalar("null") is None
        assert engine._parse_scalar("None") is None

        # Lists
        assert engine._parse_scalar("[1, 2, 3]") == [1, 2, 3]
        assert engine._parse_scalar("['a', 'b']") == ["a", "b"]
        assert engine._parse_scalar("[1.5, 2.5]") == [1.5, 2.5]


class TestEnterprisePolicyEngineEdgeCases:
    """Edge case tests for EnterprisePolicyEngine."""

    def test_empty_condition_string(self) -> None:
        """Test empty condition string is treated as True."""
        engine = EnterprisePolicyEngine("org1")
        assert engine._matches_condition("", {}) is True

    def test_whitespace_condition(self) -> None:
        """Test whitespace-only condition is treated as True."""
        engine = EnterprisePolicyEngine("org1")
        assert engine._matches_condition("   ", {}) is True

    def test_always_true_keywords(self) -> None:
        """Test 'true', 'True', 'always' keywords."""
        engine = EnterprisePolicyEngine("org1")
        assert engine._matches_condition("true", {}) is True
        assert engine._matches_condition("True", {}) is True
        assert engine._matches_condition("always", {}) is True

    def test_always_false_keywords(self) -> None:
        """Test 'false', 'False', 'never' keywords."""
        engine = EnterprisePolicyEngine("org1")
        assert engine._matches_condition("false", {}) is False
        assert engine._matches_condition("False", {}) is False
        assert engine._matches_condition("never", {}) is False

    def test_case_sensitive_comparison(self) -> None:
        """Test string comparison is case sensitive."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"status": "ACTIVE"}
        assert engine._matches_condition("status == 'ACTIVE'", resource) is True
        assert engine._matches_condition("status == 'active'", resource) is False

    def test_float_comparison(self) -> None:
        """Test float comparison works."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"ratio": 1.5}
        assert engine._matches_condition("ratio > 1.0", resource) is True
        assert engine._matches_condition("ratio < 2.0", resource) is True
        assert engine._matches_condition("ratio == 1.5", resource) is True

    def test_negative_numbers(self) -> None:
        """Test negative number parsing and comparison."""
        engine = EnterprisePolicyEngine("org1")
        resource = {"delta": -5}
        assert engine._matches_condition("delta < 0", resource) is True
        assert engine._matches_condition("delta > -10", resource) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
