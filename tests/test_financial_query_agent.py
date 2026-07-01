"""financial_query 子图单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.agents.components.finance_agent.financial_query_agent import financial_query_agent
from app.services.financial import (
    FinancialFactExtraction,
    FinancialSqlResultRow,
    FinancialSqlTemplateChoice,
    GeneratedFinancialSql,
)


@pytest.mark.asyncio
async def test_financial_query_agent_no_facts_returns_no_result_message():
    """模板命中但底层无数据时，应返回稳定的 no-result 文案。"""
    params = FinancialFactExtraction(
        companies=["未知公司"],
        years=[2024],
        metrics=["营业收入"],
    )

    with (
        patch(
            "app.agents.components.finance_agent.financial_query_agent.extract_intent.node._extract_query_params",
            new=AsyncMock(return_value=params),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.template_sql.node._choose_template",
            new=AsyncMock(
                return_value=FinancialSqlTemplateChoice(
                    route="template",
                    template_id="exact_metric_lookup",
                    reason="命中模板",
                    confidence=0.9,
                )
            ),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.template_sql.node.FinancialFactService.run_sql_template",
            new=AsyncMock(return_value=([], "SELECT 1", {"limit": 5}, [])),
        ),
    ):
        out = await financial_query_agent.ainvoke(
            {"messages": [HumanMessage(content="未知公司 2024 营收")]},
            {},
        )

    assert "暂未在结构化财务数据库" in out["messages"][-1].content
    assert out["task_results"][0]["type"] == "financial_query"
    assert out["citations"] == []
    assert out["steps"] == [
        "financial_query_extract",
        "template_sql_agent",
    ]


@pytest.mark.asyncio
async def test_financial_query_agent_with_facts_returns_template_answer():
    """模板路径命中事实后，应保留格式化答案、引用和子任务编号。"""
    params = FinancialFactExtraction(
        companies=["宁德时代"],
        years=[2024],
        metrics=["营业收入"],
    )
    row = FinancialSqlResultRow(
        company_name="宁德时代",
        ticker="300750",
        fiscal_year=2024,
        period_year=2024,
        metric_name="营业收入",
        raw_value="362,012,554",
        unit="千元",
        currency="人民币",
        source="CATL_Annual_Report_2024.pdf",
        page_num=12,
        doc_id="PDF-AR-CATL-2024",
    )

    with (
        patch(
            "app.agents.components.finance_agent.financial_query_agent.extract_intent.node._extract_query_params",
            new=AsyncMock(return_value=params),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.template_sql.node._choose_template",
            new=AsyncMock(
                return_value=FinancialSqlTemplateChoice(
                    route="template",
                    template_id="exact_metric_lookup",
                    reason="命中模板",
                    confidence=0.9,
                )
            ),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.template_sql.node.FinancialFactService.run_sql_template",
            new=AsyncMock(return_value=([row], "SELECT 1", {"limit": 5}, [])),
        ),
    ):
        out = await financial_query_agent.ainvoke(
            {
                "messages": [HumanMessage(content="宁德时代 2024 营业收入")],
                "sub_question": "宁德时代 2024 年营业收入",
                "sub_task_id": "t1",
            },
            {},
        )

    assert "营业收入" in out["messages"][-1].content
    assert out["task_results"][0]["sub_task_id"] == "t1"
    assert len(out["citations"]) == 1
    assert out["steps"] == [
        "financial_query_extract",
        "template_sql_agent",
    ]


@pytest.mark.asyncio
async def test_financial_query_agent_routes_clarification_to_clarification_agent():
    """模板节点要求补充信息时，应进入 clarification_agent。"""
    params = FinancialFactExtraction(
        companies=["苹果"],
        years=[],
        metrics=[],
    )

    with (
        patch(
            "app.agents.components.finance_agent.financial_query_agent.extract_intent.node._extract_query_params",
            new=AsyncMock(return_value=params),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.template_sql.node._choose_template",
            new=AsyncMock(
                return_value=FinancialSqlTemplateChoice(
                    route="clarify",
                    missing_fields=["company", "metric"],
                    reason="信息不足",
                    confidence=0.95,
                )
            ),
        ),
    ):
        out = await financial_query_agent.ainvoke(
            {"messages": [HumanMessage(content="苹果怎么样")]},
            {},
        )

    assert "公司名称" in out["messages"][-1].content
    assert out["steps"] == [
        "financial_query_extract",
        "template_sql_agent",
        "clarification_agent",
    ]


@pytest.mark.asyncio
async def test_financial_query_agent_routes_sql_fallback_to_text_to_sql_agent():
    """高复杂度问题应进入 text_to_sql_agent 并返回执行结果。"""
    params = FinancialFactExtraction(
        companies=["宁德时代"],
        years=[2022, 2023, 2024],
        metrics=["营业收入", "净利润", "研发费用"],
        operation="compare",
    )
    row = FinancialSqlResultRow(
        company_name="宁德时代",
        fiscal_year=2024,
        period_year=2024,
        metric_name="营业收入",
        raw_value="362,012,554",
        unit="千元",
        source="CATL_Annual_Report_2024.pdf",
        page_num=12,
        doc_id="PDF-AR-CATL-2024",
    )

    with (
        patch(
            "app.agents.components.finance_agent.financial_query_agent.extract_intent.node._extract_query_params",
            new=AsyncMock(return_value=params),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.template_sql.node._choose_template",
            new=AsyncMock(
                return_value=FinancialSqlTemplateChoice(
                    route="sql",
                    reason="复杂查询",
                    confidence=0.85,
                )
            ),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.text_to_sql.node._generate_sql",
            new=AsyncMock(
                return_value=GeneratedFinancialSql(
                    sql="SELECT 1",
                    params={"limit": 5},
                    reason="复杂查询 SQL",
                    route="execute",
                )
            ),
        ),
        patch(
            "app.agents.components.finance_agent.financial_query_agent.text_to_sql.node.FinancialFactService.run_generated_sql",
            new=AsyncMock(return_value=[row]),
        )
    ):
        out = await financial_query_agent.ainvoke(
            {"messages": [HumanMessage(content="宁德时代近三年多指标对比")]},
            {},
        )

    assert "营业收入" in out["messages"][-1].content
    assert out["task_results"][0]["type"] == "financial_query"
    assert out["steps"] == [
        "financial_query_extract",
        "template_sql_agent",
        "text_to_sql_agent",
    ]
