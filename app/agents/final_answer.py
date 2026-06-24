"""FinalAnswer 节点：统一格式化最终输出"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.states import FinAgentState
from app.core.logger import get_logger

logger = get_logger(service="final_answer")


async def final_answer_node(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    """统一格式化最终回答，附加引用来源"""

    # 护栏拦截的委婉回复
    if state.get("guardrails_pass") is False:
        reason = state.get("guardrails_reason", "输入超出业务范围")
        answer = f"抱歉，{reason}。我只能回答金融相关的问题，请重新提问。"
        return {
            "messages": [AIMessage(content=answer)],
        }

    # L4 风险（risk_triage 已拦截，此处兜底）
    if state.get("risk_needs_human", False):
        answer = "您的问题已转人工处理，请稍候。"
        return {
            "messages": [AIMessage(content=answer)],
        }

    route = state.get("route", "general")
    answer = ""

    if route == "general":
        # general 答案已由 general_agent 写入 messages，直接取最后一条 AIMessage
        for msg in reversed(list(state.get("messages") or [])):
            if isinstance(msg, AIMessage):
                answer = (
                    msg.content
                    if isinstance(msg.content, str)
                    else str(msg.content)
                )
                break
    else:
        # plan 答案来自 summarize → summary
        answer = state.get("summary", "")
        if not answer:
            for msg in reversed(list(state.get("messages") or [])):
                if isinstance(msg, AIMessage):
                    answer = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    break

    if not answer:
        answer = "抱歉，我暂时无法回答您的问题，请稍后重试。"

    citations = list(state.get("citations") or [])

    # 去重：并行分支可能返回相同引用
    seen = set()
    deduped: list[dict] = []
    for c in citations:
        key = (c.get("source", ""), c.get("page"))
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    logger.info(
        "final_answer route={} len={} citations={} deduped={}",
        route,
        len(answer),
        len(citations),
        len(deduped),
    )

    return {
        "messages": [AIMessage(content=answer)],
        "citations": deduped,
        "summary": "",
    }
