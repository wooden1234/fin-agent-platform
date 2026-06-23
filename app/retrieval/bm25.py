"""Small dependency-free BM25 utilities for hybrid retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

_WORD_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._%+-]*")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    tokens = _WORD_RE.findall(lowered)
    for seq in _CJK_RE.findall(lowered):
        tokens.extend(_cjk_ngrams(seq))
    return tokens


def bm25_scores(
    query: str,
    documents: Iterable[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    corpus_tokens = [tokenize(doc) for doc in documents]
    query_tokens = tokenize(query)
    if not corpus_tokens or not query_tokens:
        return [0.0 for _ in corpus_tokens]

    doc_freq: Counter[str] = Counter()
    for tokens in corpus_tokens:
        doc_freq.update(set(tokens))

    total_docs = len(corpus_tokens)
    avgdl = sum(len(tokens) for tokens in corpus_tokens) / total_docs or 1.0
    query_counts = Counter(query_tokens)
    scores: list[float] = []

    for tokens in corpus_tokens:
        term_freq = Counter(tokens)
        doc_len = len(tokens) or 1
        score = 0.0
        for term, query_count in query_counts.items():
            freq = term_freq.get(term, 0)
            if freq == 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / avgdl)
            score += idf * (freq * (k1 + 1) / denom) * query_count
        scores.append(score)

    return scores


def _cjk_ngrams(text: str) -> list[str]:
    if len(text) <= 2:
        return [text]
    grams: list[str] = []
    for n in (2, 3, 4):
        if len(text) >= n:
            grams.extend(text[i : i + n] for i in range(len(text) - n + 1))
    return grams
