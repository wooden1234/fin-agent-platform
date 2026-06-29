"""DB Agent 节点单元测试（mock 抽取 + DB 查询）。"""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.agents.subgraphs.db_agent import db_agent
from app.services.financial_fact_service import FinancialFactQuery


def _mock_fact():
    from decimal import Decimal
    from types import SimpleNamespace

    return SimpleNamespace(
        title="CATL Annual Report 2024",
        ticker="300750",
        fiscal_year=2024,
        period_year=2024,
        metric_name="营业收入",
        raw_value="362,012,554",
        value=Decimal("362012554"),
        unit="千元",
        currency="人民币",
        source="CATL_Annual_Report_2024.pdf",
        page_num=12,
        doc_id="PDF-AR-CATL-2024",
        metric_alias="",
    )


@pytest.mark.asyncio
async def test_db_agent_no_facts_returns_no_result_message():
    params = FinancialFactQuery(
        companies=["未知公司"],
        years=[2024],
        metrics=["营业收入"],
    )

    with (
        patch(
            "app.agents.subgraphs.db_agent._extract_query_params",
            new=AsyncMock(return_value=params),
        ),
        patch(
            "app.agents.subgraphs.db_agent.FinancialFactService.execute_query",
            new=AsyncMock(return_value=([], "exact_metric_lookup")),
        ),
    ):
        out = await db_agent(
            {"messages": [HumanMessage(content="未知公司 2024 营收")]}, {}
        )

    assert "暂未在结构化财务数据库" in out["messages"][0].content
    assert out["task_results"][0]["type"] == "db"
    assert out["citations"] == []


@pytest.mark.asyncio
async def test_db_agent_with_facts_returns_template_answer():
    params = FinancialFactQuery(
        companies=["宁德时代"],
        years=[2024],
        metrics=["营业收入"],
    )
    fact = _mock_fact()

    with (
        patch(
            "app.agents.subgraphs.db_agent._extract_query_params",
            new=AsyncMock(return_value=params),
        ),
        patch(
            "app.agents.subgraphs.db_agent.FinancialFactService.execute_query",
            new=AsyncMock(return_value=([fact], "exact_metric_lookup")),
        ),
    ):
        out = await db_agent(
            {
                "messages": [HumanMessage(content="宁德时代 2024 营业收入")],
                "sub_question": "宁德时代 2024 年营业收入",
                "sub_task_id": "t1",
            },
            {},
        )

    assert "营业收入" in out["messages"][0].content
    assert out["task_results"][0]["sub_task_id"] == "t1"
    assert len(out["citations"]) == 1
    assert out["steps"] == ["db_agent", "exact_metric_lookup"]
