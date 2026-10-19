"""Regression tests for Anthropic SDK 1.x sampling argument compatibility."""

import pytest

from zcoder.core.utils import sdk_sampling_kwargs


@pytest.mark.parametrize(
    "model",
    ["claude-sonnet-5", "claude-fable-5", "claude-mythos-5"],
)
def test_newer_models_omit_sampling_parameters(model):
    assert sdk_sampling_kwargs(model, temperature=0.3, top_p=0.5, top_k=5) == {}


def test_legacy_model_sampling_moves_to_extra_body():
    assert sdk_sampling_kwargs("claude-sonnet-4-6", temperature=0.3, top_p=0.9, top_k=20) == {
        "extra_body": {"temperature": 0.3, "top_p": 0.9, "top_k": 20}
    }


def test_absent_sampling_does_not_send_empty_extra_body():
    assert sdk_sampling_kwargs("claude-sonnet-4-6") == {}
