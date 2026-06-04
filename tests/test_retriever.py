from fin-agent-platform.app.retrieval.retriever import RetrievalHit


import pytest
from tests.conftest import requires_embedding_key  # 或单独 requires_pg_index

from app.retrieval import get_faq_retriever

# 与你 knowledge/raw 内容对应的 3 条
QUERIES = [
    "A股交易时间如何安排？",
    "什么是 T+1 交易制度？",
    "期货保证金制度如何运作？",
]


@requires_embedding_key
@pytest.mark.integration
@pytest.mark.parametrize("query", QUERIES)
def test_retriever_returns_hits(query: str):
    retriever = get_faq_retriever(top_k=3, similarity_threshold=0.3)
    hits = retriever.search(query, top_k=3)
    
    print(f"\n===== query: {query} =====")
    for i, h in enumerate[RetrievalHit](hits):
        print(f"[{i}] score={h.score:.4f} source={h.metadata.get('source')} section={h.metadata.get('section')}")
        print(h.text[:300])
        print("-" * 40)

    assert len(hits) >= 1
    assert hits[0].text
    assert hits[0].metadata.get("source")
    assert hits[0].score is not None