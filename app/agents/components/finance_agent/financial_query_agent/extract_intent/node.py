"""financial_query_agent 抽取节点。"""

from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState
from app.agents.components.finance_agent.financial_query_agent.extract_intent.prompts import (
    FINANCIAL_QUERY_EXTRACT_PROMPT,
)
from app.agents.components.finance_agent.financial_query_agent.common import (
    query_from_state,
    sub_task_id_from_state,
)
from app.core.logger import get_logger
from app.services.financial import FinancialFactExtraction
from app.services.financial.schemas import FinancialQueryIntent

logger = get_logger(service="financial_query")


async def _extract_query_params(
    question: str,
    config: RunnableConfig = None,
) -> FinancialFactExtraction:
    llm = get_router_llm()
    return cast(
        FinancialFactExtraction,
        await llm.with_structured_output(
            FinancialFactExtraction, method="json_mode"
        ).ainvoke(
            [
                ("system", FINANCIAL_QUERY_EXTRACT_PROMPT),
                ("human", f"用户问题：{question}"),
            ],
            config=config,
        ),
    )


async def extract_intent(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    query = query_from_state(state)
    sub_task_id = sub_task_id_from_state(state)
    logger.info("financial_query query={} sub_task_id={}", query[:80], sub_task_id)

    try:
        extraction = await _extract_query_params(query, config)
    except Exception:
        logger.exception("financial_query param extraction failed")
        extraction = FinancialFactExtraction(
            companies=[query],
            years=[],
            metrics=[],
            operation="lookup",
        )

    intent = FinancialQueryIntent.from_extraction(extraction)
    logger.info(
        "financial_query params company={} year={} metric={}",
        intent.company,
        intent.year,
        intent.metric,
    )
    if intent.ambiguity:
        logger.info("financial_query ambiguity={}", intent.ambiguity)

    return {
        "financial_query_text": query,
        "financial_query_intent": intent,
        "steps": ["financial_query_extract"],
    }
