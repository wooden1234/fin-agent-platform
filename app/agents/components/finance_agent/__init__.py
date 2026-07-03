"""finance_agent：编译后的 RAG Agent 子图。

Layer 1+2: 作为 components/ 下的一个编译子图节点被主图引用。
内部使用 Supervisor 框架进行 LLM 动态路由。

⚠️ 惰性加载：避免 state_mixins.py 导入本包下的 state.py 时
   触发 graph.py → states.py 循环。
"""

import importlib


def __getattr__(name):
    if name == "finance_agent":
        mod = importlib.import_module(
            "app.agents.components.finance_agent.graph"
        )
        return mod.build_finance_agent_subgraph().compile()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["finance_agent"]
