from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.retrieval.collections import all_categories, get_collection_registry, get_table_name
from app.retrieval.index import load_index


@dataclass
class RetrievalHit:
    text: str
    score: float
    metadata: dict[str, Any]
    node_id: str | None = None
    category: str | None = None
    collection: str | None = None


class Retriever(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        raise NotImplementedError


class VectorRetriever(Retriever):
    """单库或多库向量检索；多库时按 score 合并取 Top-K。"""

    def __init__(
        self,
        categories: list[str] | None = None,
        top_k: int = 5,
        similarity_threshold: float | None = 0.5,
    ):
        registry = get_collection_registry()
        if categories is None:
            self.categories = list(registry.keys())
        else:
            unknown = [c for c in categories if c not in registry]
            if unknown:
                known = ", ".join(sorted(registry))
                raise ValueError(f"未知 categories={unknown}，可选: {known}")
            self.categories = list(categories)

        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self._indices = {cat: load_index(cat) for cat in self.categories}

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalHit]:
        k = top_k or self.top_k
        per_store_k = k if len(self.categories) == 1 else max(k, k * 2)

        hits: list[RetrievalHit] = []
        for category in self.categories:
            index = self._indices[category]
            retriever = index.as_retriever(similarity_top_k=per_store_k)
            for nws in retriever.retrieve(query):
                score = float(nws.score or 0.0)
                if self.similarity_threshold is not None and score < self.similarity_threshold:
                    continue
                node = nws.node
                metadata = dict(node.metadata or {})
                metadata.setdefault("category", category)
                metadata.setdefault("collection", get_table_name(category))
                hits.append(
                    RetrievalHit(
                        text=node.get_content(metadata_mode="none"),
                        score=score,
                        metadata=metadata,
                        node_id=node.node_id,
                        category=category,
                        collection=get_table_name(category),
                    )
                )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


# 兼容旧名
FAQRetriever = Retriever
VectorFAQRetriever = VectorRetriever


def get_retriever(
    categories: list[str] | None = None,
    top_k: int = 5,
    similarity_threshold: float | None = None,
) -> Retriever:
    return VectorRetriever(
        categories=categories,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
    )


def get_faq_retriever(
    top_k: int = 5,
    similarity_threshold: float | None = None,
) -> Retriever:
    """仅检索 FAQ Markdown 集合。"""
    return get_retriever(
        categories=["faq"],
        top_k=top_k,
        similarity_threshold=similarity_threshold,
    )


def get_pdf_retriever(
    categories: list[str] | None = None,
    top_k: int = 5,
    similarity_threshold: float | None = None,
) -> Retriever:
    """检索 PDF 切块集合（默认全部 PDF 类别，不含 FAQ）。"""
    pdf_cats = [c for c in all_categories() if c != "faq"]
    return get_retriever(
        categories=categories or pdf_cats,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
    )
