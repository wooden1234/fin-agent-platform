"""FAQ 子图节点：Retriever → context → LLM（Week 3 Day 3）。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_faq_llm
from app.agents.prompts.faq import FAQ_BUSY_ANSWER, FAQ_SYSTEM_PROMPT, NO_CONTEXT_ANSWER
from app.agents.states import Citation, FinAgentState
from app.core.config import settings
from app.core.logger import get_logger
from app.retrieval import RetrievalHit, get_faq_retriever

logger = get_logger(service="faq_agent")


def _latest_user_query(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    raise ValueError("无用户消息")


def _build_context(hits: list[RetrievalHit]) -> str:
    parts = []
    for i, h in enumerate(hits, start=1):
        src = h.metadata.get("source", "unknown")
        sec = h.metadata.get("section", "")
        parts.append(f"[{i}] source={src} section={sec}\n{h.text}")
    return "\n\n".join(parts)


def _hits_to_citations(hits: list[RetrievalHit]) -> list[Citation]:
    return [
        {"source": h.metadata.get("source", ""), "snippet": (h.text or "")[:200]}
        for h in hits
    ]


async def faq_agent(
    state: FinAgentState,
    config: RunnableConfig | None = None,
) -> dict:
    query = _latest_user_query(list(state.get("messages") or []))
    logger.info("faq_agent query={}", query[:80])

    retriever = get_faq_retriever(top_k=3, similarity_threshold=None)
    hits = retriever.search(query, top_k=3)

    min_score = settings.FAQ_MIN_RELEVANCE_SCORE
    if not hits or hits[0].score < min_score:
        logger.warning(
            "faq_agent no_context hits={} top1_score={}",
            len(hits),
            hits[0].score if hits else None,
        )
        return {
            "messages": [AIMessage(content=NO_CONTEXT_ANSWER)],
            "citations": [],
        }

    context = _build_context(hits)
    citations = _hits_to_citations(hits)

    llm_messages = [
        SystemMessage(content=FAQ_SYSTEM_PROMPT.format(context=context)),
        HumanMessage(content=query),
    ]
    try:
        # resp = await get_faq_llm().ainvoke(llm_messages, config=config)
        # answer = resp.content if isinstance(resp.content, str) else str(resp.content)
        llm = get_faq_llm()
        parts: list[str] = []
        async for chunk in llm.astream(llm_messages, config=config):
            # ChatDeepSeek 流式时 chunk 是 AIMessageChunk
            if chunk.content:
                parts.append(
                    chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                )
        answer = "".join(parts)
    except Exception:
        logger.exception("faq_agent llm invoke failed")
        return {
            "messages": [AIMessage(content=FAQ_BUSY_ANSWER)],
            "citations": citations,
        }

    logger.info("faq_agent hits={} top1_score={:.4f}", len(hits), hits[0].score)
    return {
        "messages": [AIMessage(content=answer)],
        "citations": citations,
    }