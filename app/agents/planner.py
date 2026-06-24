"""Planner 节点：多意图拆分"""

from __future__ import annotations

from typing import cast
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_router_llm
from app.agents.subgraphs.prompts.planner import PLANNER_SYSTEM_PROMPT
from app.agents.states import FinAgentState, PlannerOutput, SubTask
from app.core.logger import get_logger

logger = get_logger(service="planner")


def _latest_user_query(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


async def planner_node(
    state: FinAgentState,
    config: RunnableConfig | None = None,
) -> dict:
    """将用户问题分解为独立子任务列表。

    简单问题 → sub_tasks=[] → fanout 回退到单路路由
    复合问题 → sub_tasks=[...] → fanout 并行分发
    """
    query = _latest_user_query(list(state.get("messages") or []))
    if not query:
        return {"sub_tasks": [], "steps": ["planner_skip"]}

    logger.info("planner query={}", query[:120])

    llm = get_router_llm()
    try:
        output = cast(
            PlannerOutput,
            await llm.with_structured_output(
                PlannerOutput, method="json_mode"
            ).ainvoke(
                [
                    ("system", PLANNER_SYSTEM_PROMPT),
                    ("human", f"用户问题：{query}"),
                ],
                config=config,
            ),
        )
        # 给每个子任务生成唯一 ID
        for task in output.tasks:
            if not task.id:
                task.id = uuid.uuid4().hex[:8]

        logger.info("planner tasks=%d types=%s",
                     len(output.tasks),
                     [t.type for t in output.tasks])
        return {
            "sub_tasks": output.tasks,
            "steps": ["planner"],
        }
    except Exception:
        logger.exception("planner failed, fallback to single task")
        return {"sub_tasks": [], "steps": ["planner_fallback"]}