"""finance_agent fan-in / join 测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END

from app.agents.components.finance_agent.join import fan_in_ready, sub_task_satisfied
from app.agents.components.finance_agent.join.node import route_after_join
from app.agents.states import FinAgentState, PlannerOutput, SubTask


def test_sub_task_satisfied_waits_for_web_fallback():
    assert not sub_task_satisfied(
        "t1",
        [{"sub_task_id": "t1", "type": "faq", "fallback_to_web": True}],
    )
    assert sub_task_satisfied(
        "t1",
        [
            {"sub_task_id": "t1", "type": "faq", "fallback_to_web": True},
            {"sub_task_id": "t1", "type": "web_search"},
        ],
    )


def test_fan_in_ready_requires_all_sub_tasks():
    tasks = [
        SubTask(id="a", question="q1", type="faq"),
        SubTask(id="b", question="q2", type="web_search"),
    ]
    assert not fan_in_ready(
        sub_tasks=tasks,
        task_results=[{"sub_task_id": "b", "type": "web_search"}],
    )
    assert fan_in_ready(
        sub_tasks=tasks,
        task_results=[
            {"sub_task_id": "a", "type": "faq"},
            {"sub_task_id": "b", "type": "web_search"},
        ],
    )


def test_route_after_join_waits_until_all_sub_tasks_ready():
    tasks = [
        SubTask(id="a", question="q1", type="faq"),
        SubTask(id="b", question="q2", type="web_search"),
    ]
    waiting: FinAgentState = {
        "sub_tasks": tasks,
        "task_results": [{"sub_task_id": "b", "type": "web_search"}],
    }
    ready: FinAgentState = {
        "sub_tasks": tasks,
        "task_results": [
            {"sub_task_id": "a", "type": "faq"},
            {"sub_task_id": "b", "type": "web_search"},
        ],
    }
    assert route_after_join(waiting) == END
    assert route_after_join(ready) == "summarize"


@pytest.mark.asyncio
async def test_join_barrier_summarize_runs_once_for_asymmetric_branches():
    """faq→web 比直达 web 更长时，join 先挡短路径，summarize 只跑一次。"""
    from app.agents.components.finance_agent.graph import build_finance_agent_subgraph

    mock_output = PlannerOutput(
        tasks=[
            SubTask(id="f1", question="交易规则是什么", type="faq"),
            SubTask(id="w1", question="最近有什么新规", type="web_search"),
        ]
    )
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=mock_output)
    mock_llm.with_structured_output.return_value = mock_structured

    join_calls = 0
    summarize_calls = 0

    async def mock_faq(state, config=None):
        await asyncio.sleep(0.05)
        return {
            "task_results": [
                {
                    "sub_task_id": state.get("sub_task_id", ""),
                    "question": state.get("sub_question", ""),
                    "type": "faq",
                    "context": "（未找到相关知识库条目）",
                    "fallback_to_web": True,
                    "fallback_reason": "faq_no_context",
                }
            ],
        }

    async def mock_web(state, config=None):
        question = str(state.get("sub_question") or "")
        label = "fallback" if "交易规则" in question else "planned"
        return {
            "task_results": [
                {
                    "sub_task_id": state.get("sub_task_id", ""),
                    "question": question,
                    "type": "web_search",
                    "context": f"web-{label}",
                }
            ],
        }

    async def mock_join(state, config=None):
        nonlocal join_calls
        join_calls += 1
        return {"steps": ["join"]}

    async def mock_summarize(state, config=None):
        nonlocal summarize_calls
        summarize_calls += 1
        contexts = [
            str(r.get("context") or "")
            for r in (state.get("task_results") or [])
            if r.get("type") == "web_search" and not r.get("fallback_to_web")
        ]
        return {"summary": "|".join(sorted(contexts))}

    with (
        patch(
            "app.agents.components.finance_agent.planner.node.get_router_llm",
            return_value=mock_llm,
        ),
        patch(
            "app.agents.components.finance_agent.graph.faq_agent",
            mock_faq,
        ),
        patch(
            "app.agents.components.finance_agent.graph.web_search_agent",
            mock_web,
        ),
        patch(
            "app.agents.components.finance_agent.graph.join_node",
            mock_join,
        ),
        patch(
            "app.agents.components.finance_agent.graph.summarize_node",
            mock_summarize,
        ),
    ):
        graph = build_finance_agent_subgraph().compile()
        out = await graph.ainvoke(
            {"messages": [HumanMessage(content="规则和新规")]}
        )

    assert join_calls == 2
    assert summarize_calls == 1
    assert set(out["summary"].split("|")) == {"web-fallback", "web-planned"}
