"""finance_agent 子图构建：planner → workers → join → summarize。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from app.agents.states import FinAgentState
from app.agents.components.finance_agent.planner import (
    route_after_retrieval_worker,
    route_after_supervisor,
    supervisor_node,
)
from app.agents.components.finance_agent.faq_agent import faq_agent
from app.agents.components.finance_agent.pdf_agent import pdf_agent
from app.agents.components.finance_agent.financial_query_agent import financial_query_agent
from app.agents.components.finance_agent.web_search_agent import web_search_agent
from app.agents.components.finance_agent.join import join_node, route_after_join
from app.agents.components.finance_agent.summarize import summarize_node
from app.agents.components.finance_agent.workers import isolate_worker_node


def build_finance_agent_subgraph() -> StateGraph:
    """构建 finance_agent 子图：planner → workers → join → summarize。"""
    builder = StateGraph(FinAgentState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("faq_agent", isolate_worker_node(faq_agent))
    builder.add_node("pdf_agent", isolate_worker_node(pdf_agent))
    builder.add_node(
        "financial_query_agent",
        isolate_worker_node(financial_query_agent),
    )
    builder.add_node("web_search_agent", isolate_worker_node(web_search_agent))
    builder.add_node("join", join_node)
    builder.add_node("summarize", summarize_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    builder.add_conditional_edges(
        "faq_agent",
        route_after_retrieval_worker,
        {
            "web_search_agent": "web_search_agent",
            "join": "join",
        },
    )
    builder.add_conditional_edges(
        "pdf_agent",
        route_after_retrieval_worker,
        {
            "web_search_agent": "web_search_agent",
            "join": "join",
        },
    )
    builder.add_edge("financial_query_agent", "join")
    builder.add_edge("web_search_agent", "join")
    builder.add_conditional_edges(
        "join",
        route_after_join,
        {
            "summarize": "summarize",
            END: END,
        },
    )
    builder.add_edge("summarize", END)

    return builder


__all__ = ["build_finance_agent_subgraph"]
