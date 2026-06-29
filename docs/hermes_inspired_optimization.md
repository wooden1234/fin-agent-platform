# Fin-Agent-Platform 优化建议

> 基于 `hermes-agent` 架构分析，整理给 `fin-agent-platform` 的平台化优化建议。

---

## 1. 文档目标

当前 `fin-agent-platform` 已经具备一个清晰的业务 Agent 主图：

- `guardrails -> context_compressor -> supervisor -> risk_triage -> [general_agent | plan_agent] -> final_answer`
- 主图编译入口位于 `app/agents/graph.py`
- Web 流式入口位于 `app/api/agent.py`

这套设计适合快速交付金融问答场景，但从长期看，系统仍偏向“单 Web 入口的 LangGraph 应用”，距离“可扩展、可复用、可多入口接入的 Agent 平台”还有一段距离。

本文档目标是：

1. 总结 `hermes-agent` 中真正值得借鉴的架构思想
2. 结合 `fin-agent-platform` 当前代码结构给出落地方向
3. 按优先级整理一条可执行的演进路径

---

## 2. 当前架构定位

### 2.1 现状优点

- 主图分层清楚，节点职责相对明确
- 已有 `guardrails`、`risk_triage`、`context_compressor`，说明平台已经开始从“单纯问答”向“可控 Agent”演进
- Checkpoint 已经接入，可支持多轮对话恢复
- `retrieval / services / api / agents` 分层基本合理

### 2.2 当前短板

- Agent 运行时和 HTTP 入口耦合较紧，缺少独立的 runtime 抽象
- 会话管理较薄，当前主要依赖 `thread_id = conversation_id`
- 工具层、能力层还没有统一注册中心
- 缺少后台任务与主动执行能力
- 缺少多入口抽象，未来接企业微信/飞书/工作台会重复造轮子
- 缺少统一的可观测性、恢复策略、长生命周期治理

---

## 3. Hermes 中最值得借鉴的四层结构

`hermes-agent` 的核心价值不在于“功能很多”，而在于架构分层清晰。可以概括为四层：

### 3.1 Agent Runtime 内核层

核心职责：

- 统一处理一次对话的完整生命周期
- 包含模型调用、工具调度、上下文压缩、记忆注入、重试、收尾
- 对上层入口透明

对应 Hermes 代表模块：

- `run_agent.py`
- `agent/agent_init.py`
- `agent/conversation_loop.py`

对 `fin-agent-platform` 的启发：

- 把 LangGraph 主图视为“业务决策图”
- 再向外抽一层“Agent Runtime”，负责统一执行、状态恢复、事件流、日志与错误语义

### 3.2 能力注册层

核心职责：

- 工具注册
- toolset 白名单/黑名单
- 插件发现
- skills / memory provider 等能力注入

对应 Hermes 代表模块：

- `model_tools.py`
- `toolsets.py`
- `tools/`
- `plugins/`

对 `fin-agent-platform` 的启发：

- 未来不要让工具能力散落在各个 agent 节点内部
- 应建立统一的 tool registry / capability registry
- 按场景、租户、渠道控制能力暴露范围

### 3.3 多入口通道层

核心职责：

- CLI
- Gateway
- ACP/编辑器协议
- 不同入口复用同一运行时

对应 Hermes 代表模块：

- `hermes_cli/`
- `gateway/`
- `acp_adapter/`

对 `fin-agent-platform` 的启发：

- Web API 只是一个 transport
- 未来接客服工作台、企业 IM、内部运营后台时，应复用同一 Agent 内核

### 3.4 平台治理层

核心职责：

- Session 生命周期
- Cron 主动任务
- 长连接与故障恢复
- 测试矩阵
- 部署与环境兼容

对应 Hermes 代表模块：

- `gateway/session.py` + `gateway/run.py`
- `cron/`
- `tests/`
- `docker/`, `nix/`

对 `fin-agent-platform` 的启发：

- 需要从“能回答”升级到“能稳定运行”
- 金融场景尤其需要恢复策略、审计链路和风险隔离

---

## 4. 哪些思路最适合迁移到 Fin-Agent-Platform

下面按“收益高、迁移成本相对可控”的顺序排列。

### 4.1 建立统一 Session Manager

#### 为什么值得做

当前 `conversation_id -> thread_id` 的方式足够简单，但还不够支撑下面这些能力：

- 多终端继续同一会话
- 人工中断后恢复
- 后台任务回写同一会话
- 会话自动过期、归档、恢复
- 多租户/多渠道隔离

#### 建议引入

- `SessionKey`：定义会话逻辑身份
- `SessionRuntime`：记录一次运行实例
- `SessionPolicy`：过期、恢复、是否允许后台任务写回
- `SessionStore`：统一管理会话元数据与状态

#### 落地方式

建议新增目录：

```text
app/runtime/
  sessions.py
  session_store.py
  session_policy.py
```

### 4.2 抽象 Agent Runtime 层

#### 为什么值得做

当前 `app/api/agent.py` 直接驱动 `graph.astream()`，这会导致：

- Web 层承担太多运行细节
- 未来接别的入口时重复写流式桥接代码
- 错误语义、状态事件、日志事件不统一

#### 建议引入

新增一个统一执行入口，例如：

```python
AgentRuntime.run_turn(...)
AgentRuntime.stream_turn(...)
```

它内部负责：

- 构造线程配置
- 执行主图
- 标准化事件流
- 汇总 citations
- 统一异常分类
- 写入 conversation / audit / metrics

#### 落地方式

建议新增目录：

```text
app/runtime/
  runtime.py
  events.py
  errors.py
```

然后让：

- `app/api/agent.py`
- 后续后台任务 worker
- 未来 IM channel adapter

都调用同一个 runtime。

### 4.3 建立 Tool / Capability Registry

#### 为什么值得做

金融 Agent 后面一定会扩展更多能力，例如：

- 结构化数据库查询
- 财务指标提取
- 研报/PDF 检索
- 行情/市场数据
- FAQ
- 风险检查
- 审批流 / 人工转接

如果这些能力继续散落在各 agent 节点里，后面会越来越难控制。

#### 建议引入

- `CapabilityRegistry`
- `ToolDefinition`
- `ToolPolicy`
- `ChannelCapabilityProfile`

示意：

```text
app/capabilities/
  registry.py
  definitions.py
  policies.py
  providers/
```

#### 推荐第一步

先不要做通用工具调用平台，先做“金融能力注册表”，把现在已有能力抽象出来：

- `faq_retrieval`
- `pdf_retrieval`
- `financial_fact_lookup`
- `db_query`
- `general_reasoning`

### 4.4 强化 Guardrails 与 Risk Policy

#### 为什么值得做

这是金融平台和通用 Agent 最大的差异点之一。

当前已经有：

- `guardrails`
- `risk_triage`

这是一个很好的起点，但建议继续往“策略化”演进，而不是继续堆 prompt。

#### 建议方向

- Prompt 注入检测
- 金融越权问题拦截
- 高风险建议降级
- 输出声明与合规提示
- 工具级权限控制
- 用户身份与产品线绑定

#### 建议拆分

```text
app/policies/
  input_policy.py
  risk_policy.py
  tool_policy.py
  output_policy.py
```

把“节点”与“策略”分开：

- LangGraph 节点负责调用策略
- 策略文件负责真正规则

### 4.5 引入后台任务 / 主动任务能力

#### 为什么值得做

很多金融场景不是被动问答，而是：

- 定时报送日报
- 夜间巡检知识库
- 风险事件提醒
- 失败任务重跑
- 批量生成客户摘要

Hermes 的 `cron/` 思路很适合迁移，但不需要一上来做成全功能调度系统。

#### 推荐最小版本

第一阶段只做：

- 后台任务模型
- 任务执行器
- 任务状态与重试

建议目录：

```text
app/jobs/
  models.py
  scheduler.py
  runner.py
```

如果后面需要更成熟的调度，再接 Celery / RQ / APScheduler。

### 4.6 统一事件流与可观测性

#### 为什么值得做

现在的 SSE 输出还是偏“页面可用”，还不是“平台可观测”。

建议把事件分成标准类型：

- `token`
- `node_start`
- `node_end`
- `tool_start`
- `tool_end`
- `warning`
- `citation`
- `done`
- `error`

这样可以同时服务：

- 前端实时展示
- 后台审计
- 链路追踪
- 问题复盘

#### 建议目录

```text
app/observability/
  events.py
  tracing.py
  metrics.py
  audit.py
```

### 4.7 逐步支持多入口

#### 为什么值得做

短期你们可能只需要 Web，但中期很可能会出现：

- 企业微信
- 飞书
- 客服工作台
- 内部运营后台

如果现在 API 层不抽象，后续每接一个入口就会复制一套“请求转 Agent”的逻辑。

#### 推荐做法

不要先做复杂 gateway，而是先做一个 transport 抽象：

```text
app/transports/
  base.py
  web.py
  worker.py
```

Web 入口先走 `web.py`，未来新入口继续接在同一 runtime 之上。

---

## 5. 哪些 Hermes 思路不建议直接照搬

### 5.1 不建议立刻照搬大而全的 skills 生态

Hermes 的 `skills/` 和 `optional-skills/` 很强，但对当前阶段的 `fin-agent-platform` 来说太重。

更适合的做法是做“金融内部 SOP 库”，例如：

- 基金问答模板
- 年报分析流程
- 风险提示模板
- 财报指标口径说明

### 5.2 不建议立即铺开多平台 Gateway

Hermes 的 gateway 非常成熟，但它的复杂度也很高。

对现在的 `fin-agent-platform`，更合理的节奏是：

1. 先抽象 runtime
2. 再抽象 transport
3. 最后再接新渠道

### 5.3 不建议把所有能力都做成通用插件

金融系统里很多能力高度业务化。

建议先做“内部 capability registry”，而不是一步到位做开放插件平台。

---

## 6. 推荐目标架构

建议将现有结构逐步演进为：

```text
app/
  agents/            # LangGraph 业务决策图
  api/               # Web API
  runtime/           # Agent runtime、session、事件流
  capabilities/      # 金融能力注册中心
  policies/          # 输入/风险/输出/工具策略
  transports/        # Web / worker / future IM adapters
  jobs/              # 后台任务与主动执行
  observability/     # tracing / audit / metrics / event schema
  retrieval/         # 检索能力
  services/          # 业务服务
  core/              # config / db / logger / middleware
```

分层关系：

1. `api/transports` 负责接入
2. `runtime` 负责一次 turn 的统一执行
3. `agents` 负责决策图编排
4. `capabilities/retrieval/services` 提供能力
5. `policies/observability` 提供治理和可观测性

---

## 7. 分阶段落地建议

### Phase 1：低风险重构

目标：不改变现有产品能力，只把结构拉直。

- 抽出 `app/runtime/runtime.py`
- 把 `app/api/agent.py` 中的图执行逻辑迁到 runtime
- 标准化 SSE 事件模型
- 抽出统一错误类型

预期收益：

- 降低 API 层复杂度
- 为后续多入口与后台任务铺路

### Phase 2：会话与策略增强

目标：提高稳定性和金融场景可控性。

- 引入 `SessionManager`
- 抽出 `policies/`
- 强化 guardrails / risk policy
- 增加审计日志与节点事件

预期收益：

- 更适合生产环境
- 更容易做合规审计与问题追踪

### Phase 3：能力中心化

目标：让新增能力不再继续散落。

- 建立 `capabilities/registry.py`
- 把 FAQ/PDF/financial_fact/db_query 抽象成注册能力
- 在 supervisor / plan_agent 中按能力选择，而不是按硬编码节点堆叠

预期收益：

- 降低后续扩展成本
- 更容易做租户级、渠道级能力开关

### Phase 4：主动执行与多入口

目标：让平台从“被动问答”升级到“可持续运行”。

- 引入 `jobs/`
- 支持后台运行与重试
- 增加 worker transport
- 后续接 IM / 工作台

预期收益：

- 能覆盖更多真实金融业务流程

---

## 8. 优先级结论

如果只选最值得先做的三件事，我建议是：

1. 抽 `runtime` 层，把 Agent 执行从 `api` 中分离出来
2. 做 `session + policy` 两个基础设施模块
3. 做 `capability registry`，为后续金融能力扩展建立统一入口

这三件事做完以后，`fin-agent-platform` 仍然保持现有 LangGraph 优势，但会开始从“一个项目”向“一个平台”过渡。

---

## 9. 一句话总结

`hermes-agent` 最值得借鉴的不是“功能数量”，而是“运行时内核、能力注册、多入口接入、平台治理”这四层分离。

`fin-agent-platform` 下一阶段最应该做的，也不是继续堆节点，而是把这四层里最基础的三块先补起来：

- runtime
- session/policy
- capability registry

这样后续无论是继续做金融多 Agent、RAG、数据库问答、定时任务，还是接企业渠道，都会顺很多。
