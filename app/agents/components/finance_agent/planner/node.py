"""finance_agent 入口节点：拆分子任务并按类型派发。"""

from __future__ import annotations

import uuid
from typing import cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Overwrite, Send

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState, PlannerOutput, SubTask
from app.agents.components.finance_agent.planner.prompts import (
    PLANNER_REPAIR_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
)
from app.agents.components.finance_agent.planner.validate import (
    ALLOWED_TASK_TYPES,
    validate_and_normalize_tasks,
)
from app.core.logger import get_logger

logger = get_logger(service="finance_agent_supervisor")

TASK_TYPE_TO_WORKER = {
    "faq": "faq_agent",
    "pdf": "pdf_agent",
    "financial_query": "financial_query_agent",
    "web_search": "web_search_agent",
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


def _begin_turn_workspace() -> dict:
    """每轮用户提问开始时清空中间工作区（一问一答），避免 checkpoint 跨轮污染。"""
    return {
        "task_results": Overwrite([]),
        "citations": Overwrite([]),
        "summary": "",
    }


def _assign_task_ids(tasks: list[SubTask]) -> list[SubTask]:
    for task in tasks:
        task.id = uuid.uuid4().hex[:8]
    return tasks


def _empty_plan(*, step: str, reason: str) -> dict:
    logger.warning("planner empty_plan step={} reason={}", step, reason)
    return {
        **_begin_turn_workspace(),
        "sub_tasks": [],
        "steps": [f"{step}:{reason}"],
    }


def _is_transient_api_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    name = type(exc).__name__.lower()
    markers = (
        "timeout",
        "connection",
        "ratelimit",
        "rate_limit",
        "apiconnection",
        "internalserver",
        "serviceunavailable",
        "429",
        "502",
        "503",
    )
    return any(marker in name for marker in markers)


def _is_schema_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    markers = (
        "validation",
        "json",
        "parse",
        "outputparser",
        "structuredoutput",
        "pydantic",
        "badrequest",
    )
    return any(marker in name for marker in markers)


async def _ainvoke_planner(
    *,
    system_prompt: str,
    human_prompt: str,
    config: RunnableConfig | None,
) -> PlannerOutput:
    llm = get_router_llm()
    return cast(
        PlannerOutput,
        await llm.with_structured_output(
            PlannerOutput, method="json_mode"
        ).ainvoke(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ],
            config=config,
        ),
    )


async def _plan_with_retry(
    query: str,
    config: RunnableConfig | None,
) -> PlannerOutput:
    """API/超时类错误重试一次；仍失败则抛出。"""
    human = f"用户问题：{query}"
    try:
        return await _ainvoke_planner(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            human_prompt=human,
            config=config,
        )
    except Exception as exc:
        if not _is_transient_api_error(exc):
            raise
        logger.warning(
            "planner transient api error, retrying once: {}",
            type(exc).__name__,
        )
        return await _ainvoke_planner(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            human_prompt=human,
            config=config,
        )


async def _repair_plan(
    query: str,
    raw_tasks: list[SubTask],
    issues: list[str],
    config: RunnableConfig | None,
) -> PlannerOutput:
    payload = PlannerOutput(tasks=raw_tasks).model_dump_json()
    human = (
        f"用户问题：{query}\n"
        f"校验问题：{', '.join(issues)}\n"
        f"待修正输出：{payload}"
    )
    return await _ainvoke_planner(
        system_prompt=PLANNER_REPAIR_SYSTEM_PROMPT,
        human_prompt=human,
        config=config,
    )


async def supervisor_node(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    """将用户问题分解为独立子任务列表。"""
    query = _latest_user_query(list(state.get("messages") or []))
    if not query:
        return _empty_plan(step="supervisor_skip", reason="empty_query")

    logger.info("planner query={}", query[:120])

    try:
        output = await _plan_with_retry(query, config)
    except Exception as exc:
        if _is_transient_api_error(exc):
            logger.exception("planner api failed after retry")
            return _empty_plan(step="planner_fallback", reason="api_error")
        if _is_schema_error(exc):
            logger.warning(
                "planner schema/parse error, attempting repair: {}",
                type(exc).__name__,
            )
            try:
                output = await _repair_plan(query, [], [f"schema_error:{type(exc).__name__}"], config)
            except Exception:
                logger.exception("planner schema repair failed")
                return _empty_plan(step="planner_fallback", reason="schema_error")
        else:
            logger.exception("planner failed with unexpected error")
            return _empty_plan(step="planner_fallback", reason="unexpected_error")

    validation = validate_and_normalize_tasks(output.tasks)
    if validation.needs_repair:
        logger.warning(
            "planner validation issues={}, attempting repair",
            validation.issues,
        )
        try:
            repaired = await _repair_plan(query, output.tasks, validation.issues, config)
            validation = validate_and_normalize_tasks(repaired.tasks)
        except Exception:
            logger.exception("planner repair invoke failed")
            if not validation.tasks:
                return _empty_plan(step="planner_fallback", reason="repair_failed")

    tasks = _assign_task_ids(validation.tasks)
    if not tasks:
        # 业务上无法归类：空计划 → 下游澄清，不是系统故障
        reason = "unclassifiable" if not validation.issues else "invalid_after_validate"
        logger.info(
            "planner empty tasks reason={} issues={}",
            reason,
            validation.issues,
        )
        return _empty_plan(step="planner_clarification", reason=reason)

    logger.info(
        "planner tasks={} types={} issues={}",
        len(tasks),
        [t.type for t in tasks],
        validation.issues,
    )
    return {
        **_begin_turn_workspace(),
        "sub_tasks": tasks,
        "steps": ["supervisor"],
    }


def route_after_supervisor(state: FinAgentState) -> list[Send]:
    """根据 planner 产出的子任务类型直接派发到 worker。"""
    sub_tasks: list[SubTask] = list(state.get("sub_tasks") or [])
    if not sub_tasks:
        return [
            Send(
                "join",
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
        if worker is None or task.type not in ALLOWED_TASK_TYPES:
            logger.warning("planner unknown task type={} question={}", task.type, task.question)
            sends.append(
                Send(
                    "join",
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


def route_after_retrieval_worker(state: FinAgentState) -> str | Send:
    """根据检索结果决定是否进入联网搜索兜底。

    兜底必须用 ``Send`` 显式带上 ``sub_task_id`` / ``sub_question``：
    上游 ``Send`` 的字段只在 worker 执行期可见，普通边不会自动带到下一跳。
    """
    sub_task_id = str(state.get("sub_task_id") or "")
    sub_question = str(state.get("sub_question") or "")
    task_results = list(state.get("task_results") or [])

    for result in reversed(task_results):
        result_id = str(result.get("sub_task_id") or "")
        if sub_task_id and result_id != sub_task_id:
            continue
        if result.get("fallback_to_web"):
            return Send(
                "web_search_agent",
                {
                    "sub_task_id": result_id or sub_task_id,
                    "sub_question": sub_question or str(result.get("question") or ""),
                },
            )
        return "join"

    return "join"
