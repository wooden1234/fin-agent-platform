"""finance_agent Supervisor 节点：LLM 动态路由。

接收 planner 输出的 sub_tasks，用 LLM 分析语义，决定路由到哪个 worker。
"""

from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Send
from pydantic import BaseModel, Field

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState, SubTask
from app.core.logger import get_logger

logger = get_logger(service="finance_agent_supervisor")


class PlanAgentRouting(BaseModel):
    """为单个 sub_task 的路由决策"""
    worker: str = Field(description="路由目标: faq / pdf / financial_query_agent")
    rewritten_question: str = Field(description="为 worker 改写后的子问题")
    confidence: float = Field(ge=0, le=1, description="路由置信度")
    reason: str = Field(description="路由理由")


WORKER_REGISTRY = {
    "faq": "faq_agent",
    "pdf": "pdf_agent",
    "financial_query_agent": "financial_query_agent",
}

SUPERVISOR_PROMPT = """你是 finance_agent 的路由 Supervisor。

分析每个子任务，从以下 worker 中选择最合适的：
- faq：通用金融知识问答（交易规则、术语、常识）
- pdf：PDF 文档问答（年报解读、政策文件、引用出处）
- financial_query_agent：结构化财务数值查询（营收、利润、指标）

输出 JSON：
{"worker": "faq", "rewritten_question": "...", "confidence": 0.9, "reason": "..."}
"""


async def _route_single_task(
    task: SubTask,
    config: RunnableConfig,
) -> PlanAgentRouting:
    """用 LLM 分析单个 sub_task，决定路由目标。"""
    llm = get_router_llm()
    try:
        return cast(
            PlanAgentRouting,
            await llm.with_structured_output(
                PlanAgentRouting, method="json_mode"
            ).ainvoke(
                [
                    ("system", SUPERVISOR_PROMPT),
                    ("human", f"子任务问题：{task.question}"),
                ],
                config=config,
            ),
        )
    except Exception:
        logger.exception("supervisor routing failed, default to faq")
        return PlanAgentRouting(
            worker="faq",
            rewritten_question=task.question,
            confidence=0.5,
            reason="路由异常，默认走 faq",
        )


async def finance_agent_supervisor(
    state: FinAgentState,
    config: RunnableConfig,
) -> dict:
    """用 LLM 分析每个 sub_task，动态决定路由到哪个 worker。"""
    sub_tasks: list[SubTask] = list(state.get("sub_tasks") or [])
    routes = []

    for task in sub_tasks:
        routing = await _route_single_task(task, config)
        worker_name = WORKER_REGISTRY.get(routing.worker, "faq_agent")
        routes.append({
            "worker": worker_name,
            "question": routing.rewritten_question,
            "sub_task_id": task.id or "",
            "confidence": routing.confidence,
        })

    return {"plan_agent_routes": routes}


def route_after_supervisor(state: FinAgentState) -> list[Send]:
    """条件边：Supervisor 输出 → 并行 Send 到各 Worker。"""
    routes = state.get("plan_agent_routes", [])
    if not routes:
        return [Send("faq_agent", {"sub_question": "请重新描述问题"})]

    return [
        Send(route["worker"], {
            "sub_question": route["question"],
            "sub_task_id": route["sub_task_id"],
        })
        for route in routes
    ]
