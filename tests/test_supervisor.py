"""Supervisor 路由单元测试 + 可选 LLM 联调。"""

import pytest
from langchain_core.messages import HumanMessage

from app.agents.states import FinAgentState
from app.agents.components.supervisor import analyze_and_route_query, route_query
from tests.conftest import requires_llm_key


class TestRouteQuery:
    def test_faq_route(self):
        state: FinAgentState = {"messages": [], "route": "faq"}
        assert route_query(state) == "faq_agent"

    def test_pdf_route(self):
        state: FinAgentState = {"messages": [], "route": "pdf"}
        assert route_query(state) == "pdf_agent"

    def test_account_route_ends_in_w3(self):
        state: FinAgentState = {"messages": [], "route": "account"}
        assert route_query(state) == "__end__"

    def test_general_route_ends_in_w3(self):
        state: FinAgentState = {"messages": [], "route": "general"}
        assert route_query(state) == "__end__"

    def test_default_route_is_faq(self):
        state: FinAgentState = {"messages": []}
        assert route_query(state) == "faq_agent"


@requires_llm_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_analyze_and_route_faq_query():
    state: FinAgentState = {
        "messages": [HumanMessage(content="什么是 T+1 交易制度？")],
    }
    update = await analyze_and_route_query(state, {})
    assert update["route"] == "faq"
    assert update["risk_level"] in ("L1", "L2", "L3", "L4")
    assert update["logic"]


@requires_llm_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_analyze_and_route_general_query():
    state: FinAgentState = {
        "messages": [HumanMessage(content="今天北京天气怎么样？")],
    }
    update = await analyze_and_route_query(state, {})
    assert update["route"] in ("general", "faq", "pdf")
    assert update["logic"]
