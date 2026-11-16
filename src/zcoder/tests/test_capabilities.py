"""Tests for zcoder.agent.capabilities - Tool capability modules."""

from zcoder.agent.capabilities.search import SearchCoder
from zcoder.agent.capabilities.vision import VisionCoder
from zcoder.agent.capabilities.structured import StructuredCoder
from zcoder.agent.capabilities.thinking import ThinkingCoder
from zcoder.agent.capabilities.citations import CitationsCoder
from zcoder.agent.capabilities.embeddings import EmbeddingIndex
from zcoder.agent.capabilities.advisor import AdvisorCoder
from zcoder.agent.capabilities.stream import StreamCoder


class TestCapabilityModules:
    """Tests that capability modules export expected classes."""

    def test_search_coder_exists(self):
        assert SearchCoder is not None

    def test_vision_coder_exists(self):
        assert VisionCoder is not None

    def test_structured_coder_exists(self):
        assert StructuredCoder is not None

    def test_thinking_coder_exists(self):
        assert ThinkingCoder is not None

    def test_citations_coder_exists(self):
        assert CitationsCoder is not None

    def test_embeddings_exists(self):
        assert EmbeddingIndex is not None

    def test_advisor_coder_exists(self):
        assert AdvisorCoder is not None

    def test_stream_coder_exists(self):
        assert StreamCoder is not None


class TestToolDefinitions:
    """Tests that all capability tool classes exist and are importable."""

    def test_all_tool_classes_exist(self):
        """Verify all capability tool classes can be imported."""
        tools = [
            SearchCoder,
            VisionCoder,
            StructuredCoder,
            ThinkingCoder,
            CitationsCoder,
            EmbeddingIndex,
            AdvisorCoder,
            StreamCoder,
        ]
        for tool_class in tools:
            assert tool_class is not None
            assert callable(tool_class)
