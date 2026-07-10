# financial_query_agent DeepAgent 化重构实施方案

> 目标：将 `fin-agent-platform/app/agents/components/finance_agent/financial_query_agent` 改造成更接近 AssistGen 的小型多工作流 Agent，同时保持职责单一、路径清晰、可逐步迁移。

## 一、设计结论

本方案采用以下核心设计：

1. `financial_query_agent/planner` 只负责在两类工作流之间做选择：
   - `predefined_workflow`
   - `text_to_sql_workflow`
2. `predefined_workflow` 只处理白名单模板查询，并且要求：
   - 只有在确定命中白名单且字段充足时，planner 才允许路由到这里
   - 一旦进入 `predefined_workflow`，不再做信息不足判断
   - 一旦进入 `predefined_workflow`，不再 fallback 到 `text_to_sql_workflow`
3. `text_to_sql_workflow` 负责所有非白名单复杂查询，并在内部承担：
   - 查询信息是否足够的判断
   - clarification
   - SQL 生成 / 校验 / 修正 / 执行
4. `clarification` 不再是独立总分支，而是下沉到 `text_to_sql_workflow` 内部能力。

这个设计的本质是：

- `planner` 负责**严格准入**
- `predefined_workflow` 负责**纯执行**
- `text_to_sql_workflow` 负责**复杂查询闭环**

---

## 二、最终目标流程

目标主图：

```text
extract_intent
  -> planner
      -> predefined_workflow
      -> text_to_sql_workflow
```

其中：

```text
predefined_workflow
  -> build_sql_from_whitelist
  -> execute_sql
  -> format_answer
```

```text
text_to_sql_workflow
  -> check_query_readiness
  -> clarification
  -> generate_sql
  -> validate_sql
  -> correct_sql
  -> execute_sql
  -> format_answer
```

---

## 三、职责边界

### 3.1 planner

`financial_query_agent/planner` 只负责：

- 基于用户问题描述与结构化意图，判断是否符合白名单模板条件
- 当且仅当满足白名单准入条件时，路由到 `predefined_workflow`
- 其余全部路由到 `text_to_sql_workflow`

`planner` 不负责：

- 追问补充信息
- 选择 SQL 细节
- 生成 SQL
- 在 `predefined` 和 `text_to_sql` 之间来回 fallback

### 3.2 predefined_workflow

`predefined_workflow` 只负责：

- 根据白名单模板生成 SQL
- 填充模板参数
- 执行模板 SQL
- 格式化结果

`predefined_workflow` 不负责：

- 判断用户信息是否足够
- 对模板外语义做兜底
- fallback 到复杂 SQL

它的前提是：

> 只要进入 `predefined_workflow`，就默认已经满足模板命中与字段完备条件。

### 3.3 text_to_sql_workflow

`text_to_sql_workflow` 负责：

- 判断是否具备足够查询信息
- 不足时输出 clarification
- 复杂 SQL 的完整执行闭环

它是默认复杂路径，也是非白名单问题的统一承接方。

---

## 四、为什么这样设计

### 4.1 优点

1. `predefined` 变成真正纯执行器  
   不再承担任何路由、补问、兜底职责。

2. agent 边界最清楚  
   - `planner` 决策
   - `predefined_workflow` 跑白名单
   - `text_to_sql_workflow` 跑复杂查询

3. 流程可预测  
   一旦进入白名单路径，就不允许再回退，避免工作流反复分叉。

4. 更符合单一职责  
   白名单模板场景和复杂 SQL 场景彻底分开。

### 4.2 代价

1. `planner` 必须足够保守  
   不能乐观路由到 `predefined_workflow`。

2. 更多边界问题会被送到 `text_to_sql_workflow`  
   命中白名单的覆盖率可能下降，但换来的是结构稳定。

3. `text_to_sql_workflow` 必须足够强  
   因为所有非白名单问题都会集中到这里。

---

## 五、白名单准入原则

`planner` 只有在以下条件同时满足时，才能选择 `predefined_workflow`：

1. 问题语义命中白名单模板能力范围
2. 模板所需字段全部齐备
3. 不存在明显歧义
4. 不包含复杂语义

### 5.1 可进入 predefined 的典型场景

- 单公司 + 单指标 + 单年份查数
- 单公司 + 单指标 + 最新值查询
- 标准公司对比
- 标准年份趋势

### 5.2 直接进入 text_to_sql 的场景

只要出现以下任一情况，就直接走 `text_to_sql_workflow`：

- 排名
- 占比 / 比例
- 同比 / 环比 / CAGR
- 条件筛选
- 多层计算
- 聚合
- 排序
- 复杂比较口径
- 模板所需字段不完整
- 存在实体歧义

---

## 六、clarification 为什么放进 text_to_sql_workflow

本方案不把 `clarification` 放在 planner 之前，也不让它成为全局统一分支。

原因：

1. 白名单路径要求更严格  
   既然 `planner` 已经保证“进 predefined 就成功”，那白名单路径内部不应再补问。

2. 非白名单路径才需要弹性判断  
   `text_to_sql_workflow` 面对的问题更复杂，是否信息足够需要按复杂 SQL 的标准判断。

3. clarification 应成为复杂查询工作流内部的一部分  
   而不是主图上的通用岔路。

因此：

- `planner` 只做 `predefined / text_to_sql` 分流
- `clarification` 只保留在 `text_to_sql_workflow`

---

## 七、建议目录结构

```text
financial_query_agent/
├── __init__.py
├── common.py
├── state.py
│
├── extract_intent/
│   ├── __init__.py
│   ├── node.py
│   ├── prompts.py
│   ├── models.py
│   └── normalizer.py
│
├── planner/
│   ├── __init__.py
│   ├── node.py
│   ├── prompts.py
│   └── models.py
│
├── predefined_workflow/
│   ├── __init__.py
│   ├── node.py
│   ├── prompts.py            # 如仍需要 LLM 选 template_id，可保留；否则可删
│   └── utils.py              # build_sql / fill_params / execute / format
│
├── text_to_sql/
│   ├── __init__.py
│   ├── node.py
│   ├── state.py
│   ├── generation/
│   ├── validation/
│   ├── correction/
│   ├── execution/
│   └── clarification/
│
├── services/
│   ├── __init__.py
│   ├── entity_resolver.py
│   ├── query_router.py
│   ├── sql_templates.py
│   ├── sql_executor.py
│   ├── fact_service.py
│   └── schemas.py
│
└── retrievers/
    └── __init__.py
```

---

## 八、建议状态字段

建议在 `financial_query_agent/state.py` 中保留或新增以下字段：

### 8.1 planner 输出

- `financial_query_plan_route`
  - 只允许：`predefined` / `text_to_sql`
- `financial_query_plan_reason`
- `financial_query_template_id`
  - 若 planner 已明确模板，可直接给出

### 8.2 predefined_workflow 输出

- `financial_query_sql`
- `financial_query_sql_params`

### 8.3 text_to_sql_workflow 输出

- `financial_query_validated_sql`
- `financial_query_validation_error`
- `financial_query_validation_errors`
- `financial_query_sql_attempts`
- `financial_query_next_action_sql`
- `financial_query_schema_prompt`
- `financial_query_fewshot_examples`

---

## 九、具体重构步骤

### Phase 1：收紧 planner

目标：

- `planner` 不再输出 `clarify`
- `planner` 不再输出 `template`
- `planner` 只输出：
  - `predefined`
  - `text_to_sql`

要做的事：

1. 修改 `planner/prompts.py`
2. 修改 `planner/models.py`
3. 修改 `planner/node.py`
4. 明确写入白名单准入条件

### Phase 2：合并模板路径

目标：

- 将 `template_selection/` 与 `predefined_sql/` 收编成 `predefined_workflow/`

要做的事：

1. 创建 `predefined_workflow/`
2. 将模板匹配、字段填充、SQL 构建、执行、结果整理收拢到该目录
3. 删除原本独立的二次路由逻辑

### Phase 3：将 clarification 下沉到 text_to_sql_workflow

目标：

- 主图不再有独立 `clarification` 分支
- clarification 成为 `text_to_sql_workflow` 内部节点

要做的事：

1. 将 `clarification` 逻辑迁入 `text_to_sql/clarification/`
2. 在 `text_to_sql` 子图内新增信息充足性检查节点
3. 信息不足时直接输出补问答案

### Phase 4：清理旧目录

在完成迁移后，删除以下不再需要的目录或文件：

- `template_selection/`
- `predefined_sql/`
- 主图级 `clarification/`（若已完全迁入 text_to_sql）

---

## 十、删除与保留建议

### 10.1 建议保留

- `extract_intent/`
- `services/`
- `text_to_sql/`
- `planner/`

### 10.2 建议重构后删除

以下前提是新 workflow 已稳定接管职责：

- `template_selection/`
- `predefined_sql/`
- `financial_query_agent` 主图下的独立 `clarification/`

---

## 十一、需要特别防止的问题

### 11.1 planner 误判进入 predefined

这是本方案最大风险。  
一旦 planner 放松判断标准，就会导致：

- 进入 `predefined_workflow`
- 但模板其实不能稳定执行

由于本方案明确要求 `predefined` 不再补问、不再 fallback，所以：

> planner 必须宁可保守，不可乐观。

### 11.2 predefined_workflow 再次长成“大节点”

要防止把原来的复杂逻辑换个目录名继续堆回去。  
`predefined_workflow` 仍应保持纯执行器属性。

### 11.3 clarification 粒度过粗

虽然 clarification 下沉到 `text_to_sql_workflow`，但补问内容不能只看“缺公司/缺年份/缺指标”。

还应考虑：

- 统计口径不明确
- 比较对象不明确
- 时间范围不明确
- 计算目标不明确

---

## 十二、最终推荐方案

推荐正式落地为：

```text
extract_intent
  -> planner
      -> predefined_workflow
      -> text_to_sql_workflow
```

其中：

- `planner`
  - 严格白名单准入
  - 只分 `predefined` / `text_to_sql`

- `predefined_workflow`
  - 进入即成功
  - 不补问
  - 不 fallback

- `text_to_sql_workflow`
  - 承担所有复杂查询
  - 内部处理 clarification / generation / validation / correction / execution

这是当前最符合以下目标的方案：

- Agent 单一职责
- 进行解耦
- 结构清晰
- 后续易扩展

---

## 十三、实施优先级

1. 先修改 `planner`，收紧分流职责
2. 再合并 `template_selection + predefined_sql`
3. 再把 `clarification` 下沉到 `text_to_sql_workflow`
4. 最后删除旧目录与兼容代码

---

## 十四、对应当前代码库的直接改造点

建议优先修改以下路径：

- `app/agents/components/finance_agent/financial_query_agent/__init__.py`
- `app/agents/components/finance_agent/financial_query_agent/planner/`
- `app/agents/components/finance_agent/financial_query_agent/template_selection/`
- `app/agents/components/finance_agent/financial_query_agent/predefined_sql/`
- `app/agents/components/finance_agent/financial_query_agent/text_to_sql/`
- `app/agents/components/finance_agent/financial_query_agent/clarification/`
- `app/agents/components/finance_agent/financial_query_agent/state.py`

---

## 十五、文档结论

这套方案不是追求“更多节点”，而是追求：

- 让 `planner` 只做准入与分流
- 让 `predefined_workflow` 成为纯白名单执行器
- 让 `text_to_sql_workflow` 成为复杂查询的统一闭环

这是当前 `financial_query_agent` 最适合的 DeepAgent 化方向。
