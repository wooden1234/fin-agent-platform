"""finance_agent 入口节点：拆分子任务并按类型派发。"""

from __future__ import annotations

from typing import cast
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState, PlannerOutput, SubTask
from app.agents.components.finance_agent.planner.prompts import PLANNER_SYSTEM_PROMPT
from app.core.logger import get_logger

logger = get_logger(service="finance_agent_supervisor")

TASK_TYPE_TO_WORKER = {
    "faq": "faq_agent",
    "pdf": "pdf_agent",
    "financial_query": "financial_query_agent",
}

CLARIFICATION_ANSWER = (
    "抱歉，我暂时无法判断这个问题需要查询哪类金融资料。"
    "请补充更明确的金融对象或查询目标，例如交易规则、产品费率、报告名称、公司、年份或财务指标。"
)


def _latest_user_query(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


async def supervisor_node(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    """将用户问题分解为独立子任务列表。"""
    query = _latest_user_query(list(state.get("messages") or []))
    if not query:
        return {"sub_tasks": [], "steps": ["supervisor_skip"]}

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
        for task in output.tasks:
            if not task.id:
                task.id = uuid.uuid4().hex[:8]

        logger.info(
            "planner tasks={} types={}",
            len(output.tasks),
            [t.type for t in output.tasks],
        )
        return {"sub_tasks": output.tasks, "steps": ["supervisor"]}
    except Exception:
        logger.exception("planner failed, fallback to single task")
        return {"sub_tasks": [], "steps": ["planner_fallback"]}


def route_after_supervisor(state: FinAgentState) -> list[Send]:
    """根据 planner 产出的子任务类型直接派发到 worker。"""
    sub_tasks: list[SubTask] = list(state.get("sub_tasks") or [])
    if not sub_tasks:
        return [
            Send(
                "summarize",
                {
                    "task_results": [
                        {
                            "sub_task_id": "",
                            "question": "",
                            "type": "planner_clarification",
                            "context": CLARIFICATION_ANSWER,
                        }
                    ]
                },
            )
        ]

    sends: list[Send] = []
    for task in sub_tasks:
        worker = TASK_TYPE_TO_WORKER.get(task.type)
        if worker is None:
            logger.warning("planner unknown task type={} question={}", task.type, task.question)
            sends.append(
                Send(
                    "summarize",
                    {
                        "task_results": [
                            {
                                "sub_task_id": task.id or "",
                                "question": task.question,
                                "type": str(task.type),
                                "context": CLARIFICATION_ANSWER,
                            }
                        ]
                    },
                )
            )
            continue

        sends.append(
            Send(
                worker,
                {
                    "sub_question": task.question,
                    "sub_task_id": task.id or "",
                },
            )
        )
    return sends


planner_node = supervisor_node
