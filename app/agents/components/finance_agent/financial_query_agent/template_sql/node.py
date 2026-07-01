"""financial_query_agent 模板 SQL 执行节点。"""

from __future__ import annotations

import json
from typing import cast

from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState
from app.agents.components.finance_agent.financial_query_agent.common import (
    database_failure_output,
    financial_query_output,
    query_from_state,
)
from app.agents.components.finance_agent.financial_query_agent.template_sql.prompts import (
    FINANCIAL_QUERY_TEMPLATE_SELECTION_PROMPT,
)
from app.core.logger import get_logger
from app.services.financial import (
    FinancialFactService,
    FinancialQueryRouter,
    FinancialSqlTemplateChoice,
    FinancialSqlTemplateRegistry,
    FinancialQueryIntent,
    SqlValidationError,
)

logger = get_logger(service="financial_query")

FINANCIAL_QUERY_NO_RESULT_ANSWER = "暂未在结构化财务数据库中找到相关指标，建议查阅年报 PDF 文档获取更多信息。"


def _default_missing_fields(intent: FinancialQueryIntent) -> list[str]:
    missing_fields: list[str] = []
    if not intent.companies:
        missing_fields.append("company")
    if not intent.metrics:
        missing_fields.append("metric")
    if intent.operation == "lookup" and not intent.years:
        missing_fields.append("year")
    return missing_fields


def _fallback_choice(question: str, intent: FinancialQueryIntent) -> FinancialSqlTemplateChoice:
    if intent.has_template_blocking_ambiguity():
        return FinancialSqlTemplateChoice(
            route="clarify",
            missing_fields=sorted({str(item.get("entity_type") or "") for item in intent.ambiguity if item.get("entity_type")}) or _default_missing_fields(intent),
            reason="标准化阶段仍存在实体歧义，需要用户补充。",
            confidence=0.9,
        )
    template = FinancialQueryRouter.match_template(question, intent)
    if template is not None:
        return FinancialSqlTemplateChoice(route="template", template_id=template.name, reason="规则路由命中了现有模板。", confidence=0.8)
    missing_fields = _default_missing_fields(intent)
    if missing_fields:
        return FinancialSqlTemplateChoice(route="clarify", missing_fields=missing_fields, reason="模板查询缺少必要字段。", confidence=0.8)
    return FinancialSqlTemplateChoice(route="sql", reason="问题超出模板覆盖范围，转入复杂 SQL。", confidence=0.7)


async def _choose_template(
    question: str,
    intent: FinancialQueryIntent,
    config: RunnableConfig = None,
) -> FinancialSqlTemplateChoice:
    fallback = _fallback_choice(question, intent)
    try:
        llm = get_router_llm()
        choice = cast(
            FinancialSqlTemplateChoice,
            await llm.with_structured_output(FinancialSqlTemplateChoice, method="json_mode").ainvoke(
                [
                    ("system", f"{FINANCIAL_QUERY_TEMPLATE_SELECTION_PROMPT}\n\n可用模板：\n{FinancialSqlTemplateRegistry.template_examples()}"),
                    ("human", f"用户问题：{question}\n结构化意图：{json.dumps(intent.model_dump(), ensure_ascii=False)}"),
                ],
                config=config,
            ),
        )
    except Exception:
        logger.exception("template_sql_agent template selection failed")
        return fallback

    if choice.route == "template":
        if not choice.template_id or choice.template_id not in FinancialSqlTemplateRegistry.valid_template_ids():
            return fallback
        return choice
    if choice.route == "clarify" and not choice.missing_fields:
        choice.missing_fields = _default_missing_fields(intent)
    if not choice.reason:
        choice.reason = fallback.reason
    if choice.route not in {"template", "clarify", "sql"}:
        return fallback
    return choice


async def template_sql_agent(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    intent = state.get("financial_query_intent")
    question = str(state.get("financial_query_text") or query_from_state(state))

    if not isinstance(intent, FinancialQueryIntent):
        logger.error("template_sql_agent missing intent")
        return database_failure_output(state, step="template_sql_agent_error")

    choice = await _choose_template(question, intent, config)
    base_state = {
        "financial_query_route": choice.route,
        "financial_query_route_reason": choice.reason,
        "financial_query_missing_fields": choice.missing_fields,
        "financial_query_template_id": choice.template_id,
        "steps": ["template_sql_agent"],
    }

    if choice.route == "clarify":
        return base_state
    if choice.route == "sql":
        return base_state
    if not choice.template_id:
        return {**base_state, "financial_query_route": "clarify", "financial_query_missing_fields": _default_missing_fields(intent)}

    try:
        rows, sql, params, missing_fields = await FinancialFactService.run_sql_template(choice.template_id, intent, limit=intent.top_k)
    except SqlValidationError:
        logger.exception("template_sql_agent template sql validation failed")
        return {**base_state, "financial_query_route": "sql", "financial_query_route_reason": "模板 SQL 未通过安全校验，转入复杂 SQL 节点。"}
    except Exception:
        logger.exception("template_sql_agent template execution failed")
        return database_failure_output(state, step="template_sql_agent_error")

    if missing_fields:
        return {**base_state, "financial_query_route": "clarify", "financial_query_missing_fields": missing_fields, "financial_query_route_reason": "模板所需字段不足，转入补充节点。"}
    if not rows:
        return {**base_state, "financial_query_route": "end", "financial_query_route_reason": "模板查询无结果，提前结束。"}
    return {
        **base_state,
        "financial_query_route": "end",
        "messages": [FinancialFactService.format_sql_answer(rows)],
    }
