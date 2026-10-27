"""Local source-grounded answers and citation references."""

import re
from pathlib import Path

from zcoder.services.coder import Coder

_CITATION = re.compile(r"\[(\d+)\]")
_LOCAL_CITATION_INSTRUCTIONS = (
    "Answer only from the supplied sources. Cite each source-backed claim with its "
    "source number in square brackets, such as [1]. If the sources do not contain "
    "the answer, say that the available sources are insufficient. Never invent a source."
)


class CitationsCoder:
    """Generate local answers grounded in supplied documents or search results.

    The `api_key` parameter remains for call-site compatibility and is ignored.
    Citation references are validated against the supplied source list; this
    class does not claim server-verified character offsets or quoted evidence.
    """

    def __init__(
        self, api_key: str = "", model: str = "zqwen2.5-coder-7b-instruct-q4_k_m", max_tokens: int = 4096
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.client = Coder(model=model, max_tokens=max_tokens)

    def _answer_with_sources(self, question: str, sources: list[dict], system: str | None = None) -> dict:
        if not sources:
            return {"answer": "No sources supplied.", "citations": [], "usage": {}}

        source_blocks = []
        for index, source in enumerate(sources, 1):
            title = str(source.get("title") or f"Source {index}")
            url = str(source.get("url") or "")
            source_blocks.append(
                f"[Source {index}]\nTitle: {title}\nURL: {url}\nContent:\n{source['content']}"
            )
        prompt = (
            "Answer the question using only these sources. Put source references such as "
            "[1] next to claims they support.\n\n" + "\n\n".join(source_blocks) + f"\n\nQuestion:\n{question}"
        )

        try:
            answer = self.client.generate(
                prompt,
                system=system or _LOCAL_CITATION_INSTRUCTIONS,
            )
        except Exception as exc:
            return {"answer": f"[ERROR] Local generation failed: {exc}", "citations": [], "usage": {}}

        cited_ids = list(dict.fromkeys(int(value) for value in _CITATION.findall(answer)))
        invalid_ids = [source_id for source_id in cited_ids if source_id < 1 or source_id > len(sources)]
        if invalid_ids:
            invalid = ", ".join(f"[{source_id}]" for source_id in invalid_ids)
            return {
                "answer": f"[ERROR] Local model returned unknown source references: {invalid}",
                "citations": [],
                "usage": {},
            }

        citations = []
        for source_id in cited_ids:
            source = sources[source_id - 1]
            citations.append(
                {
                    "source_id": source_id,
                    "document": str(source.get("title") or f"Source {source_id}"),
                    "url": str(source.get("url") or ""),
                }
            )
        return {"answer": answer, "citations": citations, "usage": {}}

    def cite_documents(self, question: str, documents: list[dict], system: str | None = None) -> dict:
        """Answer from local document content and return validated source references."""
        sources = []
        for document in documents:
            if not isinstance(document, dict):
                return {"answer": "[ERROR] Each document must be a mapping.", "citations": [], "usage": {}}
            content = document.get("content")
            if not isinstance(content, str):
                return {
                    "answer": "[ERROR] Each document must contain text content.",
                    "citations": [],
                    "usage": {},
                }
            sources.append({"title": document.get("title", "Document"), "content": content})
        return self._answer_with_sources(question, sources, system)

    def cite_search_results(self, question: str, results: list[dict]) -> dict:
        """Answer from already-provided search results without performing network search."""
        sources = []
        for result in results:
            if not isinstance(result, dict):
                return {
                    "answer": "[ERROR] Each search result must be a mapping.",
                    "citations": [],
                    "usage": {},
                }
            content = result.get("content")
            if not isinstance(content, str):
                return {
                    "answer": "[ERROR] Each search result must contain text content.",
                    "citations": [],
                    "usage": {},
                }
            sources.append(
                {
                    "title": result.get("title", "Search result"),
                    "url": result.get("url", ""),
                    "content": content,
                }
            )
        return self._answer_with_sources(question, sources)

    def rag_from_directory(self, question: str, directory: str, glob_pattern: str = "*.md") -> dict:
        """Load matching local text files and answer with validated file references."""
        documents = []
        try:
            paths = sorted(Path(directory).glob(glob_pattern))
        except (OSError, ValueError) as exc:
            return {
                "answer": f"[ERROR] Invalid local document selection: {exc}",
                "citations": [],
                "usage": {},
            }
        for path in paths:
            try:
                if not path.is_file():
                    continue
                documents.append({"title": path.name, "content": path.read_text(encoding="utf-8")[:8000]})
            except (OSError, UnicodeError) as exc:
                return {"answer": f"[ERROR] Cannot read {path}: {exc}", "citations": [], "usage": {}}
        if not documents:
            return {"answer": f"No documents found in {directory}", "citations": [], "usage": {}}
        return self.cite_documents(question, documents)


def cmd_cite(question: str, doc_files: list[str], api_key: str, model: str):
    documents = []
    for filename in doc_files:
        path = Path(filename)
        if not path.is_file():
            print(f"  [WARN] Not a readable file: {filename}")
            continue
        try:
            documents.append({"title": path.name, "content": path.read_text(encoding="utf-8")[:8000]})
        except (OSError, UnicodeError) as exc:
            print(f"  [WARN] Cannot read {filename}: {exc}")

    if not documents:
        print("[ERROR] No readable source files found.")
        return

    print(f"\033[94mℹ Answering with local citations from {len(documents)} document(s)\033[0m\n")
    client = CitationsCoder(api_key=api_key, model=model)
    result = client.cite_documents(question, documents)
    print(result["answer"])
    if result["citations"]:
        print("\n\033[90m── Sources ────────────────────────────\033[0m")
        for citation in result["citations"]:
            print(f"\033[90m[{citation['source_id']}] {citation['document']}\033[0m")
    return result


def cmd_rag(question: str, directory: str, api_key: str, model: str, pattern: str = "*.md"):
    print(f"\033[94mℹ Local RAG from {directory} ({pattern})\033[0m\n")
    client = CitationsCoder(api_key=api_key, model=model)
    result = client.rag_from_directory(question, directory, pattern)
    print(result["answer"])
    if result["citations"]:
        print("\n\033[90m── Sources ────────────────────────────\033[0m")
        for citation in result["citations"]:
            print(f"\033[90m[{citation['source_id']}] {citation['document']}\033[0m")
    return result
