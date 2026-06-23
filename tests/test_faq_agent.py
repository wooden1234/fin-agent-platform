"""FAQ 节点单元测试（检索 mock + 可选 LLM 集成）。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agents.subgraphs.faq import faq_agent
from app.retrieval import RetrievalHit


def _hit(text: str, score: float, source: str = "01_Stock_Trading_Rules_FAQ.md") -> RetrievalHit:
    return RetrievalHit(
        text=text,
        score=score,
        metadata={"source": source, "section": "Q2：测试"},
    )


async def _chunks(*contents: str):
    for content in contents:
        yield AIMessageChunk(content=content)


@pytest.mark.asyncio
async def test_faq_agent_no_hits_returns_no_context():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = []

    with patch("app.agents.subgraphs.faq.get_faq_retriever", return_value=mock_retriever):
        out = await faq_agent({"messages": [HumanMessage(content="未知问题")]}, {})

    assert "暂未找到" in out["messages"][0].content
    assert out["citations"] == []


@pytest.mark.asyncio
async def test_faq_agent_low_score_returns_no_context():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = [_hit("x", score=0.1)]

    with patch("app.agents.subgraphs.faq.get_faq_retriever", return_value=mock_retriever):
        out = await faq_agent({"messages": [HumanMessage(content="低分问题")]}, {})

    assert out["citations"] == []


@pytest.mark.asyncio
async def test_faq_agent_with_hits_calls_llm():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = [
        _hit("T+1 是指当日买入下一交易日才能卖出。", score=0.75)
    ]
    mock_llm = MagicMock()
    mock_llm.astream.return_value = _chunks("T+1 ", "制度说明 [1]")

    with (
        patch("app.agents.subgraphs.faq.get_faq_retriever", return_value=mock_retriever),
        patch("app.agents.subgraphs.faq.get_faq_llm", return_value=mock_llm),
    ):
        out = await faq_agent({"messages": [HumanMessage(content="什么是 T+1？")]}, {})

    assert "T+1" in out["messages"][0].content
    assert len(out["citations"]) == 1
    assert out["citations"][0]["source"] == "01_Stock_Trading_Rules_FAQ.md"
    mock_llm.astream.assert_called_once()
