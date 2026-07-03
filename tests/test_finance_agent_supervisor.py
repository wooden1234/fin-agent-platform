import pytest
from langgraph.types import Send

from app.agents.components.finance_agent.planner.node import route_after_supervisor, supervisor_node
from app.agents.states import SubTask


@pytest.mark.asyncio
async def test_finance_agent_supervisor_outputs_sub_tasks():
    out = await supervisor_node({"sub_tasks": []}, {})

    assert out["sub_tasks"] == []
    assert out["steps"] == ["supervisor_skip"]


def test_route_after_supervisor_routes_financial_query_without_llm():
    task = SubTask(id="t1", question="腾讯第三季度收入是", type="financial_query")
    out = route_after_supervisor({"sub_tasks": [task]})

    assert out == [
        Send(
            "financial_query_agent",
            {"sub_question": "腾讯第三季度收入是", "sub_task_id": "t1"},
        )
    ]


def test_route_after_supervisor_asks_clarification_when_no_subtasks():
    out = route_after_supervisor({})

    assert out[0].node == "summarize"
    assert out[0].arg["task_results"][0]["type"] == "planner_clarification"


def test_route_after_supervisor_asks_clarification_for_general_task():
    task = SubTask(id="t1", question="随便问问", type="general")
    out = route_after_supervisor({"sub_tasks": [task]})

    assert out[0].node == "summarize"
    assert out[0].arg["task_results"][0]["sub_task_id"] == "t1"
