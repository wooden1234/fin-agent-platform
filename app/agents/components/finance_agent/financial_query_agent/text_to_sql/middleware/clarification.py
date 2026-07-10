"""text_to_sql 信息不足追问中间件。"""

from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.components.finance_agent.financial_query_agent.services.schemas import (
    GeneratedFinancialSql,
)
from app.agents.components.finance_agent.financial_query_agent.text_to_sql.middleware.base import (
    MiddlewareResult,
)
from app.agents.components.finance_agent.financial_query_agent.text_to_sql.state import (
    TextToSqlState,
)
from app.core.logger import get_logger

logger = get_logger(service="financial_query")

FINANCIAL_QUERY_TEXT_TO_SQL_CLARIFICATION_PROMPT = """你是复杂结构化查询补问助手。请根据用户问题和当前缺失字段，生成一句简洁中文追问。

要求：
1. 只追问当前仍不足以生成 SQL 的关键信息
2. 一句话即可，不解释系统实现
3. 优先点名需要补充的字段或口径
"""

FINANCIAL_QUERY_TEXT_TO_SQL_NEEDS_CLARIFICATION_ANSWER = (
    "当前问题中的查询条件还不够明确。请补充更具体的公司名称、财务指标、统计年份或计算口径。"
)

_VAGUE_QUESTION_MARKERS = ("怎么样", "如何", "什么情况", "表现如何", "好不好")


def _fallback_clarification(missing_fields: list[str]) -> str:
    if missing_fields:
        field_names = {
            "company": "公司名称",
            "metric": "财务指标",
            "year": "统计年份",
            "period": "统计周期",
            "scope": "统计口径",
            "calculation": "计算方式",
        }
        labels = [field_names.get(field, field) for field in missing_fields]
        return f"请补充更明确的{'、'.join(labels)}，我再继续生成查询。"
    return FINANCIAL_QUERY_TEXT_TO_SQL_NEEDS_CLARIFICATION_ANSWER


def _is_vague_question(question: str) -> bool:
    normalized = question.strip()
    if len(normalized) < 4:
        return True
    return any(marker in normalized for marker in _VAGUE_QUESTION_MARKERS) and len(normalized) < 12


async def _build_clarification_answer(
    *,
    question: str,
    missing_fields: list[str],
    route_reason: str,
    config: RunnableConfig | None = None,
) -> str:
    fallback = _fallback_clarification(missing_fields)
    try:
        llm = get_router_llm()
        result = cast(
            str,
            await llm.ainvoke(
                [
                    ("system", FINANCIAL_QUERY_TEXT_TO_SQL_CLARIFICATION_PROMPT),
                    (
                        "human",
                        f"用户问题：{question}\n缺失字段：{missing_fields}\n原因：{route_reason}",
                    ),
                ],
                config=config,
            ),
        )
        content = getattr(result, "content", result)
        return str(content).strip() or fallback
    except Exception:
        logger.exception("text_to_sql clarification middleware failed")
        return fallback


class ClarificationMiddleware:
    """模糊问题或生成阶段判定信息不足时，截断流程并返回追问。"""

    async def before_generate(
        self,
        state: TextToSqlState,
        config: RunnableConfig | None = None,
    ) -> MiddlewareResult | None:
        del config
        question = state["question"].strip()
        if not _is_vague_question(question):
            return None
        return MiddlewareResult(
            halt=True,
            halt_reason="clarify",
            halt_answer=FINANCIAL_QUERY_TEXT_TO_SQL_NEEDS_CLARIFICATION_ANSWER,
            state_updates={
                "missing_fields": ["company", "metric", "year"],
                "route_reason": "问题过于模糊，无法直接生成 SQL。",
            },
        )

    async def _clarify_from_generation(
        self,
        state: TextToSqlState,
        generated: GeneratedFinancialSql,
        config: RunnableConfig | None = None,
    ) -> MiddlewareResult | None:
        if generated.route != "clarify":
            return None
        answer = await _build_clarification_answer(
            question=state["question"],
            missing_fields=list(generated.missing_fields),
            route_reason=generated.reason,
            config=config,
        )
        return MiddlewareResult(
            halt=True,
            halt_reason="clarify",
            halt_answer=answer,
            state_updates={
                "missing_fields": list(generated.missing_fields),
                "route_reason": generated.reason,
            },
        )

    async def after_generate(
        self,
        state: TextToSqlState,
        generated: GeneratedFinancialSql,
        config: RunnableConfig | None = None,
    ) -> MiddlewareResult | None:
        return await self._clarify_from_generation(state, generated, config)

    async def after_correct(
        self,
        state: TextToSqlState,
        corrected: GeneratedFinancialSql,
        config: RunnableConfig | None = None,
    ) -> MiddlewareResult | None:
        return await self._clarify_from_generation(state, corrected, config)


__all__ = ["ClarificationMiddleware"]
