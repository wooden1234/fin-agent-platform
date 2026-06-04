import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.vector_stores.postgres import PGVectorStore
from app.retrieval.embeddings import get_embed_model


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)
TABLE_NAME = os.getenv("PGVECTOR_TABLE_NAME", "fin_faq_vectors")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

def _pg_connection_strings() -> tuple[str, str]:
    """同步 / 异步连接串，供 PGVectorStore 使用。"""
    sync_url = os.getenv("PGVECTOR_DATABASE_URL")
    if not sync_url:
        raw = os.getenv("DATABASE_URL", "")
        sync_url = raw.replace("postgresql+asyncpg://", "postgresql://")
    if not sync_url:
        raise RuntimeError(
            "未配置 PGVECTOR_DATABASE_URL 或 DATABASE_URL，无法连接向量库"
        )
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")
    return sync_url, async_url

@lru_cache(maxsize=1)
def get_vector_store(*, rebuild: bool = False) -> PGVectorStore:
    sync_url, async_url = _pg_connection_strings()
    vector_store = PGVectorStore.from_params(
        connection_string=sync_url,
        async_connection_string=async_url,
        table_name=TABLE_NAME,
        embed_dim=EMBED_DIM,
        schema_name="public",
        perform_setup=True,
    )
    if rebuild:
        vector_store.clear()
    return vector_store

def build_index(
    nodes: list[TextNode],
    *,
    rebuild: bool = False,
    show_progress: bool = True,
) -> VectorStoreIndex:
    """将 ingest 得到的 nodes 写入 pgvector（会调用 Embedding API）。"""
    embed_model = get_embed_model()
    Settings.embed_model = embed_model
    vector_store = get_vector_store(rebuild=rebuild)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=show_progress,
    )
@lru_cache(maxsize=1)
def load_index() -> VectorStoreIndex:
    """从已有 PG 表加载索引（检索用，不重新 embed）。"""
    embed_model = get_embed_model()
    Settings.embed_model = embed_model
    vector_store = get_vector_store(rebuild=False)
    return VectorStoreIndex.from_vector_store(
        vector_store,
        embed_model=embed_model,
    )
def main() -> None:
    import argparse
    from app.retrieval.ingest import run_ingest
    parser = argparse.ArgumentParser(description="构建 FAQ 向量索引")
    parser.add_argument("--rebuild", action="store_true", help="清空表后全量重建")
    args = parser.parse_args()
    nodes = run_ingest()
    print(f"nodes: {len(nodes)}")
    build_index(nodes, rebuild=args.rebuild)
    print(f"index built → table={TABLE_NAME}, dim={EMBED_DIM}")
if __name__ == "__main__":
    main()