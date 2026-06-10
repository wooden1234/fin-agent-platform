"""主图结构单元测试（不调用 LLM）。"""

from langgraph.graph import END

from app.agents.graph import build_graph, get_graph


def test_graph_compiles_and_has_expected_nodes():
    graph = get_graph(with_checkpointer=False)
    nodes = set(graph.get_graph().nodes.keys())
    assert "supervisor" in nodes
    assert "faq_agent" in nodes
    assert "__start__" in nodes
    assert "__end__" in nodes


def test_conditional_edges_from_supervisor():
    builder = build_graph()
    # 未编译图也能检查边配置
    compiled = builder.compile()
    edges = compiled.get_graph().edges
    supervisor_edges = [e for e in edges if e[0] == "supervisor"]
    targets = {e[1] for e in supervisor_edges}
    assert "faq_agent" in targets
    assert END in targets or "__end__" in targets
