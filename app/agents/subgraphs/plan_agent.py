"""Plan Agent 子图：planner → fanout → [faq_agent | pdf_agent] → summarize → END。

作为独立 Agent 编译，主图只需 add_node("plan_agent", plan_agent)。
后续迁移到 Supervisor 框架时，整个子图作为单个 Agent 注册。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.states import FinAgentInput, FinAgentState, SubTask
from app.agents.subgraphs.faq import faq_agent
from app.agents.subgraphs.pdf import pdf_agent
from app.agents.subgraphs.planner import planner_node
from app.agents.subgraphs.summarize import summarize_node


def _latest_user_query_from_state(state: FinAgentState) -> str:
    from langchain_core.messages import HumanMessage

    for msg in reversed(list(state.get("messages") or [])):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _fanout_from_planner(state: FinAgentState) -> list[Send]:
    """Planner 后的并行分发边。

    - 每个 SubTask 一个 Send，LangGraph 自动并行
    - 空列表仅异常时出现，回退到 faq(默认)
    """
    sub_tasks: list[SubTask] = list(state.get("sub_tasks") or [])

    # 异常兜底：LLM 解析失败，回退到 faq
    if not sub_tasks:
        return [
            Send(
                "faq_agent",
                {
                    "sub_question": _latest_user_query_from_state(state),
                    "sub_task_id": "fallback",
                },
            )
        ]

    sends: list[Send] = []
    for task in sub_tasks:
        if task.type == "faq":
            sends.append(
                Send(
                    "faq_agent",
                    {"sub_question": task.question, "sub_task_id": task.id},
                )
            )
        elif task.type == "pdf":
            sends.append(
                Send(
                    "pdf_agent",
                    {"sub_question": task.question, "sub_task_id": task.id},
                )
            )
    return sends


def _build_plan_agent_subgraph() -> StateGraph:
    """构建 plan agent 子图：planner → fanout → [faq | pdf] → summarize → END"""
    builder = StateGraph(FinAgentState, input_schema=FinAgentInput)

    builder.add_node("planner", planner_node)
    builder.add_node("faq_agent", faq_agent)
    builder.add_node("pdf_agent", pdf_agent)
    builder.add_node("summarize", summarize_node)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", _fanout_from_planner)
    builder.add_edge("faq_agent", "summarize")
    builder.add_edge("pdf_agent", "summarize")
    builder.add_edge("summarize", END)

    return builder


# 编译后暴露为单个节点 —— 主图直接 add_node("plan_agent", plan_agent)
plan_agent = _build_plan_agent_subgraph().compile()
