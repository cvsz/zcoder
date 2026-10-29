"""Bounded lexical ranking used when SQLite FTS5 is unavailable."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Return Unicode-aware, case-folded terms for lexical ranking."""
    return [token.casefold() for token in _TOKEN_RE.findall(text)]


def bm25_scores(
    query_terms: list[str], documents: list[str], *, k1: float = 1.5, b: float = 0.75
) -> list[float]:
    """Compute BM25 scores for a bounded set of already-filtered documents."""
    if not documents:
        return []
    terms = set(query_terms)
    if not terms:
        return [0.0] * len(documents)

    tokenized = [tokenize(document) for document in documents]
    average_length = sum(map(len, tokenized)) / len(tokenized) or 1.0
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens) & terms)

    total_documents = len(tokenized)
    scores = []
    for tokens in tokenized:
        frequencies = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            df = document_frequency[term]
            inverse_frequency = math.log(1.0 + (total_documents - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * length / average_length)
            score += inverse_frequency * (frequency * (k1 + 1.0)) / denominator
        scores.append(score)
    return scores
