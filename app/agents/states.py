"""LangGraph 状态与 Supervisor 路由模型（Week 3）。"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

# ---------- 与前端 / SSE 对齐 ----------
AgentRoute = Literal["faq", "pdf", "account", "general", "plan"]
RiskLevel = Literal["L1", "L2", "L3", "L4"]


class Citation(TypedDict, total=False):
    """检索引用；FAQ 节点写入，SSE done 带回前端。"""
    source: str
    snippet: str
    page: int


# ---------- Supervisor 结构化输出（with_structured_output）----------
class Router(BaseModel):
    """Supervisor 对用户问题的分类结果：general（闲聊）还是 plan（RAG）。"""

    type: Literal["general", "plan"] = Field(
        description="general=闲聊/泛化/回溯对话；plan=需要检索知识库或文档"
    )
    logic: str = Field(
        description="一两句话说明为何选该路由"
    )


# ---------- Planner 多意图拆分 ----------
SubTaskType = Literal["faq", "pdf", "general"]

class SubTask(BaseModel):
    """单个子任务 — Planner 分解产物"""
    id: str = Field(default="", description="子任务唯一标识，用于结果匹配")
    question: str = Field(description="独立的子问题，可直接检索")
    type: SubTaskType = Field(
        default="faq",
        description="faq=知识库 / pdf=文档库 / general=无需检索"
    )


class PlannerOutput(BaseModel):
    """Planner 的 LLM 结构化输出"""
    tasks: list[SubTask] = Field(
        default=[],
        description="子任务列表；简单问题返回空列表"
    )


class TaskResult(TypedDict, total=False):
    """单个子任务的 Worker 返回结果"""
    sub_task_id: str
    question: str
    type: SubTaskType
    context: str              # 检索到的上下文原文
    citations: list[Citation]  # 引用


# ---------- 增强后的 FinAgentState ----------
class FinAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

    # Supervisor（不变）
    route: NotRequired[AgentRoute]
    logic: NotRequired[str]

    # 风险（拆到 risk_triage）
    risk_level: NotRequired[RiskLevel]
    risk_reason: NotRequired[str]
    risk_needs_human: NotRequired[bool]

    # Guardrails
    guardrails_pass: NotRequired[bool]
    guardrails_reason: NotRequired[str]

    # Planner 多意图
    sub_tasks: NotRequired[list[SubTask]]                     # Planner → fanout 边读取

    # Worker 并行写入（add reducer 自动归并）
    task_results: NotRequired[Annotated[list[TaskResult], add]]  # 🆕
    citations: NotRequired[Annotated[list[Citation], add]]       # 🔧 从 NotRequired[list] 改为 add

    # Summarize
    summary: NotRequired[str]

    # 调试追踪
    steps: NotRequired[Annotated[list[str], add]]


# 可选：入口更窄，只暴露 messages（compile 时 input=FinAgentInput）
class FinAgentInput(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
