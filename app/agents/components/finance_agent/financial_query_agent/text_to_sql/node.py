"""financial_query_agent SQL fallback 节点。"""

from __future__ import annotations

import json
from typing import cast

from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState
from app.agents.components.finance_agent.financial_query_agent.common import financial_query_output, query_from_state
from app.agents.components.finance_agent.financial_query_agent.text_to_sql.prompts import (
    FINANCIAL_QUERY_SQL_UNSAFE_ANSWER,
    FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER,
    FINANCIAL_QUERY_TEXT_TO_SQL_PROMPT,
)
from app.core.logger import get_logger
from app.services.financial import (
    FinancialFactService,
    GeneratedFinancialSql,
    FinancialQueryIntent,
    SqlValidationError,
)

logger = get_logger(service="financial_query")


async def _generate_sql(
    question: str,
    intent: FinancialQueryIntent,
    config: RunnableConfig = None,
) -> GeneratedFinancialSql:
    fallback = GeneratedFinancialSql(
        sql="",
        params={},
        reason="复杂问题暂未生成可执行 SQL。",
        route="clarify" if not intent.companies or not intent.metrics else "execute",
        missing_fields=[field for field, values in (("company", intent.companies), ("metric", intent.metrics)) if not values],
    )
    try:
        llm = get_router_llm()
        return cast(
            GeneratedFinancialSql,
            await llm.with_structured_output(GeneratedFinancialSql, method="json_mode").ainvoke(
                [
                    ("system", FINANCIAL_QUERY_TEXT_TO_SQL_PROMPT),
                    ("human", f"用户问题：{question}\n结构化意图：{json.dumps(intent.model_dump(), ensure_ascii=False)}"),
                ],
                config=config,
            ),
        )
    except Exception:
        logger.exception("text_to_sql_agent sql generation failed")
        fallback.route = "clarify"
        return fallback


async def text_to_sql_agent(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    intent = state.get("financial_query_intent")
    if not isinstance(intent, FinancialQueryIntent):
        return financial_query_output(state, answer=FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER, step="text_to_sql_agent")

    question = str(state.get("financial_query_text") or query_from_state(state))
    generated = await _generate_sql(question, intent, config)
    if generated.route in ("clarify",):
        answer = "请补充更明确的公司名称、财务指标或统计年份后，我再继续生成查询。"
        return {
            **financial_query_output(state, answer=answer, step="text_to_sql_agent"),
            "financial_query_missing_fields": generated.missing_fields,
            "financial_query_route_reason": generated.reason,
        }

    try:
        rows = await FinancialFactService.run_generated_sql(generated.sql, params=generated.params, limit=intent.top_k)
    except SqlValidationError:
        logger.exception("text_to_sql_agent generated sql rejected")
        return {
            **financial_query_output(state, answer=FINANCIAL_QUERY_SQL_UNSAFE_ANSWER, step="text_to_sql_agent"),
            "financial_query_sql": generated.sql,
            "financial_query_sql_params": generated.params,
            "financial_query_route_reason": generated.reason,
        }
    except Exception:
        logger.exception("text_to_sql_agent sql execution failed")
        return financial_query_output(state, answer=FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER, step="text_to_sql_agent")

    answer = FinancialFactService.format_sql_answer(rows) if rows else FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER
    citations = FinancialFactService.sql_rows_to_citations(rows) if rows else []
    return financial_query_output(state, answer=answer, citations=citations, step="text_to_sql_agent")
