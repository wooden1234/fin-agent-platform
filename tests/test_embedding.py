"""Embedding 连通性集成测试（需有效 API Key 与网络）。"""

import pytest

from app.retrieval.embeddings import get_embed_model
from tests.conftest import requires_embedding_key

SAMPLE_TEXT = "信用卡年费如何收取？"


@requires_embedding_key
@pytest.mark.integration
def test_embedding_returns_non_empty_vector():
    embed_model = get_embed_model()
    vector = embed_model.get_text_embedding(SAMPLE_TEXT)

    assert isinstance(vector, list)
    assert len(vector) > 0
    assert all(isinstance(x, float) for x in vector)


@requires_embedding_key
@pytest.mark.integration
def test_embedding_batch_same_length():
    embed_model = get_embed_model()
    texts = [SAMPLE_TEXT, "理财产品赎回 T+几到账？"]
    vectors = embed_model.get_text_embedding_batch(texts)

    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])
    assert len(vectors[0]) > 0
