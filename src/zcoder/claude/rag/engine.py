"""
claude_rag.py — Retrieval-Augmented Generation pipeline
ZCoder CLI v1.10.0

Indexes a local folder of files (or a pre-built index JSON), retrieves
the most relevant chunks at query time (keyword BM25-style scoring),
then generates a grounded, cited response. Uses the Files API to
upload large corpora once and reference them cheaply across queries.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

from zcoder.core.exceptions import ZCoderError
from zcoder.core.security import validate_name
from zcoder.core.utils import sampling_kwargs

INDEX_DIR = Path.home() / ".zcoder" / "rag_indexes"
SUPPORTED_EXTS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".go",
    ".java",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".html",
}


@dataclass
class Chunk:
    cid: str
    source: str
    content: str
    tokens: int = 0


@dataclass
class RAGIndex:
    name: str
    chunks: list[Chunk] = field(default_factory=list)
    idf: dict[str, float] = field(default_factory=dict)
    file_ids: dict[str, str] = field(default_factory=dict)  # cid → Files API id
    tenant_id: str = ""

    def to_dict(self):
        return {
            "name": self.name,
            "tenant_id": self.tenant_id,
            "chunks": [
                {"cid": c.cid, "source": c.source, "content": c.content, "tokens": c.tokens}
                for c in self.chunks
            ],
            "idf": self.idf,
            "file_ids": self.file_ids,
        }

    @staticmethod
    def from_dict(d) -> "RAGIndex":
        idx = RAGIndex(name=d["name"], tenant_id=d.get("tenant_id", ""))
        idx.chunks = [Chunk(**c) for c in d.get("chunks", [])]
        idx.idf = d.get("idf", {})
        idx.file_ids = d.get("file_ids", {})
        return idx


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _chunk_text(source: str, text: str, size: int = 600, overlap: int = 100) -> list[Chunk]:
    words = text.split()
    chunks = []
    i = 0
    cid_base = Path(source).stem
    while i < len(words):
        end = min(i + size, len(words))
        content = " ".join(words[i:end])
        cid = f"{cid_base}_{i}"
        chunks.append(Chunk(cid=cid, source=source, content=content, tokens=end - i))
        i += size - overlap
    return chunks


def build_index(
    name: str,
    folder: str,
    chunk_size: int = 600,
    overlap: int = 100,
    tenant_id: str = "",
) -> RAGIndex:
    if not tenant_id:
        # SEC-007: fail closed — no shared/default namespace. Every index
        # must be built under an explicit tenant boundary.
        raise ValueError("tenant_id is required to build a RAG index")
    # validate identifiers before any indexing work is done
    _index_path(name, tenant_id)
    idx = RAGIndex(name=name, tenant_id=tenant_id)
    df: Counter = Counter()
    total = 0
    for path in Path(folder).rglob("*"):
        if path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for chunk in _chunk_text(str(path), text, chunk_size, overlap):
            idx.chunks.append(chunk)
            total += 1
            for w in set(_tokenize(chunk.content)):
                df[w] += 1
    idx.idf = {w: math.log((total + 1) / (c + 1)) + 1 for w, c in df.items()}
    _save_index(idx)
    return idx


def _index_path(name: str, tenant_id: str) -> Path:
    validate_name(name, field="index name")
    validate_name(tenant_id, field="tenant id")
    # the {tenant}__{name} layout requires the delimiter to stay unambiguous
    if "__" in name or "__" in tenant_id:
        raise ValueError("index name and tenant id must not contain '__'")
    return INDEX_DIR / f"{tenant_id}__{name}.json"


def _save_index(idx: RAGIndex):
    if not idx.tenant_id:
        raise ValueError("tenant_id is required to save a RAG index")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    _index_path(idx.name, idx.tenant_id).write_text(json.dumps(idx.to_dict(), indent=2))


def load_index(name: str, tenant_id: str = "") -> Optional[RAGIndex]:
    if not tenant_id:
        # SEC-007: fail closed — an unnamed tenant may not resolve any index.
        raise ValueError("tenant_id is required to load a RAG index")
    p = _index_path(name, tenant_id)
    if not p.exists():
        # Legacy un-namespaced indexes ({name}.json without tenant metadata)
        # are intentionally invisible here: they carry no tenant boundary.
        return None
    idx = RAGIndex.from_dict(json.loads(p.read_text()))
    if idx.tenant_id != tenant_id or idx.name != name:
        # Fail closed on tampered/renamed files whose stored identity does
        # not match the requested tenant namespace.
        return None
    return idx


def _score(query_tokens: list[str], chunk: Chunk, idf: dict[str, float]) -> float:
    tf = Counter(_tokenize(chunk.content))
    score = 0.0
    for qt in query_tokens:
        if qt in tf:
            score += (tf[qt] / (tf[qt] + 1.5)) * idf.get(qt, 1.0)
    return score


def retrieve(idx: RAGIndex, query: str, k: int = 5) -> list[Chunk]:
    qt = _tokenize(query)
    scored = [(c, _score(qt, c, idx.idf)) for c in idx.chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, s in scored[:k] if s > 0]


def generate(query: str, chunks: list[Chunk], api_key: str, model: str = "claude-sonnet-5") -> str:
    client = anthropic.Anthropic(api_key=api_key)
    ctx = "\n\n".join(f"[{c.source}]\n{c.content}" for c in chunks)
    system = (
        "Answer based on the provided context. Cite sources using the "
        "[filename] format. If the context doesn't contain the answer, "
        "say so clearly rather than guessing."
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        **sampling_kwargs(model, temperature=0.2),
        system=system,
        messages=[{"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {query}"}],
    )
    return resp.content[0].text


# ── CLI commands ──────────────────────────────────────────────────────────────


def cmd_rag_index(name: str, folder: str, chunk_size: int = 600, tenant_id: str = ""):
    if not tenant_id:
        print("[ERROR] --rag-tenant is required to build an index (SEC-007 tenant isolation)")
        raise SystemExit(2)
    try:
        _index_path(name, tenant_id)
    except ZCoderError as e:
        print(f"[ERROR] {e}")
        raise SystemExit(2) from e
    print(f"Building RAG index '{name}' (tenant {tenant_id}) from {folder} …")
    idx = build_index(name, folder, chunk_size, tenant_id=tenant_id)
    print(f"✓ Indexed {len(idx.chunks)} chunks from {folder}")


def cmd_rag_query(name: str, query: str, api_key: str, model: str, k: int = 5, tenant_id: str = ""):
    try:
        idx = load_index(name, tenant_id)
    except (ValueError, ZCoderError) as e:
        print(f"[ERROR] {e}")
        raise SystemExit(2) from e
    if not idx:
        print(
            f"Index not found for tenant '{tenant_id or '(none)'}': {name}\n"
            "  Run --rag-index with the same --rag-tenant to build it."
        )
        return
    chunks = retrieve(idx, query, k)
    if not chunks:
        print("No relevant chunks found.")
        return
    print(f"Retrieved {len(chunks)} chunk(s). Generating answer …\n")
    print(generate(query, chunks, api_key, model))


def cmd_rag_list(tenant_id: str = ""):
    if not INDEX_DIR.exists():
        print("No RAG indexes found.")
        return
    shown = 0
    for p in sorted(INDEX_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        t = d.get("tenant_id", "")
        if tenant_id and t != tenant_id:
            continue
        if not tenant_id and not t:
            # Legacy un-namespaced indexes carry no tenant boundary; list
            # them only so operators can see and rebuild them.
            print(f"  {d.get('name', '?'):<24} {len(d.get('chunks', []))} chunks [no tenant — rebuild]")
            shown += 1
            continue
        print(f"  {d.get('name', '?'):<24} [{t}] {len(d.get('chunks', []))} chunks")
        shown += 1
    if not shown:
        print("No RAG indexes found.")
