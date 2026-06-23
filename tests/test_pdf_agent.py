"""PDF 节点单元测试（检索 mock + LLM mock）。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agents.subgraphs.pdf import pdf_agent
from app.retrieval import RetrievalHit


def _hit(
    text: str,
    score: float,
    source: str = "2024_annual_report.pdf",
    page_num: int = 12,
) -> RetrievalHit:
    return RetrievalHit(
        text=text,
        score=score,
        metadata={
            "source": source,
            "category": "annual_reports",
            "section": "管理层讨论与分析",
            "page_num": page_num,
        },
    )


async def _chunks(*contents: str):
    for content in contents:
        yield AIMessageChunk(content=content)


@pytest.mark.asyncio
async def test_pdf_agent_no_hits_returns_no_context():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = []

    with patch("app.agents.subgraphs.pdf.get_pdf_retriever", return_value=mock_retriever):
        out = await pdf_agent({"messages": [HumanMessage(content="查年报收入")]}, {})

    assert "PDF 文档库中暂未找到" in out["messages"][0].content
    assert out["citations"] == []


@pytest.mark.asyncio
async def test_pdf_agent_low_score_returns_no_context():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = [_hit("x", score=0.1)]

    with patch("app.agents.subgraphs.pdf.get_pdf_retriever", return_value=mock_retriever):
        out = await pdf_agent({"messages": [HumanMessage(content="低分问题")]}, {})

    assert out["citations"] == []


@pytest.mark.asyncio
async def test_pdf_agent_with_hits_calls_llm_and_returns_page_citation():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = [
        _hit("公司营业收入同比增长，主要来自主营业务扩张。", score=0.82)
    ]
    mock_llm = MagicMock()
    mock_llm.astream.return_value = _chunks("营业收入", "同比增长 [1]")

    with (
        patch("app.agents.subgraphs.pdf.get_pdf_retriever", return_value=mock_retriever),
        patch("app.agents.subgraphs.pdf.get_pdf_llm", return_value=mock_llm),
    ):
        out = await pdf_agent({"messages": [HumanMessage(content="年报如何描述收入变化？")]}, {})

    assert "营业收入" in out["messages"][0].content
    assert len(out["citations"]) == 1
    assert out["citations"][0]["source"] == "2024_annual_report.pdf"
    assert out["citations"][0]["page"] == 12
    mock_llm.astream.assert_called_once()
