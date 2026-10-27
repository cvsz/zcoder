from __future__ import annotations

import pytest

from zcoder.agent.capabilities.vision import _image_block


def test_image_block_requires_path_or_url():
    with pytest.raises(ValueError, match="Provide an image path or URL"):
        _image_block()


def test_image_block_accepts_url_without_reading_a_file():
    assert _image_block(url="https://images.example.test/sample.png") == {
        "type": "image",
        "source": {"type": "url", "url": "https://images.example.test/sample.png"},
    }
