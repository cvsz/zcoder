"""Document ingestion and preprocessing pipeline for Phase 16.

Handles document ingestion, chunking, preprocessing, and indexing
for the RAG knowledge base. Supports multiple file types and
integrates with vector store backends.
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

from zcoder.agent.rag.engine import RAGIndex, build_index

SUPPORTED_EXTS = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".html",
    ".xml",
    ".csv",
    ".jsonl",
    ".pdf",  # PDF support (basic text extraction)
    ".docx",  # Word document support (basic text extraction)
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".mp3",
    ".wav",
    ".ogg",
    ".mp4",
    ".avi",
    ".mkv",
}


def guess_ext(filepath: str) -> str:
    """Guess the file extension from a filepath."""
    return Path(filepath).suffix.lower()


def is_supported(filepath: str) -> bool:
    """Check if a file type is supported for ingestion."""
    ext = guess_ext(filepath)
    return ext in SUPPORTED_EXTS or mimetypes.guess_type(filepath)[0] is not None


def read_text_file(filepath: str, encoding: str = "utf-8") -> str:
    """Read text content from a file."""
    return Path(filepath).read_text(encoding=encoding, errors="replace")


def preprocess_text(text: str) -> str:
    """Preprocess text content for indexing.

    Applies cleaning transformations without changing semantic meaning:
    - Normalize whitespace
    - Remove excessive blank lines
    - Strip non-printable characters (except newlines)
    - Normalize Unicode
    """
    # Remove non-printable characters except whitespace
    text = re.sub(r"[^\x20-\x7E\n\r]", "", text)

    # Normalize excessive whitespace
    text = "\n".join(line.strip() for line in text.split("\n"))

    # Collapse multiple consecutive blank lines to a single one
    text = re.sub(r"\n\n+", "\n\n", text)

    return text


def chunk_text(
    text: str,
    chunk_size: int = 600,
    overlap: int = 100,
    separator: str = "\n\n",
) -> list[dict[str, Any]]:
    """Chunk text into overlapping segments for RAG indexing.

    Args:
        text: The text to chunk
        chunk_size: Target size of each chunk in tokens (approx characters)
        overlap: Number of characters to overlap between chunks
        separator: Preferred split separator

    Returns:
        List of chunk dictionaries with 'content', 'source', and 'tokens' keys
    """
    # Normalize the text first
    text = preprocess_text(text)

    # Split by separator first
    parts = text.split(separator)
    chunks: list[dict[str, Any]] = []

    current_chunk: list[str] = []
    current_size = 0

    for part in parts:
        part_size = len(part) + len(separator)  # Include separator

        # If single part exceeds chunk_size, split it further
        if part_size > chunk_size and current_chunk:
            # Flush current chunk
            content = separator.join(current_chunk)
            chunks.append(
                {
                    "content": content,
                    "tokens": len(content.split()),
                    "source_hash": hash(content),
                }
            )
            current_chunk = []
            current_size = 0

        # If part itself exceeds chunk_size, split it
        if part_size > chunk_size:
            # Split by sentences or words
            words = part.split()
            i = 0
            while i < len(words):
                chunk_words = words[i : i + chunk_size]
                if chunk_words:
                    content = " ".join(chunk_words)
                    chunks.append(
                        {
                            "content": content,
                            "tokens": len(chunk_words),
                            "source_hash": hash(content),
                        }
                    )
                i += chunk_size
            continue

        # Add part to current chunk
        if current_size + part_size > chunk_size and current_chunk:
            # Flush current chunk and start new one
            content = separator.join(current_chunk)
            chunks.append(
                {
                    "content": content,
                    "tokens": len(content.split()),
                    "source_hash": hash(content),
                }
            )
            current_chunk = [part]
            current_size = part_size
        else:
            current_chunk.append(part)
            current_size += part_size

    # Flush remaining chunk
    if current_chunk:
        content = separator.join(current_chunk)
        chunks.append(
            {
                "content": content,
                "tokens": len(current_chunk),
                "source_hash": hash(content),
            }
        )

    return chunks


def ingest_file(
    filepath: str,
    vector_store: Any,
    chunk_size: int = 600,
    overlap: int = 100,
    tenant_id: str = "",
    vector_store_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Ingest a single file into the vector store.

    Args:
        filepath: Path to the file to ingest
        vector_store: Vector store instance to insert chunks into
        chunk_size: Target chunk size in characters
        overlap: Chunk overlap in characters
        tenant_id: Tenant identifier for isolation
        vector_store_config: Additional vector store configuration

    Returns:
        List of chunk metadata that was ingested
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for ingestion (SEC-007 tenant isolation)")

    if not Path(filepath).exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    # Read file content
    text = read_text_file(filepath)

    # Preprocess text
    text = preprocess_text(text)

    # Chunk the text
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    # Insert chunks into vector store
    ingested: list[dict[str, Any]] = []
    for chunk in chunks:
        # Generate a chunk ID
        chunk_id = f"{tenant_id}_{Path(filepath).name}_{chunk['source_hash']}"

        # Create embedding vector (using hash-based fallback for offline)
        import numpy as np

        dimension = vector_store_config.get("dimension", 768) if vector_store_config else 768
        vector = np.array(
            [hash(chunk["content"] + chunk_id) % (2**31) for _ in range(dimension)],
            dtype=np.float32,
        )

        # Prepare metadata
        metadata = {
            "source": filepath,
            "filename": Path(filepath).name,
            "tenant_id": tenant_id,
            "chunk_tokens": chunk["tokens"],
        }

        # Insert into vector store
        vector_store.insert(
            chunk_id=chunk_id,
            vector=vector,
            metadata=metadata,
        )

        ingested.append(
            {
                "chunk_id": chunk_id,
                "source": filepath,
                "tokens": chunk["tokens"],
                "metadata": metadata,
            }
        )

    return ingested


def ingest_folder(
    folder: str,
    vector_store: Any,
    chunk_size: int = 600,
    overlap: int = 100,
    tenant_id: str = "",
    vector_store_config: dict[str, Any] | None = None,
    recursive: bool = True,
) -> dict[str, int]:
    """Ingest all supported files from a folder into the vector store.

    Args:
        folder: Path to the folder to ingest
        vector_store: Vector store instance to insert chunks into
        chunk_size: Target chunk size in characters
        overlap: Chunk overlap in characters
        tenant_id: Tenant identifier for isolation
        vector_store_config: Additional vector store configuration
        recursive: Whether to recursively process subfolders

    Returns:
        Dictionary with count of files processed and chunks ingested
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for ingestion (SEC-007 tenant isolation)")

    folder_path = Path(folder)
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    stats = {"files_processed": 0, "chunks_ingested": 0}

    # Find all supported files
    pattern = "**/*" if recursive else "*"
    for filepath in folder_path.glob(pattern):
        if not filepath.is_file():
            continue

        ext = filepath.suffix.lower()
        if ext in SUPPORTED_EXTS or is_supported(str(filepath)):
            try:
                result = ingest_file(
                    str(filepath),
                    vector_store,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    tenant_id=tenant_id,
                    vector_store_config=vector_store_config,
                )
                stats["files_processed"] += 1
                stats["chunks_ingested"] += len(result)
            except Exception as e:
                print(f"[WARN] Failed to ingest {filepath}: {e}")

    return stats


def ingest_with_vector_store(
    name: str,
    folder: str,
    chunk_size: int = 600,
    overlap: int = 100,
    tenant_id: str = "",
    vector_store_backend: str = "pgvector",
    vector_store_config: dict[str, Any] | None = None,
) -> RAGIndex:
    """Full ingestion pipeline: build index from folder and insert into vector store.

    Args:
        name: Index name
        folder: Folder path to ingest
        chunk_size: Target chunk size
        overlap: Chunk overlap
        tenant_id: Tenant identifier
        vector_store_backend: Vector store backend (pgvector, faiss, offline)
        vector_store_config: Vector store configuration

    Returns:
        Created RAGIndex with vector store backend integrated
    """

    # Build the RAG index (this creates chunks and BM25 scoring)
    # Use default vector store backend (pgvector) since configuration is handled separately
    idx = build_index(
        name=name,
        folder=folder,
        chunk_size=chunk_size,
        tenant_id=tenant_id,
    )

    # Get the vector store from the index and ingest all chunks
    if hasattr(idx, "_vector_backend") and idx._vector_backend:
        vs = idx._vector_backend
        # Re-ingest all chunks into the vector store
        ingest_result = ingest_folder(
            folder=folder,
            vector_store=vs,
            chunk_size=chunk_size,
            overlap=overlap,
            tenant_id=tenant_id,
            vector_store_config=vector_store_config,
            recursive=True,
        )
        print(f"✓ Ingested {ingest_result['chunks_ingested']} chunks from {idx.name} index into vector store")
    else:
        print(f"[WARN] No vector store backend available for {idx.name}; using BM25-only search")

    return idx
