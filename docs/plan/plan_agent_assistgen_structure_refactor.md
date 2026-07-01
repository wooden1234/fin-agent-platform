# 按 AssistGen 结构重构 Main Graph 与 PlanAgent

## Summary

将 `fin-agent-platform` 的主图和 `plan_agent` 改成类似 `agentic_rag_agents` 的分层结构：`components` 放节点，`edges` 放条件路由，`workflow` 负责编图。PlanAgent 内部改为 `planner -> tool_selection -> worker agents -> summarize`，不再由 planner 直接决定最终 worker。

保持现有外部 API 兼容：`app.agents.graph.build_graph/get_graph`、`app.agents.subgraphs.plan_agent.plan_agent` 继续可用，上层调用不需要改。

## Key Changes

- 主图结构整理为 workflow 风格：
  - 新增 `app/agents/workflows/main.py` 和 `app/agents/workflows/edges.py`
  - `app/agents/graph.py` 保留为兼容门面，继续导出 `build_graph`、`compile_graph`、`get_graph`
  - 现有 `guardrails`、`context_compressor`、`supervisor`、`risk_triage`、`final_answer` 行为不变，只调整组织方式

- PlanAgent 从单文件改为包：
  - 将 `app/agents/subgraphs/plan_agent.py` 迁移为 `app/agents/subgraphs/plan_agent/`
  - 包内包含 `workflow.py`、`edges.py`、`components/planner.py`、`components/tool_selection.py`、`components/summarize.py`
  - `__init__.py` 继续导出 `plan_agent`，兼容现有 import

- PlanAgent 新流程：
  - `planner` 只负责把用户问题拆成子任务，不再作为最终路由权威
  - `tool_selection` 对每个子任务单独选择 `faq`、`pdf`、`financial_query` 或 `general`
  - worker 执行后写入统一 `task_results`
  - `summarize` 汇总所有 worker 结果生成 `summary`

- 状态与模型：
  - 保留 `SubTask.type` 以兼容旧代码，但 PlanAgent 内部以 `tool_selection` 的输出为准
  - 新增 `PlanToolSelection`：包含 `tool`、`reason`、`confidence`
  - `TaskResult` 增加可选字段 `selected_tool`、`tool_reason`，用于调试和汇总
  - Planner 若输出空任务，自动补一个原问题 task，避免旧逻辑回退固定 `faq`

## Implementation Details

- `tool_selection` 使用 `get_router_llm().with_structured_output(...)` 输出结构化工具选择，不使用 AssistGen 的 Cypher 工具绑定代码。
- worker 路由使用 LangGraph `Command(goto=Send(...))` 风格，贴近 AssistGen 的 `tool_selection -> tool node` 结构。
- `general` 子任务需要新增轻量 wrapper，使它像 `faq/pdf/financial_query` 一样写入 `task_results`，否则 summarize 无法统一处理。
- 不复制 AssistGen 的 KG、Cypher、Neo4j、visualization、history 相关模块；只迁移它的组织方式和 planner/tool-selection/workflow 模式。
- `financial_query` 子图保持现有新结构，不在本轮继续改内部 SQL 模板逻辑。

## Test Plan

- 更新主图结构测试：
  - `get_graph(with_checkpointer=False)` 可编译
  - `app.agents.graph` 兼容导出仍可用
  - 主图仍保持 `guardrails -> context_compressor -> supervisor -> risk_triage -> plan_agent/general -> final_answer`

- 新增 PlanAgent 测试：
  - planner 输出多个任务时，每个任务都会进入 `tool_selection`
  - planner 输出空任务时，自动创建一个原问题任务
  - `tool_selection` 分别路由到 `faq`、`pdf`、`financial_query`、`general`
  - 多 worker 结果能通过 reducer 汇总到 `task_results`
  - `summarize` 对单结果直接返回，对多结果调用汇总逻辑

- 回归测试：
  - `tests/test_graph.py`
  - `tests/test_financial_query_agent.py`
  - 新增 `tests/test_plan_agent_workflow.py`
  - 新增 `tests/test_plan_tool_selection.py`

## Assumptions

- “连主图一起改”解释为主图也按 `workflow/edges/components` 风格整理，但不把主图的 guardrails/final_answer 复制进 PlanAgent。
- Planner 仍使用现有 `PLANNER_SYSTEM_PROMPT`，但会调整 prompt，让它更偏“拆任务”，工具选择交给新 `tool_selection` prompt。
- 本轮不引入 AssistGen 的 `history`、`visualization`、`validate_final_answer`，避免扩大行为面。
- 本轮不改变外部 API、SSE 输出结构、`FinAgentState.messages` 和 `citations` 的主流程语义。
