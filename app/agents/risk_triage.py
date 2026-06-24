"""Risk Triage 节点：风险分级 + 处置（独立于分类）。"""

from __future__ import annotations

from typing import cast

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.agents.llm import get_router_llm
from app.agents.states import FinAgentState, RiskLevel
from app.core.logger import get_logger

logger = get_logger(service="risk_triage")


class RiskAssessment(BaseModel):
    """风险评估结果（独立模型，不污染 Router）"""
    risk_level: RiskLevel = Field(description="L1-L4 风险等级")
    reason: str = Field(description="判定理由，1-2 句中文")
    needs_human: bool = Field(default=False, description="是否需要转人工")


RISK_TRIAGE_PROMPT = """你是金融智能客服平台的风险评估 Agent。

仅评估风险等级，不要做分类，不要回答用户问题。

| 级别 | 场景 | 处置动作 |
|------|------|----------|
| L1 | 普通 FAQ、一般咨询 | 正常回答 |
| L2 | 账户查询、持仓盈亏 | 正常回答，附加风险提示 |
| L3 | 投诉、纠纷、敏感 | 温和回复，告知投诉渠道 |
| L4 | 挂失、大额、欺诈、紧急 | **立即转人工**，返回安抚话术 |

输出 JSON：
{"risk_level": "L1", "reason": "...", "needs_human": false}
"""


async def risk_triage_node(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    """独立的风险评估与处置节点"""
    history = list(state.get("messages") or [])
    if not history:
        return {"risk_level": "L1", "risk_needs_human": False}

    llm = get_router_llm()
    messages = [
        ("system", RISK_TRIAGE_PROMPT),
        *[("user" if isinstance(m, HumanMessage) else "assistant", 
           m.content if isinstance(m.content, str) else str(m.content)) 
          for m in history],
    ]

    try:
        assessment = cast(
            RiskAssessment,
            await llm.with_structured_output(
                RiskAssessment, method="json_mode"
            ).ainvoke(messages, config=config),
        )
    except Exception:
        logger.exception("risk assessment failed, default to L1")
        assessment = RiskAssessment(risk_level="L1", reason="评估失败，默认放行")

    logger.info("risk={} needs_human={}", assessment.risk_level, assessment.needs_human)

    # L4 立即拦截，生成安抚话术
    if assessment.needs_human or assessment.risk_level == "L4":
        response = (
            "您的问题已升级为紧急处理，建议立即联系我们的人工客服团队。"
            "客服热线：XXX-XXXX-XXXX（24 小时）。"
        )
        return {
            "risk_level": assessment.risk_level,
            "risk_reason": assessment.reason,
            "risk_needs_human": True,
            "messages": [AIMessage(content=response)],  # 直接回复，不走后续 Agent
        }

    return {
        "risk_level": assessment.risk_level,
        "risk_reason": assessment.reason,
        "risk_needs_human": False,
    }


def risk_triage_edge(state: FinAgentState) -> str:
    """条件边：L4 → END（已回复安抚话术），其他 → 继续"""
    if state.get("risk_needs_human", False):
        return "__end__"
    route = state.get("route", "plan")
    if route == "general":
        return "general_agent"
    return "plan_agent"