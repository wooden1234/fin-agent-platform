"""主图编译：START → Supervisor → [general_agent | plan_agent → [faq_agent | pdf_agent]] → END。"""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.states import FinAgentInput, FinAgentState
from app.agents.subgraphs.faq import faq_agent
from app.agents.subgraphs.general import general_agent
from app.agents.subgraphs.pdf import pdf_agent
from app.agents.subgraphs.plan import plan_agent
from app.agents.supervisor import analyze_and_route_query, route_query

_compiled_graph = None

_PlanTarget = Literal["faq_agent", "pdf_agent", "__end__"]


def _route_from_plan(state: FinAgentState) -> _PlanTarget:
    """Plan Agent 之后的子路由：faq → faq_agent；pdf → pdf_agent。"""
    route = state.get("route", "faq")
    if route == "faq":
        return "faq_agent"
    if route == "pdf":
        return "pdf_agent"
    return "__end__"


def build_graph() -> StateGraph:
    """构建未编译的 StateGraph（便于单测与 export）。"""
    builder = StateGraph(FinAgentState, input_schema=FinAgentInput)

    builder.add_node("supervisor", analyze_and_route_query)
    builder.add_node("general_agent", general_agent)
    builder.add_node("plan_agent", plan_agent)
    builder.add_node("faq_agent", faq_agent)
    builder.add_node("pdf_agent", pdf_agent)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_query,
        {
            "general_agent": "general_agent",
            "plan_agent": "plan_agent",
            "__end__": END,
        },
    )
    builder.add_conditional_edges(
        "plan_agent",
        _route_from_plan,
        {
            "faq_agent": "faq_agent",
            "pdf_agent": "pdf_agent",
            "__end__": END,
        },
    )
    builder.add_edge("general_agent", END)
    builder.add_edge("faq_agent", END)
    builder.add_edge("pdf_agent", END)

    return builder


def compile_graph(checkpointer: BaseCheckpointSaver | None):
    return build_graph().compile(checkpointer=checkpointer)


def reset_graph_cache() -> None:
    global _compiled_graph
    _compiled_graph = None


def get_graph(*, with_checkpointer: bool = True):
    """返回编译后的主图。

    - ``with_checkpointer=False``：无持久化（export / 结构单测）
    - ``with_checkpointer=True``：使用 ``init_checkpoint()`` 后的 saver（Postgres 或 Memory）
    """
    global _compiled_graph

    if not with_checkpointer:
        return compile_graph(None)

    if _compiled_graph is None:
        from app.agents.checkpoint import get_checkpointer

        _compiled_graph = compile_graph(get_checkpointer())
    return _compiled_graph


def get_graph_with_memory():
    """测试辅助：独立 MemorySaver，不依赖全局 init。"""
    return compile_graph(MemorySaver())
