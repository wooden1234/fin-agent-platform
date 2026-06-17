"""Checkpoint 与多轮 state 单元/集成测试。"""

import uuid
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.checkpoint import (
    close_checkpoint,
    init_checkpoint,
    make_thread_config,
    normalize_checkpoint_dsn,
)
from app.agents.graph import get_graph, get_graph_with_memory, reset_graph_cache


def test_normalize_checkpoint_dsn():
    assert (
        normalize_checkpoint_dsn("postgresql+asyncpg://fin:fin@localhost:5432/fin_agent")
        == "postgresql://fin:fin@localhost:5432/fin_agent"
    )


def test_make_thread_config_uses_string_conversation_id():
    cfg = make_thread_config(42)
    assert cfg["configurable"]["thread_id"] == "42"


@pytest.mark.asyncio
async def test_multiturn_messages_accumulate_memory_backend():
    """不调 LLM：mock 节点验证同 thread_id 下 messages 累加。"""
    await close_checkpoint()
    reset_graph_cache()

    async def mock_supervisor(state, config):
        history = list(state.get("messages") or [])
        return {"route": "faq", "logic": f"n={len(history)}", "risk_level": "L1"}

    async def mock_faq(state, config):
        n = len(state.get("messages") or [])
        return {"messages": [AIMessage(content=f"seen={n}")], "citations": []}

    with (
        patch("app.agents.graph.analyze_and_route_query", mock_supervisor),
        patch("app.agents.graph.faq_agent", mock_faq),
    ):
        await init_checkpoint(backend="memory")
        graph = get_graph()
        thread = f"mem-{uuid.uuid4()}"
        config = make_thread_config(thread)

        r1 = await graph.ainvoke({"messages": [HumanMessage(content="q1")]}, config=config)
        r2 = await graph.ainvoke({"messages": [HumanMessage(content="q2")]}, config=config)

    assert len(r1["messages"]) == 2
    assert r1["messages"][-1].content == "seen=1"
    assert len(r2["messages"]) == 4
    assert r2["messages"][-1].content == "seen=3"
    await close_checkpoint()


@pytest.mark.asyncio
async def test_postgres_checkpointer_init():
    """集成：PostgresSaver.setup 可连上本地库。"""
    await close_checkpoint()
    reset_graph_cache()
    saver = await init_checkpoint(backend="postgres")
    assert saver is not None
    graph = get_graph()
    assert graph is not None
    await close_checkpoint()


@pytest.mark.asyncio
async def test_multiturn_messages_accumulate_postgres_backend():
    """集成：Postgres 持久化下同 thread 续聊（mock LLM）。"""
    await close_checkpoint()
    reset_graph_cache()

    async def mock_supervisor(state, config):
        return {"route": "faq", "logic": "ok", "risk_level": "L1"}

    async def mock_faq(state, config):
        n = len(state.get("messages") or [])
        return {"messages": [AIMessage(content=f"pg-seen={n}")], "citations": []}

    with (
        patch("app.agents.graph.analyze_and_route_query", mock_supervisor),
        patch("app.agents.graph.faq_agent", mock_faq),
    ):
        await init_checkpoint(backend="postgres")
        graph = get_graph()
        thread = f"pg-{uuid.uuid4()}"
        config = make_thread_config(thread)

        r1 = await graph.ainvoke({"messages": [HumanMessage(content="a")]}, config=config)
        r2 = await graph.ainvoke({"messages": [HumanMessage(content="b")]}, config=config)

    assert len(r1["messages"]) == 2
    assert len(r2["messages"]) == 4
    assert r2["messages"][-1].content == "pg-seen=3"
    await close_checkpoint()
