"""
tests/test_source_of_truth_conformance.py — Source-of-Truth Conformance Tests

Validates ZCoder runtime behavior and constants directly against independent
authoritative Anthropic specifications, preventing regressions and false releases.
"""

from zcoder.claude.models.registry import (
    DEPRECATED_MODELS,
    INFERENCE_GEO_SUPPORTED,
    MODEL_CATALOG,
    RETIRED_MODELS,
)
from zcoder.claude.models.sonnet5 import STANDARD_PRICE_IN_USD, STANDARD_PRICE_OUT_USD, current_pricing
from zcoder.core.resilience import extract_response_metadata


def test_sonnet5_authoritative_price():
    """Assert Sonnet 5 permanent pricing matches the August 10, 2026 announcement ($2.00 / $10.00)."""
    assert STANDARD_PRICE_IN_USD == 2.0
    assert STANDARD_PRICE_OUT_USD == 10.0
    pricing = current_pricing()
    assert pricing["price_in"] == 2.0
    assert pricing["price_out"] == 10.0
    catalog = MODEL_CATALOG["claude-sonnet-5"]
    assert catalog["price_in"] == 2.0
    assert catalog["price_out"] == 10.0


def test_opus41_retired():
    """Assert claude-opus-4-1-20250805 is retired (passed August 5, 2026)."""
    assert "claude-opus-4-1-20250805" in RETIRED_MODELS
    assert "claude-opus-4-1-20250805" not in DEPRECATED_MODELS


def test_opus5_geo_supported():
    """Assert claude-opus-5 is in INFERENCE_GEO_SUPPORTED."""
    assert "claude-opus-5" in INFERENCE_GEO_SUPPORTED
    assert "claude-sonnet-5" in INFERENCE_GEO_SUPPORTED


def test_workspace_id_response_metadata_extraction():
    """Assert anthropic-workspace-id in HTTP response headers is extracted into metadata."""
    headers = {
        "request-id": "req_01AbcDef",
        "anthropic-workspace-id": "wrkspc_998877",
        "anthropic-ratelimit-requests-remaining": "49",
        "anthropic-ratelimit-tokens-remaining": "399990",
    }
    meta = extract_response_metadata(headers)
    assert meta["request_id"] == "req_01AbcDef"
    assert meta["workspace_id"] == "wrkspc_998877"
    assert meta["ratelimit_requests_remaining"] == 49
    assert meta["ratelimit_tokens_remaining"] == 399990
