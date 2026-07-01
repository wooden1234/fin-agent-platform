"""finance_agent：编译后的 RAG Agent 子图。

Layer 1+2: 作为 components/ 下的一个编译子图节点被主图引用。
内部使用 Supervisor 框架进行 LLM 动态路由。
"""

from app.agents.components.finance_agent.graph import build_finance_agent_subgraph

# 编译后暴露为单个节点
finance_agent = build_finance_agent_subgraph().compile()

__all__ = ["finance_agent"]
