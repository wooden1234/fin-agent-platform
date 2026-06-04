import asyncio
from functools import lru_cache
from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.models.user import User
from app.retrieval import get_faq_retriever
from app.schemas.rag import RagHitItem, RagSearchResponse


router = APIRouter(prefix="/rag", tags=["rag"])

@lru_cache(maxsize=1)
def _get_retriever():
    """进程内复用，避免每次请求 load_index。"""
    return get_faq_retriever(top_k=3, similarity_threshold=None)

@router.post("/search",response_model=RagSearchResponse)
async def search_rag(query: str = Query(..., description="搜索查询"), current_user: User = Depends(get_current_user)):
    retriever = _get_retriever()
    hits = await asyncio.to_thread(retriever.search, query, top_k=3)
    hits = [
        RagHitItem(
            text=h.text,
            score=h.score,
            metadata=h.metadata,
            node_id=h.node_id,
        )
        for h in hits
    ]
    return RagSearchResponse(query=query, top_k=len(hits), hits=hits)