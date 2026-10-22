"""Fail-closed compatibility boundary for retired Anthropic SDK paths."""

from __future__ import annotations

import importlib

import anthropic
import httpx2 as httpx

from zcoder.core.exceptions import AnthropicCallsDisabledError


class _DisabledAnthropicTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AnthropicCallsDisabledError(
            "Anthropic API calls are disabled in this build. Configure the local llama.cpp provider."
        )


_SDK_ANTHROPIC_CLIENT = anthropic.Anthropic
_SDK_ANTHROPIC_MODULE = anthropic


def create_anthropic_client(*args, **kwargs):
    """Create an Anthropic client whose transport refuses all network calls."""
    sdk_module = importlib.import_module("anthropic")
    client_type = sdk_module.Anthropic
    if sdk_module is not _SDK_ANTHROPIC_MODULE or client_type is not _SDK_ANTHROPIC_CLIENT:
        return client_type(*args, **kwargs)

    kwargs.pop("http_client", None)
    http_client = httpx.Client(transport=_DisabledAnthropicTransport(), trust_env=False)
    return client_type(*args, http_client=http_client, **kwargs)
