# Agent 工具调用指南

> 如何在 fin-agent-platform 中为 Agent 添加工具调用能力。

---

## 当前状态 vs 本文目标

| 项 | 当前代码 | 本文目标 |
|:---|:---|:---|
| `@tool` / `bind_tools()` | ❌ 未使用 | ✅ 在 `general_agent` 挂载通用工具 |
| `app/agents/tools.py` | ❌ 不存在 | ✅ 新建，集中定义工具与 `GENERAL_TOOLS` |
| `get_general_llm_with_tools()` | ❌ 不存在 | ✅ 在 `llm.py` 新增工厂 |
| `general_agent` 工具循环 | ❌ 纯 LLM + `astream` | ✅ 工具轮次 `ainvoke` + 最终回答 `astream` |
| SSE 过滤 `tool_calls` | ✅ 已在 `app/api/agent.py` 实现 | 无需改动 |
| `GENERAL_SYSTEM_PROMPT` | 禁止编造金融数据 | 需同步更新，说明可用工具及边界 |

**说明**：下文示例代码可直接复制落地；按步骤改完后，建议用 `pytest` 或手动调用 `/agent/query` 验证。

---

## 主图路由（完整）

工具应挂在**理解挂载点**后再添加——不同路径经过的节点不同：

```
START
  → guardrails          # 业务范围校验，不通过 → final_answer
  → context_compressor    # 长对话压缩
  → supervisor            # with_structured_output(Router)：general | plan
       ├─ general ──────────────────→ general_agent → final_answer → END
       └─ plan ──→ risk_triage       # with_structured_output(RiskAssessment)
              ├─ L4 / needs_human ──→ END（安抚话术）
              └─ 继续 ──→ plan_agent  # 子图：planner → fanout → [faq | pdf] → summarize
                                    → final_answer → END
```

**重要**：

- `general` 路由**不经过** `risk_triage`，在 `general_agent` 上挂外部 API 时需自行考虑超时、鉴权与审计。
- 金融类工具（股价、账户余额）更建议挂在 `plan` 路径或未来 `account_agent`，并配合 `risk_triage` / guardrails。
- `SubTaskType` 虽含 `general`，但 `plan_agent` 的 fanout 目前只分发 `faq` / `pdf`；`app/agents/subgraphs/general.py` 为预留副本，主图使用的是 `app/agents/general_agent.py`。

---

## 决策模式：结构化输出 vs 工具调用

| 模式 | 适用场景 | 实现 |
|:---|:---|:---|
| **结构化输出** | 路由、分类、风险评估、任务拆分 | `llm.with_structured_output(Pydantic)` |
| **工具调用** | 查天气、计算、调外部 API | `@tool` + `bind_tools()` + Agent 内执行循环 |

两者可以并存：Supervisor / Planner 继续用结构化输出；只有需要**执行外部能力**的 Agent 节点才绑定工具。

---

## 哪些地方不需要工具

| 节点 | 当前机制 | 理由 |
|:---|:---:|:---|
| `supervisor` | `with_structured_output(Router)` | 只需 general/plan 二分类 |
| `planner` | `with_structured_output(PlannerOutput)` | 只需拆分子任务列表 |
| `risk_triage` | `with_structured_output(RiskAssessment)` | 只需评估风险等级 |
| `faq_agent` / `pdf_agent` | Retriever + LLM | 检索已是固定 pipeline，无需 LangChain Tool |

---

## 哪些地方需要工具

| 场景 | 建议挂载节点 | 工具示例 | 备注 |
|:---|:---|:---|:---|
| 查天气 | `general_agent` | `get_current_weather(city)` | 非金融，适合 general 路径 |
| 数学计算 | `general_agent` | `calculate(expression)` | 用安全 AST 解析，禁止 `eval()` |
| 翻译 | `general_agent` | `translate(text, target_lang)` | |
| 查股价 / 基金净值 | `plan` 子图或 `account_agent` | `get_stock_price(code)` | 需改 prompt + 风险策略，不宜直接挂 general |
| DB 查询 | 未来 `account_agent` | `query_user_balance(user_id)` | 需鉴权，禁止无副作用原则例外 |
| 调用外部 API | 按场景选节点 | `call_external_api(url, params)` | 超时、重试、审计日志 |

---

## 添加工具的标准步骤

### 第一步：定义工具函数

新建 `app/agents/tools.py`（**`GENERAL_TOOLS` 在此统一定义并导出**）：

```python
"""Agent 工具集"""

from __future__ import annotations

import ast
import operator

from langchain_core.tools import BaseTool, tool

# ---------- 安全计算（禁止 eval） ----------

_BIN_OPS: dict[type, object] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, object] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_ast_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        return float(op(_eval_ast_node(node.left), _eval_ast_node(node.right)))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return float(op(_eval_ast_node(node.operand)))
    raise ValueError(f"不支持的表达式: {type(node).__name__}")


def safe_calculate(expression: str) -> str:
    """仅支持 + - * / // % ** 和括号的基本算术。"""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        return str(_eval_ast_node(tree))
    except Exception as e:
        return f"计算出错：{e}"


# ---------- 工具定义 ----------

@tool
def get_current_weather(city: str) -> str:
    """查询指定城市的实时天气。

    Args:
        city: 城市名称，例如"北京"、"上海"、"广州"
    """
    # TODO: 对接真实天气 API（httpx + 超时）
    return f"{city}今天晴，22°C ~ 28°C，微风。"


@tool
def calculate(expression: str) -> str:
    """执行数学计算。

    Args:
        expression: 数学表达式，例如"3 + 5 * 2"或"(10 - 2) / 4"
    """
    return safe_calculate(expression)


# 统一导出：llm.py 与 general_agent.py 均从此处 import
GENERAL_TOOLS: list[BaseTool] = [
    get_current_weather,
    calculate,
]

TOOL_MAP: dict[str, BaseTool] = {t.name: t for t in GENERAL_TOOLS}
```

### 第二步：在 `llm.py` 中注册工具 LLM

在 `app/agents/llm.py` 末尾追加：

```python
from app.agents.tools import GENERAL_TOOLS


@lru_cache(maxsize=1)
def get_general_llm_with_tools() -> BaseChatModel:
    """general_agent 用 LLM：绑定工具，允许调用外部能力。"""
    return ChatDeepSeek(
        model=settings.DEEPSEEK_MODEL,
        api_key=_require_llm_api_key(),
        api_base=_normalize_api_base(settings.DEEPSEEK_BASE_URL),
        temperature=settings.AGENT_FAQ_TEMPERATURE,
        max_retries=2,
    ).bind_tools(GENERAL_TOOLS)
```

保留原有 `get_faq_llm()` 供 faq/pdf 等无工具节点使用。

### 第三步：更新 System Prompt

在 `app/agents/prompts/general.py` 中，将工具说明写入 prompt（与原有「不编造金融数据」策略对齐）：

```python
GENERAL_SYSTEM_PROMPT = """你是一个温暖、友好、乐于助人的 AI 助手。

你的风格：
- 像一个善解人意的朋友在聊天，语气亲切自然，不要冷冰冰
- 适当使用语气词（"呢""哦""哈"）和表情符号让对话更生动
- 回答长度灵活：简单问候可以一句话，常识问题可以多说几句讲清楚
- 如果用户问了一个你不太确定答案的问题，诚实说明，给出建议方向

你可以使用以下工具（仅在需要实时数据或精确计算时调用）：
- get_current_weather：查询城市天气
- calculate：执行数学表达式计算

什么事你都可以聊：
- 闲聊（心情、天气、兴趣爱好、推荐电影餐厅等等）
- 常识与通识知识（科学、历史、文化、生活技巧）
- 帮用户梳理思路、讨论想法
- 回溯之前的对话，帮用户回忆"刚才聊了什么"

底线：
- **绝对不要编造金融数据、股票代码、投资建议等专业金融内容**
- 遇到金融专业问题，友善地告诉用户："这个问题涉及专业知识，建议你切换到文档问答模式哈～"
- 天气类问题优先调用 get_current_weather，数学类问题优先调用 calculate，不要凭空猜测
"""
```

### 第四步：改造 `general_agent`（多轮工具 + 保留流式）

替换 `app/agents/general_agent.py`：

```python
"""General Agent 节点：LLM 对话 + 工具调用（多轮）+ 最终回答流式输出。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_general_llm_with_tools
from app.agents.prompts.general import GENERAL_BUSY_ANSWER, GENERAL_SYSTEM_PROMPT
from app.agents.states import FinAgentState
from app.agents.tools import TOOL_MAP
from app.core.logger import get_logger

logger = get_logger(service="general_agent")

MAX_TOOL_ITERATIONS = 5


async def _run_tool_calls(tool_calls: list) -> list[ToolMessage]:
    """执行一批 tool_calls，未知工具返回错误文本而非静默跳过。"""
    tool_messages: list[ToolMessage] = []
    for tc in tool_calls:
        name = tc.get("name", "")
        tool_fn = TOOL_MAP.get(name)
        if tool_fn is None:
            logger.warning("unknown tool requested: {}", name)
            tool_messages.append(
                ToolMessage(
                    content=f"未知工具：{name}",
                    tool_call_id=tc["id"],
                )
            )
            continue
        try:
            result = await tool_fn.ainvoke(tc.get("args") or {})
        except Exception as e:
            logger.exception("tool {} failed", name)
            result = f"工具 {name} 执行失败：{e}"
        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tc["id"])
        )
    return tool_messages


async def _stream_final_answer(llm, messages, config) -> str:
    """最终回答走 astream，保持 SSE token 流式体验。"""
    parts: list[str] = []
    async for chunk in llm.astream(messages, config=config):
        if chunk.content:
            parts.append(
                chunk.content if isinstance(chunk.content, str) else str(chunk.content)
            )
    return "".join(parts)


async def general_agent(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    history = list(state.get("messages") or [])
    logger.info("general_agent history_messages={}", len(history))

    llm = get_general_llm_with_tools()
    working_messages = [SystemMessage(content=GENERAL_SYSTEM_PROMPT), *history]

    try:
        # 先用 ainvoke 探测是否需要工具（bind_tools 模型需完整 message 才能解析 tool_calls）
        response = await llm.ainvoke(working_messages, config=config)

        if not getattr(response, "tool_calls", None):
            # 无工具：直接用首次 ainvoke 结果（避免 ainvoke + astream 双调用）
            answer = (
                response.content
                if isinstance(response.content, str)
                else str(response.content or "")
            )
            if not answer:
                answer = await _stream_final_answer(llm, working_messages, config)
        else:
            # 有工具：多轮 ainvoke 执行，最后一条回答走 astream
            iterations = 0
            while getattr(response, "tool_calls", None) and iterations < MAX_TOOL_ITERATIONS:
                iterations += 1
                logger.info(
                    "general_agent tool_round={} tools={}",
                    iterations,
                    [tc.get("name") for tc in response.tool_calls],
                )
                tool_messages = await _run_tool_calls(response.tool_calls)
                working_messages = working_messages + [response] + tool_messages
                response = await llm.ainvoke(working_messages, config=config)

            if iterations >= MAX_TOOL_ITERATIONS and getattr(response, "tool_calls", None):
                logger.warning(
                    "general_agent hit MAX_TOOL_ITERATIONS={}", MAX_TOOL_ITERATIONS
                )
                # 去掉工具绑定，强制生成文本
                answer = await _stream_final_answer(
                    llm.bind_tools([]), working_messages + [response], config
                )
            else:
                answer = await _stream_final_answer(
                    llm, working_messages + [response], config
                )

    except Exception:
        logger.exception("general_agent llm invoke failed")
        return {"messages": [AIMessage(content=GENERAL_BUSY_ANSWER)]}

    return {"messages": [AIMessage(content=answer)]}
```

**设计要点**：

| 阶段 | 调用方式 | 原因 |
|:---|:---|:---|
| 首次探测 | `ainvoke` | 解析 `tool_calls` |
| 无工具 | 取 `response.content` | 单次调用，与改造前效率一致 |
| 工具执行（多轮） | `ainvoke` + `ToolMessage` | 链式依赖由 `while` 处理 |
| 工具后最终回答 | `astream` | 保持节点内流式聚合习惯 |

### 第五步：SSE 流式输出（已实现，确认即可）

`app/api/agent.py` 中**已有**过滤逻辑，工具落地后无需再改：

```python
STREAMABLE_NODES = frozenset({"faq_agent", "pdf_agent", "general_agent"})

# 跳过带 tool_calls 的中间 AIMessage（ToolMessage 本身也不是 AIMessage，不会透出）
if getattr(msg, "additional_kwargs", {}).get("tool_calls"):
    continue
if not isinstance(msg, AIMessage):
    continue
```

---

## 多轮工具调用示例

以下流程依赖第四步中的 `while` 循环（`MAX_TOOL_ITERATIONS = 5`）：

```
用户："北京今天多少度？再帮我算一下 (32 - 5) * 2"
  → 第 1 轮: tool_call(get_current_weather, city="北京")
  → 返回 "北京今天晴，22°C ~ 28°C，微风。"
  → 第 2 轮: tool_call(calculate, expression="(32 - 5) * 2")
  → 返回 "54"
  → 第 3 轮: 无 tool_calls → 生成最终回答
  → "北京今天 22°C ~ 28°C 呢～ 另外 (32-5)*2 = 54 哦！"
```

链式依赖（先 A 再 B 再 calculate）同样由 `while` 循环自动处理，无需手写「第二轮」。

---

## 工具设计原则

1. **输入参数简单** — 用 `str` / `int` / `float`，避免嵌套对象，LLM 更易填对参数。
2. **返回值纯文本** — 工具结果由 LLM 组织成自然语言，不要在工具内做 Markdown 排版。
3. **幂等 / 无副作用** — 查询类工具不应改库；写操作需单独鉴权节点（如 `account_agent`）。
4. **错误内部消化** — `try/except` 后返回描述性字符串，不向上抛异常。
5. **安全** — 禁止 `eval()`；外部 API 设 `timeout`（如 `httpx` 10s）；敏感参数写审计日志。
6. **未知工具可观测** — 返回 `"未知工具：xxx"` 而非静默跳过，避免 LLM 幻觉补全。

---

## 可选方案：LangGraph ToolNode

若工具逻辑继续膨胀，可拆成独立节点，减少 Agent 内手写循环：

```python
from langgraph.prebuilt import ToolNode

builder.add_node("tools", ToolNode(GENERAL_TOOLS))
builder.add_conditional_edges(
    "general_agent",
    tools_condition,  # langgraph.prebuilt 提供
    {"tools": "tools", "__end__": "final_answer"},
)
builder.add_edge("tools", "general_agent")
```

当前项目规模下，第四步的单节点 `while` 循环足够；节点数增多时再迁移。

---

## 落地检查清单

- [ ] 新建 `app/agents/tools.py`，`pytest` 覆盖 `safe_calculate` 与 `@tool` 装饰器
- [ ] `llm.py` 新增 `get_general_llm_with_tools()`
- [ ] 更新 `GENERAL_SYSTEM_PROMPT` 说明可用工具
- [ ] 改造 `app/agents/general_agent.py`（保留 `astream` 最终回答）
- [ ] 确认 `app/api/agent.py` SSE 过滤仍生效
- [ ] 手动测试：`/agent/query` 问天气 + 计算复合问题
- [ ] 若新增金融类工具：评估是否改路由至 `plan` / `account_agent` 并经过 `risk_triage`

---

## 参考文件

| 文件 | 作用 |
|:---|:---|
| `app/agents/graph.py` | 主图编排 |
| `app/agents/supervisor.py` | 结构化路由 |
| `app/agents/risk_triage.py` | 风险评估（仅 plan 路径） |
| `app/agents/llm.py` | LLM 工厂 |
| `app/agents/general_agent.py` | 工具挂载点（general 路径） |
| `app/api/agent.py` | SSE 流式输出 |
