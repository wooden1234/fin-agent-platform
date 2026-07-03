"""financial_query_agent：结构化财务事实查询子图。

作为 finance_agent 内部的一个独立子 Agent 图，可独立编译/测试/复用。

⚠️ 惰性加载：避免 state_mixins.py 导入本包下的 state.py 时
   触发本包的顶层 import → states.py 循环。
"""

from __future__ import annotations

import importlib

_BUILT = False
_financial_query_agent = None


def _build_subgraph() -> object:
    """惰性构建子图，在首次访问 financial_query_agent 时调用。"""
    from langgraph.graph import END, START, StateGraph

    from app.agents.states import FinAgentState
    from app.agents.components.finance_agent.financial_query_agent.common import query_from_state
    from app.agents.components.finance_agent.financial_query_agent.extract_intent import extract_intent
    from app.agents.components.finance_agent.financial_query_agent.template_sql import template_sql_agent
    from app.agents.components.finance_agent.financial_query_agent.text_to_sql import text_to_sql_agent
    from app.agents.components.finance_agent.financial_query_agent.clarification import clarification_agent

    def route_after_template_sql(state: dict) -> str:
        route_name = str(state.get("financial_query_route") or "done")
        if route_name == "clarify":
            return "clarify"
        if route_name == "sql":
            return "sql"
        return "end"

    builder = StateGraph(FinAgentState)
    builder.add_node("extract_intent", extract_intent)
    builder.add_node("template_sql_agent", template_sql_agent)
    builder.add_node("clarify", clarification_agent)
    builder.add_node("sql", text_to_sql_agent)
    builder.add_edge(START, "extract_intent")
    builder.add_edge("extract_intent", "template_sql_agent")
    builder.add_conditional_edges(
        "template_sql_agent",
        route_after_template_sql,
        {"clarify": "clarify", "sql": "sql", "end": END},
    )
    builder.add_edge("clarify", END)
    builder.add_edge("sql", END)

    return builder.compile()


def __getattr__(name):
    global _BUILT, _financial_query_agent

    if name == "financial_query_agent":
        if not _BUILT:
            _financial_query_agent = _build_subgraph()
            _BUILT = True
        return _financial_query_agent

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["financial_query_agent"]


__all__ = [
    "_extract_query_params",
    "clarification_agent",
    "extract_intent",
    "financial_query_agent",
    "route_after_template_sql",
    "template_sql_agent",
    "text_to_sql_agent",
]
