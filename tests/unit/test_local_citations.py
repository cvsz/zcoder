from unittest.mock import Mock

from zcoder.agent.capabilities.citations import CitationsCoder


def test_local_document_citations_use_loopback_coder_and_validate_refs(monkeypatch):
    client = Mock()
    client.generate.return_value = "Use the documented approach [2]."
    constructor = Mock(return_value=client)
    monkeypatch.setattr("zcoder.agent.capabilities.citations.Coder", constructor)

    citations = CitationsCoder(api_key="ignored", model="local-model")
    result = citations.cite_documents(
        "What approach?",
        [
            {"title": "one.md", "content": "First source."},
            {"title": "two.md", "content": "Second source."},
        ],
    )

    constructor.assert_called_once_with(model="local-model", max_tokens=4096)
    client.generate.assert_called_once()
    assert "First source." in client.generate.call_args.args[0]
    assert client.generate.call_args.kwargs["system"]
    assert result == {
        "answer": "Use the documented approach [2].",
        "citations": [{"source_id": 2, "document": "two.md", "url": ""}],
        "usage": {},
    }


def test_local_citations_reject_unknown_source_ids(monkeypatch):
    client = Mock()
    client.generate.return_value = "Unsupported claim [7]."
    monkeypatch.setattr("zcoder.agent.capabilities.citations.Coder", lambda **_: client)

    result = CitationsCoder().cite_documents("Question", [{"content": "Only source."}])

    assert result["answer"] == "[ERROR] Local model returned unknown source references: [7]"
    assert result["citations"] == []


def test_local_search_result_citations_preserve_supplied_urls(monkeypatch):
    client = Mock()
    client.generate.return_value = "The result supports this [1]."
    monkeypatch.setattr("zcoder.agent.capabilities.citations.Coder", lambda **_: client)

    result = CitationsCoder().cite_search_results(
        "Question", [{"title": "Local result", "url": "https://example.test/doc", "content": "Evidence."}]
    )

    assert result["citations"] == [
        {"source_id": 1, "document": "Local result", "url": "https://example.test/doc"}
    ]


def test_local_rag_reads_only_matching_regular_files(monkeypatch, tmp_path):
    client = Mock()
    client.generate.return_value = "Found it [1]."
    monkeypatch.setattr("zcoder.agent.capabilities.citations.Coder", lambda **_: client)
    (tmp_path / "notes.md").write_text("Local evidence", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("Not selected", encoding="utf-8")

    result = CitationsCoder().rag_from_directory("Question", str(tmp_path))

    assert result["citations"][0]["document"] == "notes.md"
    assert "Local evidence" in client.generate.call_args.args[0]
    assert "Not selected" not in client.generate.call_args.args[0]


def test_local_rag_reports_missing_directory_without_generation(monkeypatch, tmp_path):
    client = Mock()
    monkeypatch.setattr("zcoder.agent.capabilities.citations.Coder", lambda **_: client)

    result = CitationsCoder().rag_from_directory("Question", str(tmp_path / "missing"))

    assert result["citations"] == []
    client.generate.assert_not_called()
