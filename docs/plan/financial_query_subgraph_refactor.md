# 完善 `financial_query` 子图结构计划

## Summary

将 `app/agents/subgraphs/financial_query.py` 从单个大节点改成领域子图，对齐 `docs/平台级Harness与工具边界设计.md` 中的边界：

- `plan_agent` 仍只看到一个 `financial_query` 节点。
- `financial_query` 内部拆成 selector、template、fuzzy、clarify、text-to-SQL fallback 等节点。
- 本轮不实现真正的 text-to-SQL 生成链路，只把现有 `TEXT_TO_SQL_FALLBACK_ROUTE` 收敛为独立占位节点，保持当前行为不变。

## Key Changes

- `financial_query_agent` 改为编译后的 LangGraph 子图，而不是一个大 async 函数。
- 子图内部节点固定为：

```text
START
  -> extract_intent
  -> financial_tool_selection
  -> template_fact_agent / fuzzy_fact_agent / clarification_agent / text_to_sql_agent
  -> END
```

- 使用 `StateGraph(FinAgentState)` 组装子图，`financial_tool_selection` 后通过 conditional edges 分发到四个 worker 节点。
- `financial_query_agent` 是 `builder.compile()` 的返回值；外层 `plan_agent` 不感知内部节点。

- `extract_intent` 负责：
  - 获取 `sub_question` 或最后一条用户消息。
  - 调用 LLM 抽取 `FinancialFactExtraction`。
  - 转成 `FinancialQueryIntent`。
  - 写入 `financial_query_text`、`financial_query_intent`。
  - 抽取失败时沿用当前兜底行为：把原问题作为 company 候选，`years=[]`、`metrics=[]`、`operation="lookup"`，避免节点异常直接打断子图。

- `financial_tool_selection` 负责：
  - 调用 `FinancialQueryRouter.match_template()`。
  - 未命中模板时调用 `FinancialQueryRouter.route_generic_search()`。
  - 写入 `financial_query_route` 和 `financial_query_template`。
  - 条件边只返回四个稳定分支标签：`template`、`fuzzy`、`clarify`、`sql`。
  - 模板命中时 route 使用 `template.name`，未命中模板时 route 使用 router 的原始 route：`generic_search_safe`、`needs_clarification`、`text_to_sql_fallback`。

- `template_fact_agent` 负责：
  - 调用 `FinancialFactService.run_template()`。
  - 格式化答案和 citations。
  - 返回 `task_results`、`messages`、`steps`。

- `fuzzy_fact_agent` 负责：
  - 调用 `FinancialFactService.search()`。
  - 复用现有 generic safe search 行为。
  - 返回命中或 no-result。

- `clarification_agent` 负责：
  - 返回 `FINANCIAL_QUERY_NEEDS_CLARIFICATION_ANSWER`。

- `text_to_sql_agent` 负责：
  - 返回 `FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER`。
  - 不新增真实 SQL 执行能力。

- 新子图内部不再调用 `FinancialFactService.execute_query()`；该方法只作为旧调用方兼容入口保留。
- 建议抽一个本文件内的小 helper 统一构造金融查询返回值，避免四个 worker 重复拼 `messages`、`citations`、`task_results`、`steps`：

```python
def _financial_query_output(...):
    ...
```

- helper 只做结果包装，不承担路由或查询逻辑。

## Interfaces

- `plan_agent` 不改对外调用方式，仍使用：

```python
builder.add_node("financial_query", financial_query_agent)
```

- `db_agent = financial_query_agent` 兼容别名继续保留。
- `FinAgentState` 补充可选字段：
  - `financial_query_text: str`
  - `financial_query_intent: FinancialQueryIntent`
  - `financial_query_route: str`
  - `financial_query_template: FinancialQueryTemplate | None`

- `FinAgentState` 字段声明建议：

```python
financial_query_text: NotRequired[str]
financial_query_intent: NotRequired[FinancialQueryIntent]
financial_query_route: NotRequired[str]
financial_query_template: NotRequired[FinancialQueryTemplate | None]
```

- 这些字段只在 `financial_query` 子图内部串行写入，不需要 `Annotated[..., add]` reducer。
- 类型导入优先从叶子模块引入，避免通过聚合入口增加循环依赖风险：

```python
from app.services.financial.query_router import FinancialQueryTemplate
from app.services.financial.schemas import FinancialQueryIntent
```

- `task_results.type` 继续使用 `financial_query`。
- `steps` 改为更细粒度但稳定的节点路径：
  - `financial_query_extract`
  - `financial_tool_selection`
  - `template_fact_agent`
  - `fuzzy_fact_agent`
  - `clarification_agent`
  - `text_to_sql_agent`

## Node Contracts

- `extract_intent` 输出：
  - `financial_query_text`
  - `financial_query_intent`
  - `steps=["financial_query_extract"]`

- `financial_tool_selection` 输出：
  - `financial_query_route`
  - `financial_query_template`
  - `steps=["financial_tool_selection"]`

- `template_fact_agent` 前置条件：
  - `financial_query_intent` 必须存在。
  - `financial_query_template` 必须存在。
  - 缺少前置字段时返回 no-result，并记录 `template_fact_agent_error`。

- `fuzzy_fact_agent` 前置条件：
  - `financial_query_intent` 必须存在。
  - 仅处理 `generic_search_safe`。
  - 缺少前置字段或底层查询异常时返回 no-result，并记录 `fuzzy_fact_agent_error`。

- `clarification_agent` 和 `text_to_sql_agent` 不访问数据库，只返回固定 fallback 文案。

## Error Handling

- LLM 抽取失败：记录异常，使用当前兜底 extraction，继续进入 selector。
- 模板执行失败：记录异常，返回 `FINANCIAL_QUERY_NO_RESULT_ANSWER`，`context` 使用 `（数据库查询失败）` 或同等稳定文案。
- 通用搜索失败：同模板执行失败处理。
- 节点返回的 `task_results` 必须始终包含 `sub_task_id`、`question`、`type`、`context`，避免 summarize 阶段出现缺字段分支。

## Test Plan

- 更新 `tests/test_db_agent.py`，保持旧测试语义：
  - 无事实返回 no-result。
  - 命中模板返回格式化答案和 citation。
  - `db_agent` 仍是 `financial_query_agent` 兼容别名。

- 测试 mock 点需要从旧的 `FinancialFactService.execute_query()` 迁移：
  - 抽取仍可 mock `_extract_query_params()`。
  - 模板路径 mock `FinancialQueryRouter.match_template()` 和 `FinancialFactService.run_template()`。
  - fuzzy 路径 mock `FinancialQueryRouter.route_generic_search()` 和 `FinancialFactService.search()`。
  - clarify / sql fallback 路径只 mock router route，不需要 mock DB。

- 新增或扩展测试覆盖内部路由：
  - 模板命中走 `template_fact_agent`。
  - `generic_search_safe` 走 `fuzzy_fact_agent`。
  - `needs_clarification` 走 `clarification_agent`。
  - `text_to_sql_fallback` 走 `text_to_sql_agent`。
  - 节点返回的 `steps` 包含对应稳定节点名。
  - 子图编译后仍可通过 `await financial_query_agent.ainvoke(state, config)` 或测试项目现有调用方式执行。

- 运行验证：

```bash
conda run -n agent python -m py_compile app/agents/subgraphs/financial_query.py app/agents/states.py tests/test_db_agent.py
conda run -n agent python -m pytest tests/test_db_agent.py tests/test_financial_query_router.py tests/test_financial_fact_service.py
```

## Acceptance Criteria

- `plan_agent` 中 `builder.add_node("financial_query", financial_query_agent)` 不需要修改。
- `db_agent is financial_query_agent` 继续成立。
- `financial_query.py` 中不存在新的“大节点”总控分支；路由由 selector 节点和 conditional edges 表达。
- `TEXT_TO_SQL_FALLBACK_ROUTE` 只进入 `text_to_sql_agent` 固定返回，不生成、不执行 SQL。
- 旧测试语义保持不变，新增测试能证明四条内部路径分别进入正确节点。

## Assumptions

- 本轮目标是修复 `financial_query.py` 的 Agent 编排杂乱，不继续拆 `app/services/financial/*`。
- `text_to_sql_agent` 暂时只是 fallback 节点，不生成、不执行 SQL。
- `fuzzy_fact_agent` 对应当前的低风险通用结构化搜索，不新增新的模糊检索算法。
- `plan_agent` 外层 fanout 不按 Mermaid 图新增 `sql` 任务类型；`sql` 是 `financial_query` 子图内部路由结果。
