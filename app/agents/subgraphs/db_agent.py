"""DB Agent 子图节点：结构化财务事实查询（annual_financial_facts）。"""

from __future__ import annotations

from typing import cast

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState
from app.agents.subgraphs.prompts.db_agent import (
    DB_AGENT_EXTRACT_PROMPT,
    DB_NO_RESULT_ANSWER,
)
from app.core.logger import get_logger
from app.services.financial_fact_service import (
    FinancialFactQuery, 
    FinancialFactService,
)

logger = get_logger(service="db_agent")


def _latest_user_query(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    raise ValueError("无用户消息")


async def _extract_query_params(
    question: str,
    config: RunnableConfig | None,
) -> FinancialFactQuery:
    llm = get_router_llm()
    return cast(
        FinancialFactQuery,
        await llm.with_structured_output(
            FinancialFactQuery, method="json_mode"
        ).ainvoke(
            [
                ("system", DB_AGENT_EXTRACT_PROMPT),
                ("human", f"用户问题：{question}"),
            ],
            config=config,
        ),
    )


async def db_agent(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    sub_question = state.get("sub_question", "")
    sub_task_id = state.get("sub_task_id", "")

    if sub_question:
        query = sub_question
    else:
        query = _latest_user_query(list(state.get("messages") or []))

    logger.info("db_agent query={} sub_task_id={}", query[:80], sub_task_id)

    try:
        params = await _extract_query_params(query, config)
    except Exception:
        logger.exception("db_agent param extraction failed")
        params = FinancialFactQuery(
            companies=[query],
            years=[],
            metrics=[],
            operation="lookup",
        )

    logger.info(
        "db_agent params company={} year={} metric={}",
        params.company,
        params.year,
        params.metric,
    )

    try:
        facts, template_name = await FinancialFactService.execute_query(query, params)
    except Exception:
        logger.exception("db_agent database query failed")
        return {
            "messages": [AIMessage(content=DB_NO_RESULT_ANSWER)],
            "citations": [],
            "task_results": [
                {
                    "sub_task_id": sub_task_id,
                    "question": query,
                    "type": "db",
                    "context": "（数据库查询失败）",
                }
            ],
            "steps": ["db_agent_error"],
        }
    logger.info("db_agent template={}", template_name)

    if not facts:
        logger.warning("db_agent no facts for company={} year={}", params.company, params.year)
        return {
            "messages": [AIMessage(content=DB_NO_RESULT_ANSWER)],
            "citations": [],
            "task_results": [
                {
                    "sub_task_id": sub_task_id,
                    "question": query,
                    "type": "db",
                    "context": DB_NO_RESULT_ANSWER,
                }
            ],
            "steps": ["db_agent_miss", template_name],
        }

    answer = FinancialFactService.format_answer(facts)
    citations = FinancialFactService.to_citations(facts)

    logger.info("db_agent hits={}", len(facts))
    return {
        "messages": [AIMessage(content=answer)],
        "citations": citations,
        "task_results": [
            {
                "sub_task_id": sub_task_id,
                "question": query,
                "type": "db",
                "context": answer,
            }
        ],
        "steps": ["db_agent", template_name],
    }
