"""finance_agent 子图构建：planner → supervisor → [faq_agent | pdf_agent | financial_query_agent] → summarize。

使用 Supervisor 框架进行 LLM 动态路由，替代静态 _fanout_from_planner。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.states import FinAgentState
from app.agents.components.finance_agent.planner import planner_node
from app.agents.components.finance_agent.supervisor import finance_agent_supervisor, route_after_supervisor
from app.agents.components.finance_agent.faq_agent import faq_agent
from app.agents.components.finance_agent.pdf_agent import pdf_agent
from app.agents.components.finance_agent.financial_query_agent import financial_query_agent
from app.agents.components.finance_agent.summarize import summarize_node


def build_finance_agent_subgraph() -> StateGraph:
    """构建 finance_agent 子图：planner → supervisor → workers → summarize"""
    builder = StateGraph(FinAgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", finance_agent_supervisor)
    builder.add_node("faq_agent", faq_agent)
    builder.add_node("pdf_agent", pdf_agent)
    builder.add_node("financial_query_agent", financial_query_agent)
    builder.add_node("summarize", summarize_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    builder.add_edge("faq_agent", "summarize")
    builder.add_edge("pdf_agent", "summarize")
    builder.add_edge("financial_query_agent", "summarize")
    builder.add_edge("summarize", END)

    return builder


__all__ = ["build_finance_agent_subgraph"]
