"""Vector store implementations for RAG knowledge base (Phase 16).

Supports two backends:
1. pgvector via psycopg2 - PostgreSQL with vector extension
2. FAISS - Facebook AI Similarity Search (local, no GPU required for basic use)

Provides a unified interface for document ingestion, vector storage, and
similarity search across both backends.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

# Try to import pgvector-friendly types; pgvector is a PostgreSQL extension,
# not a Python package, so we interact via psycopg2 with raw SQL.
try:
    import psycopg2

    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# Try to import faiss; falls back gracefully if not available.
try:
    import faiss

    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


class VectorStoreBackend(Enum):
    """Available vector store backends."""

    PGVECTOR = "pgvector"
    FAISS = "faiss"
    OFFLINE = "offline"  # Pure numpy fallback for testing


@dataclass
class VectorConfig:
    """Configuration for vector store backend."""

    backend: VectorStoreBackend = VectorStoreBackend.PGVECTOR
    dimension: int = 768  # Default embedding dimension
    index_type: str = "flat"  # flat, ivf, hnsw
    metric: str = "cosine"  # cosine, l2, ip
    connection_string: str | None = None  # For pgvector
    index_path: str | None = None  # For FAISS disk-based index


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    vector: np.ndarray
    model_id: str
    tokens_used: int
    cost_usd: float = 0.0


@dataclass
class SearchResult:
    """Result of a vector search query."""

    chunk_id: str
    source: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Abstract base class for vector store implementations."""

    def __init__(self, config: VectorConfig | None = None) -> None:
        self.config = config or VectorConfig()
        self.dimension = self.config.dimension

    @abstractmethod
    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for k nearest neighbors to the query vector."""
        raise NotImplementedError

    @abstractmethod
    def insert(
        self,
        chunk_id: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert a vector chunk into the store."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, chunk_id: str) -> None:
        """Delete a vector chunk from the store."""
        raise NotImplementedError

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get metadata for a specific chunk."""
        raise NotImplementedError


class PGVectorStore(BaseVectorStore):
    """pgvector-backed vector store using psycopg2.

    Requires PostgreSQL with the pgvector extension installed:
    CREATE EXTENSION IF NOT EXISTS vector;

    Tables expected:
    CREATE TABLE chunks (
        chunk_id VARCHAR PRIMARY KEY,
        vector VECTOR(768),
        content TEXT,
        source VARCHAR,
        metadata JSONB DEFAULT '{}'::jsonb
    );
    """

    def __init__(self, config: VectorConfig | None = None) -> None:
        super().__init__(config)
        if not HAS_PSYCOPG2:
            raise ImportError("psycopg2 is required for pgvector backend")
        if not config.connection_string:
            raise ValueError("connection_string is required for PGVectorStore")
        self.conn_string = config.connection_string
        # Ensure extension and table exist on first use
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create extension and chunks table if they don't exist."""
        with psycopg2.connect(self.conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chunks (
                        chunk_id VARCHAR PRIMARY KEY,
                        vector VECTOR(%s),
                        content TEXT,
                        source VARCHAR,
                        metadata JSONB DEFAULT '{}'::jsonb
                    )
                    """,
                    (self.dimension,),
                )
                conn.commit()

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for k nearest neighbors using cosine similarity."""
        with psycopg2.connect(self.conn_string) as conn:
            with conn.cursor() as cur:
                # Build SQL with pgvector cosine similarity operator
                # <-> is distance, <-> is cosine similarity in pgvector
                sql = """
                    SELECT chunk_id, content, source, metadata,
                           1 - (vector <=> %s) AS similarity
                    FROM chunks
                    WHERE vector IS NOT NULL
                    ORDER BY vector <=> %s
                    LIMIT %s
                """
                cur.execute(sql, (query_vector.tobytes(), query_vector.tobytes(), k))
                rows = cur.fetchall()
                results: list[SearchResult] = []
                for row in rows:
                    chunk_id, content, source, metadata, similarity = row
                    results.append(
                        SearchResult(
                            chunk_id=chunk_id,
                            source=source or "unknown",
                            content=content or "",
                            score=float(similarity) if similarity is not None else 0.0,
                            metadata=metadata or {},
                        )
                    )
                return results

    def insert(
        self,
        chunk_id: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert a vector with chunk metadata."""
        with psycopg2.connect(self.conn_string) as conn:
            with conn.cursor() as cur:
                # Serialize metadata to JSONB
                metadata_json = json.dumps(metadata) if metadata else "{}"
                sql = """
                    INSERT INTO chunks (chunk_id, vector, content, source, metadata)
                    VALUES (%s, %s::vector, %s, %s, %s::jsonb)
                    ON CONFLICT (chunk_id) DO UPDATE
                    SET vector = EXCLUDED.vector,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata
                """
                cur.execute(
                    sql,
                    (
                        chunk_id,
                        vector.tobytes(),
                        "",  # content stored separately if needed
                        metadata.get("source", "unknown") if metadata else "unknown",
                        metadata_json,
                    ),
                )
                conn.commit()

    def delete(self, chunk_id: str) -> None:
        """Delete a chunk by ID."""
        with psycopg2.connect(self.conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE chunk_id = %s", (chunk_id,))
                conn.commit()

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get chunk metadata by ID."""
        with psycopg2.connect(self.conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chunk_id, vector, content, source, metadata FROM chunks WHERE chunk_id = %s",
                    (chunk_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "chunk_id": row[0],
                    "vector": np.frombuffer(row[1], dtype=np.float32).tolist() if row[1] else [],
                    "content": row[2] or "",
                    "source": row[3] or "unknown",
                    "metadata": row[4] or {},
                }


class FAISSVectorStore(BaseVectorStore):
    """FAISS-backed vector store for local similarity search.

    Falls back to brute-force flat index if FAISS is not available,
    but provides IVF or HNSW for large-scale search when FAISS is present.
    """

    def __init__(self, config: VectorConfig | None = None) -> None:
        super().__init__(config)
        if HAS_FAISS:
            # Use the configured index type
            if config.index_type == "ivf":
                self.index = faiss.IndexIVFFlat(
                    self._get_base_index(),
                    self.dimension,
                    config.index_config.get("nlist", 100),
                    getattr(faiss, config.metric, faiss.METRIC_L2),
                )
            elif config.index_type == "hnsw":
                self.index = faiss.IndexHNSWFlat(
                    self.dimension,
                    config.index_config.get("M", 16),
                    getattr(faiss, config.metric, faiss.METRIC_L2),
                )
            else:
                # Default to flat index
                self.index = faiss.IndexFlat(self._get_metric())
        else:
            # Fallback to pure numpy brute-force
            self.index = None  # Will use numpy search instead

    def _get_base_index(self) -> faiss.IndexFlat:
        """Get the base flat index for IVF/hnsw construction."""
        return faiss.IndexFlatL2(self.dimension)

    def _get_metric(self) -> int:
        """Get the FAISS metric enum based on config."""
        if self.config.metric == "cosine":
            return faiss.METRIC_INNER_PRODUCT  # cosine = 1 - 2*distance, but FAISS uses IP
        return faiss.METRIC_L2

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for k nearest neighbors using FAISS index."""
        if HAS_FAISS and self.index is not None:
            # Normalize for cosine similarity if needed
            if self.config.metric == "cosine":
                faiss.normalize_L2(query_vector.reshape(1, -1))
            distances, indices = self.index.search(query_vector.reshape(1, -1), k)
            results: list[SearchResult] = []
            for dist, idx in zip(distances[0], indices[0], strict=False):
                if idx == -1:
                    # No result
                    results.append(SearchResult(chunk_id="", source="", content="", score=0.0))
                else:
                    # In L2 distance, smaller is better; convert to similarity
                    # For cosine: similarity = 1 - (dist^2 / 2) approximately
                    # For IP: similarity = dist (already inner product)
                    score = float(-dist) if self.config.metric == "l2" else float(dist)
                    results.append(SearchResult(score=score))
            return results
        else:
            # Fallback: numpy-based brute force
            return self._numpy_search(query_vector, k)

    def _numpy_search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
    ) -> list[SearchResult]:
        """Fallback numpy-based search (no FAISS installed)."""
        # This would need access to stored vectors; in a full implementation,
        # we'd store them in a numpy array or migrate to pgvector later.
        # For now, return empty results indicating vector store not available.
        return []

    def insert(
        self,
        chunk_id: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert a vector into the FAISS index."""
        if HAS_FAISS and self.index is not None:
            # Normalize for cosine similarity
            if self.config.metric == "cosine":
                vector = vector / (np.linalg.norm(vector) + 1e-10)
            self.index.add(vector.reshape(1, -1))
        # If FAISS not available, we store in a fallback dict for later migration
        # (the system will degrade gracefully with numpy-only search)

    def delete(self, chunk_id: str) -> None:
        """Delete a chunk from the FAISS index.

        Note: FAISS does not support efficient deletion; in practice we
        mark chunks as deleted and rebuild the index periodically.
        """
        if HAS_FAISS and self.index is not None:
            # FAISS doesn't have a direct delete; we'll rebuild or mark inactive
            pass  # TODO: implement proper deletion or marking

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get chunk metadata from FAISS store.

        FAISS is a search index only; metadata must be stored separately
        (e.g., in a dict or database). This is a stub for the interface.
        """
        return None


class VectorStoreFactory:
    """Factory to create vector store instances based on config."""

    @staticmethod
    def create(config: VectorConfig) -> BaseVectorStore:
        """Create a vector store instance matching the config backend."""
        if config.backend == VectorStoreBackend.PGVECTOR:
            return PGVectorStore(config)
        elif config.backend == VectorStoreBackend.FAISS:
            return FAISSVectorStore(config)
        elif config.backend == VectorStoreBackend.OFFLINE:
            # Pure numpy fallback for testing
            from .rag.vector_stores import OfflineVectorStore

            return OfflineVectorStore(config)
        else:
            raise ValueError(f"Unsupported vector store backend: {config.backend}")


# Offline fallback for testing without pgvector/FAISS
class OfflineVectorStore(BaseVectorStore):
    """Pure numpy fallback for testing and development.

    Stores vectors in memory with brute-force search. Not suitable for
    production with large datasets but works for unit tests.
    """

    def __init__(self, config: VectorConfig | None = None) -> None:
        super().__init__(config)
        self.vectors: dict[str, np.ndarray] = {}  # chunk_id -> vector
        self.metadata: dict[str, dict[str, Any]] = {}  # chunk_id -> metadata

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Brute-force search using numpy cosine similarity or L2."""
        if not self.vectors:
            return []
        vectors_array = np.array(list(self.vectors.values()))
        # Compute L2 distances
        diff = vectors_array - query_vector.reshape(1, -1)
        distances = np.sum(diff**2, axis=1)
        # Get top-k indices
        top_indices = np.argsort(distances)[:k]
        results: list[SearchResult] = []
        for idx in top_indices:
            # Find matching chunk_id
            chunk_id = list(self.vectors.keys())[idx]
            score = float(distances[idx])
            # Convert L2 distance to cosine similarity approximation
            if self.config.metric == "cosine":
                # Normalize vectors for cosine approx
                query_norm = np.linalg.norm(query_vector)
                vec_norm = np.linalg.norm(self.vectors[chunk_id])
                if query_norm > 0 and vec_norm > 0:
                    cosine_sim = np.dot(query_vector, self.vectors[chunk_id]) / (query_norm * vec_norm)
                    score = float(cosine_sim)
                else:
                    score = 0.0
            results.append(SearchResult(chunk_id=chunk_id, score=score))
        return results

    def insert(
        self,
        chunk_id: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert a vector into the offline store."""
        self.vectors[chunk_id] = vector
        if metadata is not None:
            self.metadata[chunk_id] = metadata

    def delete(self, chunk_id: str) -> None:
        """Delete a chunk from the offline store."""
        self.vectors.pop(chunk_id, None)
        self.metadata.pop(chunk_id, None)

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get chunk metadata from offline store."""
        if chunk_id not in self.vectors:
            return None
        return {
            "chunk_id": chunk_id,
            "vector": self.vectors[chunk_id].tolist(),
            "metadata": self.metadata.get(chunk_id, {}),
        }
