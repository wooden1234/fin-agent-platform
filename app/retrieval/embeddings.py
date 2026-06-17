"""W2：Embedding 工厂（DashScope 文本向量）。"""

import os
from functools import lru_cache

from llama_index.embeddings.dashscope import DashScopeEmbedding


def _resolve_embedding_credentials() -> tuple[str, str]:
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

    if not api_key:
        raise RuntimeError(
            "未配置 Embedding API Key，请在 .env 中设置 QWEN_API_KEY 或 DASHSCOPE_API_KEY"
        )
    return api_key, model


@lru_cache(maxsize=1)
def get_embed_model() -> DashScopeEmbedding:
    api_key, model = _resolve_embedding_credentials()
    return DashScopeEmbedding(model_name=model, api_key=api_key)
