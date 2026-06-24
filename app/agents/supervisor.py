"""Supervisor：意图分类 + 风险分级（Week 3 Day 2）。"""

from __future__ import annotations

from typing import Literal, cast

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from app.agents.states import FinAgentState, Router
from app.core.logger import get_logger

logger = get_logger(service="supervisor")

# 顶层路由：Supervisor 输出 general / plan，分别走 general_agent / plan_agent
RouteTarget = Literal["general_agent", "plan_agent", "__end__"]


async def analyze_and_route_query(
    state: FinAgentState,
    config: RunnableConfig,
) -> dict[str, str]:
    """分析用户问题，写入 route / logic / risk_level。

    使用 ``with_structured_output(Router)`` 约束 LLM 输出。
    """
    model = get_router_llm()
    history = list(state.get("messages") or [])
    messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT), *history]

    logger.info("----- Supervisor: analyze_and_route_query -----")
    logger.info("history_messages={}", len(history))

    router = cast(
       Router,
       await model.with_structured_output(
            Router, method="json_mode"
        ).ainvoke(messages, config=config),
    )
    logger.info(
        "route={} risk_level={} logic={}",
        router.type,
        router.risk_level,
        router.logic,
    )

    return {
        "route": router.type,
        "logic": router.logic,
        "risk_level": router.risk_level,
    }


def route_query(state: FinAgentState) -> RouteTarget:
    """条件边：根据 Supervisor 的 route 选择下一节点。

    ``general`` → ``general_agent``；``plan`` → ``plan_agent``；其余 → ``__end__``。
    """
    route = state.get("route", "general")
    logger.info("route_query: route={}", route)

    if route == "general":
        return "general_agent"
    if route == "plan":
        return "plan_agent"

    logger.warning("未知 route={}，结束图执行", route)
    return "__end__"
