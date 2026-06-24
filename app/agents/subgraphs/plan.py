"""Plan 子图节点：RAG 路由 → 决定 faq / pdf / future_db（Week 4）。"""

from __future__ import annotations

from typing import cast

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.prompts.plan import PLAN_SUPERVISOR_PROMPT
from app.agents.states import FinAgentState, PlanRouter
from app.core.logger import get_logger

logger = get_logger(service="plan_agent")


async def plan_agent(
    state: FinAgentState,
    config: RunnableConfig | None = None,
) -> dict:
    """RAG 子路由：Supervisor 判为 plan 后，由本节点决定走 faq 还是 pdf。"""
    model = get_router_llm()
    history = list(state.get("messages") or [])
    messages = [SystemMessage(content=PLAN_SUPERVISOR_PROMPT), *history]

    logger.info("----- Plan Agent: route_rag -----")
    logger.info("history_messages={}", len(history))

    router = cast(
        PlanRouter,
        await model.with_structured_output(
            PlanRouter, method="json_mode"
        ).ainvoke(messages, config=config),
    )
    logger.info("plan_route={} logic={}", router.type, router.logic)

    return {
        "route": router.type,
        "logic": router.logic,
    }
