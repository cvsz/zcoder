"""Security regression for DeepResearchAgent caller-supplied source URLs."""

import pytest

from zcoder.claude.rag.research import DeepResearchAgent


def test_research_source_url_blocks_loopback_before_network_access():
    agent = DeepResearchAgent.__new__(DeepResearchAgent)

    with pytest.raises(ValueError, match="non-public"):
        agent._fetch_retrying("http://127.0.0.1:8080/private")
