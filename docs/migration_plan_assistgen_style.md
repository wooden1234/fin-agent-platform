# AssistGen 编码风格迁移方案

> 将 `assistgen/llm_backend/app/lg_agent/kg_sub_graph/agentic_rag_agents` 的编码风格（"一个功能一个文件夹，一个节点一个文件夹"）引入 `fin-agent-platform`。

---

## 一、当前问题

`fin-agent-platform/app/agents/` 现有结构：

```
agents/
├── __init__.py
├── states.py
├── graph.py
├── supervisor.py          # 扁平文件，无文件夹
├── guardrails.py           # 扁平文件，无文件夹
├── context_compressor.py   # 扁平文件，无文件夹
├── general_agent.py        # 扁平文件，无文件夹
├── final_answer.py         # 扁平文件，无文件夹
├── risk_triage.py          # 扁平文件，无文件夹
├── llm.py                  # 工具
├── checkpoint.py           # 工具
├── prompts/                # 提示词与节点分离
│   ├── general.py
│   └── supervisor.py
├── subgraphs/
│   ├── __init__.py
│   ├── faq.py              # 扁平文件
│   ├── general.py          # 扁平文件
│   ├── pdf.py              # 扁平文件
│   ├── planner.py          # 扁平文件
│   ├── summarize.py        # 扁平文件
│   ├── plan_agent.py       # 扁平文件
│   ├── prompts/            # 提示词与节点分离
│   │   ├── faq.py
│   │   ├── pdf.py
│   │   ├── planner.py
│   │   └── summarize.py
│   └── financial_query/    # ✅ 已部分采用此风格
│       ├── __init__.py
│       ├── clarification_agent.py  # 可改为 node.py
│       ├── common.py
│       ├── extract.py              # 可改为 node.py
│       ├── template_sql_agent.py   # 可改为 node.py
│       └── text_to_sql_agent.py    # 可改为 node.py
```

### 主要痛点

| 问题 | 描述 |
|------|------|
| **扁平文件** | `guardrails.py` 含 node + edge 两个函数，但文件名不体现"节点"身份 |
| **提示词分离** | `prompts/` 与节点代码分离，改一个节点需要改两个文件，易遗漏 |
| **风格不一致** | `financial_query/` 已近似 assistgen 风格，其他子图仍是扁平文件 |
| **无 components 层** | 没有将"节点"与"图编排"明确分离的层级 |
| **节点命名随意** | `guardrails.py`、`supervisor.py` 等无统一命名模式，`financial_query/` 内用 `extract.py` 而非 `node.py` |

---

## 二、目标结构（三层递进式）

迁移后的 `app/agents/` 遵循 assistgen 风格，采用**三层递进**结构：

```
                    ┌─────────────────────────────────┐
                    │       Layer 1: components/       │
                    │ 所有节点均为文件夹 + finance_agent│
                    │  guardrails/, supervisor/,       │
                    │  risk_triage/, general_agent/    │
                    │  context_compressor/,            │
                    │  final_answer/                   │
                    │  ┌───────────────────────────┐   │
                    │  │   finance_agent (子图)     │   │
                    │  └───────────────────────────┘   │
                    └─────────────────────────────────┘
                                    │
                    ┌──────────────────────────────────┐
                    │   Layer 2: finance_agent/         │
                    │  planner → supervisor → workers   │
                    │  → summarize                      │
                    │  ┌──────────┐ ┌─────────┐       │
                    │  │planner/  │ │faq_agent│       │
                    │  │supervisor│ │pdf_agent│       │
                    │  │ + 路由    │ │financial│       │
                    │  └──────────┘ │_query   │       │
                    │               │_agent/  │       │
                    └───────────────┴─────────┘       │
                                    │
                    ┌──────────────────────────────────┐
                    │ Layer 3: financial_query_agent/   │
                    │  extract_intent/ → template_sql/ │
                    │  → [clarify/ | text_to_sql/]     │
                    │  每个节点一个文件夹               │
                    └──────────────────────────────────┘
```

### 完整目录树

```
app/agents/
├── __init__.py                  # 统一导出（保持向后兼容）
├── llm.py                       # LLM 工具（保留）
├── checkpoint.py                # Checkpoint 工具（保留）
├── states.py                    # 全局 State（保留）
│
├── components/                  # 🆕 Layer 1: 所有节点，每个节点一个文件夹
│   ├── __init__.py              # 聚合导出
│   ├── guardrails/              # Layer 1 — 原 guardrails.py
│   │   ├── __init__.py
│   │   ├── node.py              # guardrails_node + guardrails_edge
│   │   └── patterns.py          # _INJECTION_PATTERNS 等常量
│   ├── context_compressor/      # Layer 1 — 原 context_compressor.py
│   │   ├── __init__.py
│   │   ├── node.py              # compress_context
│   │   └── prompts.py           # SUMMARY_PROMPT
│   ├── supervisor/              # Layer 1 — 原 supervisor.py（主图路由）
│   │   ├── __init__.py
│   │   ├── node.py              # analyze_and_route_query + route_query
│   │   └── prompts.py           # SUPERVISOR_SYSTEM_PROMPT
│   ├── risk_triage/             # Layer 1 — 原 risk_triage.py
│   │   ├── __init__.py
│   │   ├── node.py              # risk_triage_node + risk_triage_edge
│   │   ├── models.py            # RiskAssessment
│   │   └── prompts.py           # RISK_TRIAGE_PROMPT
│   ├── general_agent/           # Layer 1 — 原 general_agent.py
│   │   ├── __init__.py
│   │   ├── node.py              # general_agent
│   │   └── prompts.py           # GENERAL_SYSTEM_PROMPT
│   ├── final_answer/            # Layer 1 — 原 final_answer.py
│   │   ├── __init__.py
│   │   └── node.py              # final_answer_node
│   │
│   └── finance_agent/           # 🆕 Layer 1+2: 整个 Finance Agent 子图
│       ├── __init__.py          # 编译导出 finance_agent 子图
│       ├── graph.py             # 子图构建: planner → supervisor → workers → summarize
│       │
│       ├── planner/             # Layer 2 — 任务分解（原 subgraphs/planner.py）
│       │   ├── __init__.py
│       │   ├── node.py          # planner_node
│       │   └── prompts.py       # PLANNER_SYSTEM_PROMPT
│       │
│       ├── supervisor/          # 🆕 Layer 2 — finance_agent 的 LLM 路由节点
│       │   ├── __init__.py
│       │   ├── node.py          # finance_agent_supervisor: 分析 sub_task 并路由
│       │   └── prompts.py       # SUPERVISOR_PROMPT
│       │
│       ├── workers/             # 🆕 Layer 2 — Worker 注册表
│       │   ├── __init__.py      # WORKER_REGISTRY
│       │   ├── faq_agent/       # → finance_agent/faq_agent
│       │   ├── pdf_agent/       # → finance_agent/pdf_agent
│       │   └── financial_query_agent/ # → finance_agent/financial_query_agent
│       │
│       ├── faq_agent/           # Layer 2 — FAQ 问答（原 subgraphs/faq.py）
│       │   ├── __init__.py
│       │   ├── node.py
│       │   └── prompts.py       # FAQ_SYSTEM_PROMPT
│       │
│       ├── pdf_agent/           # Layer 2 — PDF 文档问答（原 subgraphs/pdf.py）
│       │   ├── __init__.py
│       │   ├── node.py
│       │   └── prompts.py       # PDF_SYSTEM_PROMPT
│       │
│       ├── financial_query_agent/  # Layer 2→3 — 独立子 Agent 图
│       │   ├── __init__.py      # 编译 financial_query_agent 子图
│       │   ├── common.py        # 共享工具（query_from_state 等）
│       │   ├── graph.py         # 子图构建逻辑
│       │   ├── extract_intent/  # Layer 3 — 意图抽取
│       │   │   ├── __init__.py
│       │   │   ├── node.py
│       │   │   └── prompts.py   # FINANCIAL_QUERY_EXTRACT_PROMPT
│       │   ├── template_sql/    # Layer 3 — 模板 SQL
│       │   │   ├── __init__.py
│       │   │   ├── node.py
│       │   │   └── prompts.py   # FINANCIAL_QUERY_TEMPLATE_SELECTION_PROMPT
│       │   ├── text_to_sql/     # Layer 3 — 复杂 SQL
│       │   │   ├── __init__.py
│       │   │   ├── node.py
│       │   │   └── prompts.py   # FINANCIAL_QUERY_TEXT_TO_SQL_PROMPT
│       │   └── clarification/   # Layer 3 — 补充追问
│       │       ├── __init__.py
│       │       ├── node.py
│       │       └── prompts.py   # FINANCIAL_QUERY_CLARIFICATION_PROMPT
│       │
│       └── summarize/           # Layer 2 — 结果汇总（原 subgraphs/summarize.py）
│           ├── __init__.py
│           ├── node.py
│           └── prompts.py       # SUMMARIZE_SYSTEM_PROMPT
│
├── graph.py                     # 主图编译（引用 components/ 中的节点）
└── prompts/                     # ❌ 删除（提示词已移入各节点目录）
```

### 三层递进关系一览

| 层级 | 路径 | 内容 | 职责 |
|------|------|------|------|
| **Layer 1** | `components/` 顶层 | `guardrails/`, `context_compressor/`, `supervisor/`, `risk_triage/`, `general_agent/`, `final_answer/`, **`finance_agent/`** | 主图编排的 6 个节点 + 整个 Finance Agent 作为一个子图节点 |
| **Layer 2** | `components/finance_agent/` | `planner/`, `supervisor/`, `workers/`, `faq_agent/`, `pdf_agent/`, **`financial_query_agent/`**, `summarize/` | Finance Agent 内部: 任务分解 → LLM 路由 → 并行 Worker → 汇总 |
| **Layer 3** | `components/finance_agent/financial_query_agent/` | `extract_intent/`, `template_sql/`, `text_to_sql/`, `clarification/` | financial_query_agent 内部子图，每个节点严格按文件夹组织 |

---

## 三、迁移步骤（分阶段执行）

### Phase 1: 创建 `components/` + 迁移扁平节点（影响最小）

**目标**: 将 `agents/` 下的 6 个扁平节点文件迁移为文件夹结构。

| 原文件 | 目标文件夹 |
|--------|-----------|
| `guardrails.py` | `components/guardrails/` |
| `context_compressor.py` | `components/context_compressor/` |
| `supervisor.py` | `components/supervisor/` |
| `risk_triage.py` | `components/risk_triage/` |
| `general_agent.py` | `components/general_agent/` |
| `final_answer.py` | `components/final_answer/` |

**操作要点**:
1. 创建 `components/` 目录
2. 为每个节点创建文件夹，内含 `__init__.py` + `node.py`
3. 节点原有前置常量/内联提示词视复杂度决定是否提取为 `prompts.py` 或 `patterns.py`
4. 更新 `graph.py` 的 import 路径
5. **保留原文件做兼容重定向**（或一次性改完所有引用）
6. 更新 `__init__.py` 保持导出不变

### Phase 2: 迁移 `subgraphs/` + `plan_agent` 改用 Supervisor 框架

**目标**: 将 `subgraphs/` 下的扁平子图迁移到 `components/`，同时将 `plan_agent` 的静态 fanout 改为 Supervisor 动态路由。

#### Phase 2a: 构建 `finance_agent/` 容器 + 迁移简单子图

首先创建 `finance_agent/` 作为 Finance Agent 的整体容器，所有子图节点都放在其下。

**简单子图直接迁移**（faq、pdf、general）：

| 原文件 | 目标文件夹 |
|--------|-----------|
| `subgraphs/faq.py` | `finance_agent/faq_agent/` |
| `subgraphs/pdf.py` | `finance_agent/pdf_agent/` |
| `subgraphs/general.py` | 内容并入 `components/general_agent/`（已与顶层 general_agent 重复） |

#### Phase 2b: `finance_agent` 内部改用 Supervisor 框架

**现状** — 静态 fanout（在 `subgraphs/plan_agent.py` 的 `_fanout_from_planner` 中硬编码）：

```
planner → _fanout_from_planner(task.type 硬编码) → workers → summarize
```

**目标** — Supervisor 动态路由（全部在 `finance_agent/` 内）：

```
finance_agent 子图:
    planner → supervisor(LLM路由) → [faq_agent | pdf_agent | financial_query_agent] → summarize

            ┌─ supervisor ──────────────────┐
            │  接收 planner 输出的 sub_task, │
            │  用 LLM 分析语义，判断最佳     │
            │  worker，改写子问题，返回路由   │
            └────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
     faq_agent      pdf_agent    financial_query_agent
         │              │              │
         └──────────────┼──────────────┘
                        ▼
                   summarize
```

**核心变更**：

| 原文件 | 目标路径 | 说明 |
|--------|---------|------|
| `subgraphs/plan_agent.py` | `finance_agent/graph.py` | 子图构建：planner → supervisor → workers → summarize |
| `subgraphs/planner.py` | `finance_agent/planner/node.py` | 任务分解 |
| `subgraphs/summarize.py` | `finance_agent/summarize/node.py` | 结果汇总 |
| — 🆕 | `finance_agent/supervisor/node.py` | **Supervisor 节点**：LLM 分析 sub_task，决策路由目标 |
| — 🆕 | `finance_agent/supervisor/prompts.py` | SUPERVISOR_PROMPT |
| — 🆕 | `finance_agent/workers/__init__.py` | WORKER_REGISTRY 注册表 |

**Supervisor 节点设计**（`finance_agent/supervisor/node.py`）：

```python
class PlanAgentRouting(BaseModel):
    """Supervisor 输出：为每个子任务决定路由目标"""
    worker: Literal["faq", "pdf", "financial_query_agent"]
    rewritten_question: str = Field(description="为 target worker 改写的子问题")
    reason: str = Field(description="路由理由")


WORKER_REGISTRY = {
    "faq": "faq_agent",
    "pdf": "pdf_agent",
    "financial_query_agent": "financial_query_agent",
}


async def finance_agent_supervisor(
    state: FinAgentState,
    config: RunnableConfig,
) -> dict:
    """Supervisor 节点：为每个 sub_task 用 LLM 决定路由目标。"""
    sub_tasks = state.get("sub_tasks", [])
    routes = []
    for task in sub_tasks:
        # LLM 分析 task.question，决定最佳 worker
        routing = await llm.with_structured_output(PlanAgentRouting).ainvoke(...)
        routes.append({
            "worker": WORKER_REGISTRY[routing.worker],
            "question": routing.rewritten_question,
            "sub_task_id": task.id,
        })
    return {"plan_agent_routes": routes}


def route_after_supervisor(state: FinAgentState) -> list[Send]:
    """条件边：Supervisor 输出 → 并行 Send 到各 Worker。"""
    return [
        Send(route["worker"], {
            "sub_question": route["question"],
            "sub_task_id": route["sub_task_id"],
        })
        for route in state.get("plan_agent_routes", [])
    ]
```

**优势**：
- 新增 agent 只需注册到 `WORKER_REGISTRY`，Supervisor LLM 自动学会路由
- 路由逻辑基于子任务语义，不依赖硬编码 type 字段
- 易于扩展：注册新 worker + 写 worker 节点即可
- `finance_agent` 内部所有组件内聚（planner、supervisor、workers、summarize 都在自己的文件夹）

### Phase 3: `financial_query_agent` 重构为独立子 Agent 图

**目标**: 将 `financial_query_agent` 升级为"可独立存在、可被任何父图引用"的子 Agent 图，内部子节点严格遵循文件夹风格。路径从 `subgraphs/financial_query/` 迁移到 `finance_agent/financial_query_agent/`。

| 原文件 | 目标文件夹 |
|--------|-----------|
| `subgraphs/financial_query/__init__.py` | `finance_agent/financial_query_agent/__init__.py`（仅导出） |
| — 🆕 | `finance_agent/financial_query_agent/graph.py` | 子图构建逻辑（从 `__init__` 移出） |
| `extract.py` | `finance_agent/financial_query_agent/extract_intent/node.py` |
| `clarification_agent.py` | `finance_agent/financial_query_agent/clarification/node.py` |
| `template_sql_agent.py` | `finance_agent/financial_query_agent/template_sql/node.py` |
| `text_to_sql_agent.py` | `finance_agent/financial_query_agent/text_to_sql/node.py` |
| `common.py` | `finance_agent/financial_query_agent/common.py`（保留） |

**`financial_query_agent` 作为独立子 Agent 图的设计**（Layer 2→3）：

```
finance_agent/financial_query_agent/
├── __init__.py           # 编译导出 financial_query_agent
├── common.py             # query_from_state 等共享工具
├── graph.py              # 🆕 子图构建逻辑
├── extract_intent/       # Layer 3: 意图抽取
│   ├── __init__.py
│   ├── node.py
│   └── prompts.py
├── template_sql/         # Layer 3: 模板 SQL
│   ├── __init__.py
│   ├── node.py
│   └── prompts.py
├── text_to_sql/          # Layer 3: 复杂 SQL
│   ├── __init__.py
│   ├── node.py
│   └── prompts.py
└── clarification/        # Layer 3: 补充追问
    ├── __init__.py
    ├── node.py
    └── prompts.py
```

**`graph.py` 结构**：
```python
# finance_agent/financial_query_agent/graph.py
from langgraph.graph import END, START, StateGraph
from app.agents.components.finance_agent.financial_query_agent.extract_intent import extract_intent
from app.agents.components.finance_agent.financial_query_agent.template_sql import template_sql_agent
from app.agents.components.finance_agent.financial_query_agent.clarification import clarification_agent
from app.agents.components.finance_agent.financial_query_agent.text_to_sql import text_to_sql_agent

def route_after_template_sql(state: FinAgentState) -> str:
    route_name = state.get("financial_query_route", "done")
    return {"clarify": "clarify", "sql": "sql"}.get(route_name, "end")

def build_financial_query_subgraph() -> StateGraph:
    builder = StateGraph(FinAgentState)
    builder.add_node("extract_intent", extract_intent)
    builder.add_node("template_sql_agent", template_sql_agent)
    builder.add_node("clarify", clarification_agent)
    builder.add_node("sql", text_to_sql_agent)
    builder.add_edge(START, "extract_intent")
    builder.add_edge("extract_intent", "template_sql_agent")
    builder.add_conditional_edges("template_sql_agent", route_after_template_sql,
        {"clarify": "clarify", "sql": "sql", "end": END})
    builder.add_edge("clarify", END)
    builder.add_edge("sql", END)
    return builder
```

**这样设计的好处**：
- `financial_query_agent` 是一个**编译好的独立子图**，可作为黑盒被 `finance_agent`、主图或未来其他父图引用
- 内部修改不影响外部调用者
- 每个内部节点都是文件夹结构，可独立测试
- `graph.py` 把图编排和节点实现分离，符合 assistgen 的 `workflows/` 理念

### Phase 4: 清理 + 删除旧文件

1. 删除 `agents/prompts/`（提示词已移入各节点 `prompts.py`）
2. 删除 `agents/subgraphs/prompts/`（提示词已移入各节点 `prompts.py`）
3. 删除 `agents/subgraphs/faq.py`、`pdf.py`、`general.py`、`planner.py`、`summarize.py`、`plan_agent.py`
4. 删除 `agents/subgraphs/financial_query/` 下所有文件（已迁入 `finance_agent/financial_query_agent/`）
5. 删除 `agents/subgraphs/` 目录（空壳）
6. 删除 `agents/guardrails.py`、`context_compressor.py`、`supervisor.py`、`risk_triage.py`、`general_agent.py`、`final_answer.py`
7. 更新测试文件 import 路径
8. 验证 `finance_agent` 子图的 Supervisor 框架下各路由路径正常工作
9. 验证 `financial_query_agent` 作为第三层子图可被 `finance_agent` 和其他父图正确引用

---

## 四、需要修改的文件清单

### 4.1 新增文件（三层递进结构）

```
app/agents/components/
├── __init__.py                                    # 聚合导出
│
├── guardrails/__init__.py                         # Layer 1
├── guardrails/node.py
├── guardrails/patterns.py
│
├── context_compressor/__init__.py                 # Layer 1
├── context_compressor/node.py
├── context_compressor/prompts.py
│
├── supervisor/__init__.py                         # Layer 1
├── supervisor/node.py
├── supervisor/prompts.py
│
├── risk_triage/__init__.py                        # Layer 1
├── risk_triage/node.py
├── risk_triage/models.py
├── risk_triage/prompts.py
│
├── general_agent/__init__.py                      # Layer 1
├── general_agent/node.py
├── general_agent/prompts.py
│
├── final_answer/__init__.py                       # Layer 1
├── final_answer/node.py
│
├── finance_agent/                                  # Layer 1+2+3
    ├── __init__.py                                # 导出编译后子图
    ├── graph.py                                   # 主子图构建
    │
    ├── planner/                                   # Layer 2
    │   ├── __init__.py
    │   ├── node.py
    │   └── prompts.py
    │
    ├── supervisor/                                # 🆕 Layer 2
    │   ├── __init__.py
    │   ├── node.py
    │   └── prompts.py
    │
    ├── workers/                                   # 🆕 Layer 2
    │   └── __init__.py
    │
    ├── faq_agent/                                 # Layer 2
    │   ├── __init__.py
    │   ├── node.py
    │   └── prompts.py
    │
    ├── pdf_agent/                                 # Layer 2
    │   ├── __init__.py
    │   ├── node.py
    │   └── prompts.py
    │
    ├── financial_query_agent/                     # Layer 2→3
    │   ├── __init__.py
    │   ├── graph.py
    │   ├── common.py
    │   ├── extract_intent/
    │   │   ├── __init__.py
    │   │   ├── node.py
    │   │   └── prompts.py
    │   ├── template_sql/
    │   │   ├── __init__.py
    │   │   ├── node.py
    │   │   └── prompts.py
    │   ├── text_to_sql/
    │   │   ├── __init__.py
    │   │   ├── node.py
    │   │   └── prompts.py
    │   └── clarification/
    │       ├── __init__.py
    │       ├── node.py
    │       └── prompts.py
    │
    └── summarize/                                 # Layer 2
        ├── __init__.py
        ├── node.py
        └── prompts.py
```

### 4.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `app/agents/__init__.py` | 更新 import 路径指向 `components/` |
| `app/agents/graph.py` | 更新所有 import 路径 |
| `app/api/agent.py` | 检查引用，更新 import |
| 各测试文件 | 更新 import 路径 |

### 4.3 删除文件

```
app/agents/prompts/                           # 整体删除（提示词已移入各节点 prompts.py）
app/agents/prompts/general.py
app/agents/prompts/supervisor.py

app/agents/subgraphs/prompts/                 # 整体删除
app/agents/subgraphs/prompts/faq.py
app/agents/subgraphs/prompts/pdf.py
app/agents/subgraphs/prompts/planner.py
app/agents/subgraphs/prompts/summarize.py
app/agents/subgraphs/prompts/financial_query.py

app/agents/subgraphs/faq.py                   # → finance_agent/faq_agent/
app/agents/subgraphs/pdf.py                   # → finance_agent/pdf_agent/
app/agents/subgraphs/general.py               # → components/general_agent/
app/agents/subgraphs/planner.py               # → finance_agent/planner/
app/agents/subgraphs/summarize.py             # → finance_agent/summarize/
app/agents/subgraphs/plan_agent.py            # → finance_agent/graph.py（改用 Supervisor）

app/agents/subgraphs/financial_query/         # 整体迁移到 finance_agent/financial_query_agent/
app/agents/subgraphs/financial_query/__init__.py
app/agents/subgraphs/financial_query/common.py
app/agents/subgraphs/financial_query/extract.py
app/agents/subgraphs/financial_query/clarification_agent.py
app/agents/subgraphs/financial_query/template_sql_agent.py
app/agents/subgraphs/financial_query/text_to_sql_agent.py

app/agents/subgraphs/                         # 空壳 → 删除

app/agents/guardrails.py                      # → components/guardrails/
app/agents/context_compressor.py              # → components/context_compressor/
app/agents/supervisor.py                      # → components/supervisor/
app/agents/risk_triage.py                     # → components/risk_triage/
app/agents/general_agent.py                   # → components/general_agent/
app/agents/final_answer.py                    # → components/final_answer/
```

---

## 五、`__init__.py` 导出约定（与 assistgen 对齐）

### 节点级（每个节点文件夹）

```python
# components/guardrails/__init__.py
from .node import guardrails_node, guardrails_edge

__all__ = ["guardrails_node", "guardrails_edge"]
```

### 组件级（components/ 聚合导出）

```python
# components/__init__.py
from .guardrails import guardrails_node, guardrails_edge
from .context_compressor import compress_context
from .supervisor import analyze_and_route_query, route_query
from .risk_triage import risk_triage_node, risk_triage_edge
from .general_agent import general_agent
from .final_answer import final_answer_node
from .finance_agent import finance_agent  # 编译好的 Finance Agent 子图

__all__ = [
    "guardrails_node", "guardrails_edge",
    "compress_context",
    "analyze_and_route_query", "route_query",
    "risk_triage_node", "risk_triage_edge",
    "general_agent",
    "final_answer_node",
    "finance_agent",              # Layer 1+2+3 的完整 Finance Agent
]
```

### 主 `agents/__init__.py`（保持向后兼容）

```python
# 重导出 components/ 中的顶层内容
from app.agents.components import (
    guardrails_node, guardrails_edge,
    compress_context,
    analyze_and_route_query, route_query,
    risk_triage_node, risk_triage_edge,
    general_agent,
    final_answer_node,
    finance_agent,              # 整个 Finance Agent (Layer 1+2+3)
)
from app.agents.graph import build_graph, get_graph
from app.agents.states import FinAgentInput, FinAgentState, Router

__all__ = [...]
```

---

## 六、graph.py 修改示例

```python
# 修改前
from app.agents.general_agent import general_agent
from app.agents.subgraphs.plan_agent import plan_agent
from app.agents.supervisor import analyze_and_route_query, route_query
from app.agents.guardrails import guardrails_edge, guardrails_node
from app.agents.risk_triage import risk_triage_edge, risk_triage_node
from app.agents.final_answer import final_answer_node
from app.agents.context_compressor import compress_context

# 修改后（通过 components/__init__.py 统一导入）
from app.agents.components import (
    guardrails_node, guardrails_edge,
    compress_context,
    analyze_and_route_query, route_query,
    risk_triage_node, risk_triage_edge,
    general_agent,
    final_answer_node,
    finance_agent,                # ← 编译后的 Finance Agent 子图
)
```

---

## 七、关键设计详解

### 7.1 `finance_agent` Supervisor 框架设计

#### 背景：为什么不用静态 fanout？

当前 `_fanout_from_planner` 的问题：

```python
def _fanout_from_planner(state: FinAgentState) -> list[Send]:
    for task in sub_tasks:
        if task.type == "faq":           # 硬编码
            Send("faq_agent", ...)
        elif task.type == "pdf":          # 硬编码
            Send("pdf_agent", ...)
        elif task.type == "financial_query":  # 硬编码
            Send("financial_query", ...)
```

- **每次新增 agent 类型都要改这个函数**
- **路由逻辑不灵活**：无法根据子任务的具体语义做判断
- **Planner 承担了"路由决策"职责**，职责不够单一

#### Supervisor 模式

```python
# components/finance_agent/supervisor/node.py

class PlanAgentRouting(BaseModel):
    """为单个 sub_task 的路由决策"""
    worker: Literal["faq", "pdf", "financial_query_agent"]


WORKER_REGISTRY = {
    "faq": {
        "node": "faq_agent",
        "description": "通用金融知识问答（交易规则、术语、常识）",
    },
    "pdf": {
        "node": "pdf_agent",
        "description": "PDF 文档问答（年报解读、政策文件、引用出处）",
    },
    "financial_query_agent": {
        "node": "financial_query_agent",
        "description": "结构化财务数值查询（营收、利润、指标）",
    },
}


async def plan_agent_supervisor(
    state: FinAgentState,
    config: RunnableConfig,
) -> dict:
    """用 LLM 分析每个 sub_task，动态决定路由到哪个 worker。"""
    sub_tasks: list[SubTask] = list(state.get("sub_tasks") or [])
    routes = []

    for task in sub_tasks:
        # LLM 分析 task.question 的语义，从 WORKER_REGISTRY 中选择最佳 worker
        routing = await _route_single_task(task, config)
        routes.append({
            "worker": WORKER_REGISTRY[routing.worker]["node"],
            "question": routing.rewritten_question,
            "sub_task_id": task.id,
            "confidence": routing.confidence,
        })

    return {"plan_agent_routes": routes}


def route_after_supervisor(state: FinAgentState) -> list[Send]:
    """条件边：Supervisor 输出 → 并行 Send 到各 Worker。"""
    routes = state.get("plan_agent_routes", [])
    if not routes:
        # 异常兜底
        return [Send("faq_agent", {"sub_question": "请重新描述问题"})]

    return [
        Send(route["worker"], {
            "sub_question": route["question"],
            "sub_task_id": route["sub_task_id"],
        })
        for route in routes
    ]
```

#### finance_agent/graph.py 子图构建

```python
# components/finance_agent/graph.py
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from app.agents.components.finance_agent.planner import planner_node
from app.agents.components.finance_agent.supervisor import finance_agent_supervisor, route_after_supervisor
from app.agents.components.finance_agent.summarize import summarize_node
from app.agents.components.finance_agent.faq_agent import faq_agent
from app.agents.components.finance_agent.pdf_agent import pdf_agent
from app.agents.components.finance_agent.financial_query_agent import financial_query_agent

def build_finance_agent_subgraph() -> StateGraph:
    builder = StateGraph(FinAgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", finance_agent_supervisor)
    builder.add_node("faq_agent", faq_agent)
    builder.add_node("pdf_agent", pdf_agent)
    builder.add_node("financial_query_agent", financial_query_agent)
    builder.add_node("summarize", summarize_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    builder.add_edge("faq_agent", "summarize")
    builder.add_edge("pdf_agent", "summarize")
    builder.add_edge("financial_query_agent", "summarize")
    builder.add_edge("summarize", END)

    return builder

finance_agent = build_finance_agent_subgraph().compile()
```

#### Supervisor 路由优势

| 维度 | 旧方案（静态 fanout） | 新方案（Supervisor） |
|------|---------------------|---------------------|
| 路由依据 | `task.type` 硬编码 | LLM 语义理解 |
| 扩展 worker | 改 `_fanout_from_planner` 代码 | 注册到 `WORKER_REGISTRY` + 更新 prompt |
| 子问题改写 | 不做改写 | LLM 可为 worker 改写子问题 |
| 路由透明度 | 无 | 输出 `reason` + `confidence`，可观测 |
| 层级归属 | 不明确 | Layer 2(finance_agent) 内部，清晰递进 |

### 7.2 `financial_query_agent` 作为独立子 Agent 图（Layer 3）

#### 设计原则

`financial_query_agent` 是 `finance_agent` 下的一个**自包含编译子图**，遵循以下原则：

1. **可独立测试**：`financial_query_agent` 可以脱离 `finance_agent` 单独运行
2. **可被内部复用**：`finance_agent` 的 Supervisor 将其作为一个 worker 节点注册
3. **未来可被外部引用**：主图或其他未来父图可以直接引用 `finance_agent.financial_query_agent`
4. **内部实现隐藏**：外部调用者只看到 `financial_query_agent` 一个节点，内部 4 个节点不暴露
5. **文件夹即节点**：`extract_intent/`、`template_sql/`、`text_to_sql/`、`clarification/` 各为一个文件夹，内有 `node.py`

#### 子图边界

```
外部传入:  sub_question, sub_task_id, [messages]
内部状态:  financial_query_text, financial_query_intent,
           financial_query_route, financial_query_route_reason,
           financial_query_missing_fields, financial_query_sql,
           financial_query_template_id
子图输出:  messages[], task_results[], citations[], steps[]
```

#### 与 finance_agent Supervisor 的交互（Layer 2 ↔ Layer 3）

```
finance_agent Supervisor (Layer 2)
  │ 路由到 financial_query_agent
  ▼
financial_query_agent — 编译子图 (Layer 2→3)
  ├── extract_intent     → 提取结构化意图
  ├── template_sql       → 尝试模板匹配
  │   ├── clarify?       → clarification (追问)
  │   └── sql?           → text_to_sql (复杂SQL)
  └── 输出 task_results
      ▼
finance_agent summarize 汇总所有 worker 结果
```

#### future financial_query_agent 独立使用场景

```python
# 方式 A: 通过 finance_agent 间接使用（推荐）
from app.agents.components.finance_agent.financial_query_agent import financial_query_agent

# 方式 B: 未来在主图中直接使用 financial_query_agent
# 不经过 finance_agent 的 planner + supervisor
builder.add_node("financial_query_agent", financial_query_agent)
builder.add_edge("some_node", "financial_query_agent")
```

---

## 九、迁移风险与缓解措施

| 风险 | 缓解措施 |
|------|---------|
| **import 路径断裂** | 分阶段迁移，每阶段跑测试验证；先用兼容重定向再删除旧文件 |
| **git 冲突** | 不与在进行的其他大改动并行；选择低活跃期执行 |
| **测试覆盖不足** | 迁移前确认测试通过，迁移后对比覆盖率 |
| **提示词遗漏** | 迁移 prompts/ 时逐文件核对 import 引用 |
| **性能影响** | 仅文件结构变化，无运行时性能影响 |
| **CI/CD 中断** | 迁移后更新所有 import 路径，跑全量测试 |

---

## 八、验证清单

### 8.1 通用验证

- [ ] `pytest` 全量通过
- [ ] `py_compile` 所有修改文件语法正确
- [ ] `uvicorn` 服务启动正常
- [ ] 所有旧文件 import 可正常工作（兼容层）
- [ ] 无遗留的 `app.agents.prompts` import
- [ ] 无遗留的 `app.agents.subgraphs` import（最终阶段）
- [ ] 目录结构与 assistgen 风格一致

### 8.2 Supervisor 框架验证

- [ ] `finance_agent` 子图在 Supervisor 框架下能正确接收 planner 输出的 sub_tasks
- [ ] Supervisor LLM 能正确路由到 faq_agent、pdf_agent、financial_query_agent 三个 worker
- [ ] 路由失败时 Supervisor 有异常兜底逻辑（回退到 faq）
- [ ] 新增 worker 只需要注册到 `WORKER_REGISTRY` 即可生效
- [ ] Supervisor 输出的 `rewritten_question` 能被 worker 正确消费
- [ ] 并行 Send 后 summarize 能正确归并所有 worker 的 task_results

### 8.3 `financial_query_agent` 子 Agent 图验证（Layer 3）

- [ ] `financial_query_agent` 可作为独立编译子图单独导入和测试
- [ ] 子图内部 4 个节点（extract_intent、template_sql、text_to_sql、clarification）均为文件夹结构
- [ ] 提示词已从 `subgraphs/prompts/financial_query.py` 移入各自节点目录
- [ ] `graph.py` 中的 `route_after_template_sql` 条件边正确
- [ ] `financial_query_agent` 可被 `finance_agent` 和主图同时引用

### 8.4 三层递进验证

- [ ] Layer 1 的 `components/__init__.py` 只导出顶层 7 个符号（6 节点 + finance_agent）
- [ ] Layer 2 的 `finance_agent/` 内包含 planner、supervisor、workers、faq_agent、pdf_agent、financial_query_agent、summarize
- [ ] Layer 3 的 `finance_agent/financial_query_agent/` 内包含 4 个文件夹节点 + graph.py
- [ ] import 路径符合层级：`app.agents.components.finance_agent.financial_query_agent.extract_intent`

---

## 十、总结

此迁移 **纯为代码组织优化**，不改变任何业务逻辑、API 行为或最终回答质量。其中两个关键架构升级：

1. **`finance_agent` 改用 Supervisor 框架** — 从静态 `task.type` fanout 升级为 LLM 语义路由，新增 worker 只需注册到 `WORKER_REGISTRY`
2. **`financial_query_agent` 升级为独立子 Agent 图** — 内部 4 个节点严格按文件夹组织，可独立编译/测试/复用

| 指标 | 迁移前 | 迁移后 |
|------|--------|--------|
| 节点扁平文件数 | 12+ | 0 |
| 节点文件夹数 | 0 | 20+ |
| 提示词与节点分离 | 是（2 个 prompts/ 目录） | 否（合并到各节点） |
| 路由方式（finance_agent 内） | 静态 `task.type` fanout | LLM Supervisor 动态路由 |
| 子图层级（financial_query_agent） | 扁平在 subgraphs/ 下 | Layer 3 独立子图，嵌套在 finance_agent 下 |
| 目录递进深度 | 2 层（agents/subgraphs） | 3 层（components/finance_agent/financial_query_agent） |
| 主图引用方式 | `plan_agent` 散装节点 | `finance_agent` 一个编译子图 |
| 风格一致性 | 低（扁平 + 文件夹混用） | 高（全部文件夹，层级递进） |
| 新增节点成本 | 创建文件 | 创建文件夹（更规范） |
| 测试可读性 | 低 | 高（按层级+文件夹分组） |
