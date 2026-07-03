"""Components 聚合导出 — Layer 1: 主图节点 + 整个 Finance Agent。

⚠️ 所有 import 是惰性的（通过 __getattr__），避免 state_mixins.py 等
   模块在导入时触发 components/__init__.py → guardrails/node.py → states.py 循环。
"""

import importlib

_COMPONENT_MAP = {
    "guardrails_node": "app.agents.components.guardrails",
    "guardrails_edge": "app.agents.components.guardrails",
    "compress_context": "app.agents.components.context_compressor",
    "analyze_and_route_query": "app.agents.components.supervisor",
    "route_query": "app.agents.components.supervisor",
    "risk_triage_node": "app.agents.components.risk_triage",
    "risk_triage_edge": "app.agents.components.risk_triage",
    "general_agent": "app.agents.components.general_agent",
    "final_answer_node": "app.agents.components.final_answer",
}


def __getattr__(name):
    if name in _COMPONENT_MAP:
        mod = importlib.import_module(_COMPONENT_MAP[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "guardrails_node", "guardrails_edge",
    "compress_context",
    "analyze_and_route_query", "route_query",
    "risk_triage_node", "risk_triage_edge",
    "general_agent",
    "final_answer_node",
]
