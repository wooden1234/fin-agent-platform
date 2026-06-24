"""Summarize 节点：跨源证据融合"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_faq_llm
from app.agents.states import FinAgentState, TaskResult
from app.agents.subgraphs.prompts.summarize import SUMMARIZE_SYSTEM_PROMPT
from app.core.logger import get_logger

logger = get_logger(service="summarize")


def _format_task_results(task_results: list[TaskResult]) -> str:
    parts = []
    for i, tr in enumerate(task_results, start=1):
        parts.append(f"### 子任务 {i}：{tr.get('question', '未知')}")
        parts.append(f"类型：{tr.get('type', 'faq')}")
        parts.append(f"结果：{tr.get('context', '无结果')}")
        parts.append("")
    return "\n".join(parts) if parts else "无检索结果"


async def summarize_node(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    """融合所有并行检索结果，生成统一回答"""
    task_results: list[TaskResult] = state.get("task_results", [])
    risk_level = state.get("risk_level", "L1")

    logger.info(
        "summarize task_results=%d risk_level=%s",
        len(task_results),
        risk_level,
    )

    if risk_level in ("L3", "L4"):
        return {
            "summary": "您的问题涉及敏感内容，建议联系人工客服获得进一步帮助。",
        }

    if not task_results:
        return {"summary": ""}

    if len(task_results) == 1:
        return {"summary": task_results[0].get("context", "")}

    formatted = _format_task_results(task_results)
    llm = get_faq_llm()
    try:
        parts: list[str] = []
        async for chunk in llm.astream(
            [
                ("system", SUMMARIZE_SYSTEM_PROMPT.format(risk_level=risk_level)),
                ("human", f"请综合以下检索结果生成答案：\n\n{formatted}"),
            ],
            config=config,
        ):
            if chunk.content:
                parts.append(
                    chunk.content
                    if isinstance(chunk.content, str)
                    else str(chunk.content)
                )
        summary = "".join(parts)
    except Exception:
        logger.exception("summarize llm invoke failed")
        summary = "抱歉，在汇总信息时出现错误，请稍后重试。"

    return {"summary": summary}
