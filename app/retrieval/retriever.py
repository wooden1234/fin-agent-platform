from dataclasses import dataclass
from typing import Any
from app.retrieval.index import load_index

@dataclass
class RetrievalHit:
    text: str
    score: float
    metadata: dict[str, Any]
    node_id: str | None = None

from abc import ABC, abstractmethod
class FAQRetriever(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        raise NotImplementedError

class VectorFAQRetriever(FAQRetriever):
    def __init__(
        self,
        top_k: int = 5,
        similarity_threshold: float | None = 0.5,
    ):
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self._index = load_index()
        self._retriever = self._index.as_retriever(
            similarity_top_k=top_k,
        )
    def search(self, query: str, top_k: int | None = None) -> list[RetrievalHit]:
        k = top_k or self.top_k
        if k != self.top_k:
            self._retriever = self._index.as_retriever(similarity_top_k=k)
        nodes_with_scores = self._retriever.retrieve(query)
        hits: list[RetrievalHit] = []
        for nws in nodes_with_scores:
            score = float(nws.score or 0.0)
            if self.similarity_threshold is not None and score < self.similarity_threshold:
                continue
            node = nws.node
            hits.append(
                RetrievalHit(
                    text=node.get_content(metadata_mode="none"),
                    score=score,
                    metadata=dict(node.metadata or {}),
                    node_id=node.node_id,
                )
            )
        return hits

def get_faq_retriever(
    top_k: int = 5,
    similarity_threshold: float | None = None,
) -> FAQRetriever:
    return VectorFAQRetriever(top_k=top_k, similarity_threshold=similarity_threshold)