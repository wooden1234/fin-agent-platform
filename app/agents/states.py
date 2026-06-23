"""LangGraph 状态与 Supervisor 路由模型（Week 3）。"""

from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

# ---------- 与前端 / SSE 对齐 ----------
AgentRoute = Literal["faq", "pdf", "account", "general"]
# 风险等级：L1 普通 FAQ；L2 账户查询；L3 投诉敏感；L4 挂失大额等需人工
RiskLevel = Literal["L1", "L2", "L3", "L4"]


class Citation(TypedDict, total=False):
    """检索引用；FAQ 节点写入，SSE done 带回前端。"""
    source: str
    snippet: str
    page: int


# ---------- Supervisor 结构化输出（with_structured_output）----------
class Router(BaseModel):
    """Supervisor 对用户问题的分类结果。"""

    type: AgentRoute = Field(
        description="业务路由：faq=知识库问答；account=账户类；general=闲聊/泛化"
    )
    logic: str = Field(
        description="一两句话说明为何选该路由"
    )
    risk_level: RiskLevel = Field(
        default="L1",
        description="L1 普通 FAQ；L2 账户查询；L3 投诉敏感；L4 挂失大额等需人工",
    )


# ---------- 图状态 ----------
class FinAgentState(TypedDict):
    """主图状态。W3 仅 faq 链路；W4 扩展 account/general。"""

    # 唯一带 reducer 的字段：新消息追加，同 id 可覆盖
    messages: Annotated[list[AnyMessage], add_messages]

    # Supervisor 写入；无 reducer → 节点返回值整体覆盖
    route: NotRequired[AgentRoute]
    logic: NotRequired[str]
    risk_level: NotRequired[RiskLevel]

    # FAQ 节点写入；检索完成后填充
    citations: NotRequired[list[Citation]]


# 可选：入口更窄，只暴露 messages（compile 时 input=FinAgentInput）
class FinAgentInput(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
