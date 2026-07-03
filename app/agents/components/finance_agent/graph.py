"""finance_agent 子图构建：supervisor → workers → summarize。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from app.agents.states import FinAgentState
from app.agents.components.finance_agent.planner import route_after_supervisor, supervisor_node
from app.agents.components.finance_agent.faq_agent import faq_agent
from app.agents.components.finance_agent.pdf_agent import pdf_agent
from app.agents.components.finance_agent.financial_query_agent import financial_query_agent
from app.agents.components.finance_agent.summarize import summarize_node


def build_finance_agent_subgraph() -> StateGraph:
    """构建 finance_agent 子图：supervisor → workers → summarize"""
    builder = StateGraph(FinAgentState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("faq_agent", faq_agent)
    builder.add_node("pdf_agent", pdf_agent)
    builder.add_node("financial_query_agent", financial_query_agent)
    builder.add_node("summarize", summarize_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    builder.add_edge("faq_agent", "summarize")
    builder.add_edge("pdf_agent", "summarize")
    builder.add_edge("financial_query_agent", "summarize")
    builder.add_edge("summarize", END)

    return builder


__all__ = ["build_finance_agent_subgraph"]
