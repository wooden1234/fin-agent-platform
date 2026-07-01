"""financial_query_agent 澄清节点。"""

from __future__ import annotations

import json
from typing import cast

from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState
from app.agents.components.finance_agent.financial_query_agent.common import financial_query_output
from app.agents.components.finance_agent.financial_query_agent.clarification.prompts import (
    FINANCIAL_QUERY_CLARIFICATION_PROMPT,
    FINANCIAL_QUERY_NEEDS_CLARIFICATION_ANSWER,
)
from app.core.logger import get_logger
from app.services.financial.schemas import FinancialQueryIntent

logger = get_logger(service="financial_query")


def _fallback_clarification(intent: FinancialQueryIntent | None, missing_fields: list[str]) -> str:
    if missing_fields:
        field_names = {"company": "公司名称", "metric": "财务指标", "year": "统计年份"}
        labels = [field_names.get(field, field) for field in missing_fields]
        return f"请补充更明确的{'、'.join(labels)}，我再继续查询。"
    if intent is not None and intent.ambiguity:
        return "请补充更明确的公司名称、指标名称或统计年份，避免歧义后我再继续查询。"
    return FINANCIAL_QUERY_NEEDS_CLARIFICATION_ANSWER


async def _generate_clarification_question(
    intent: FinancialQueryIntent | None,
    missing_fields: list[str],
    config: RunnableConfig = None,
) -> str:
    fallback = _fallback_clarification(intent, missing_fields)
    if intent is None:
        return fallback
    try:
        llm = get_router_llm()
        result = cast(
            str,
            await llm.ainvoke(
                [
                    ("system", FINANCIAL_QUERY_CLARIFICATION_PROMPT),
                    ("human", f"缺失字段：{missing_fields}\n歧义信息：{intent.ambiguity}\n当前意图：{json.dumps(intent.model_dump(), ensure_ascii=False)}"),
                ],
                config=config,
            ),
        )
        content = getattr(result, "content", result)
        return str(content).strip() or fallback
    except Exception:
        logger.exception("clarification_agent llm generation failed")
        return fallback


async def clarification_agent(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    intent = state.get("financial_query_intent")
    missing_fields = list(state.get("financial_query_missing_fields") or [])
    answer = await _generate_clarification_question(
        intent if isinstance(intent, FinancialQueryIntent) else None,
        missing_fields,
        config,
    )
    return financial_query_output(state, answer=answer, step="clarification_agent")
