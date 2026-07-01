# Agent Rules

本文档只记录高优先级、稳定规则。不要把它扩展成项目百科；临时方案、详细设计和操作手册放到 `docs/`。

## 环境与验证

- 默认使用 Conda 环境 `agent`。
- 优先运行与改动最相关的最小测试集，跨模块改动再跑全量。
- 常用命令：

```bash
conda run -n agent python -m pytest tests/test_db_agent.py tests/test_financial_fact_service.py
conda run -n agent python -m pytest
conda run -n agent python -m py_compile <changed-python-files>
conda run -n agent python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 架构边界

- `app/agents` 只放图编排、路由、Agent 节点、Agent prompt，以及未来 Agent 可直接调用的外部工具。
- `app/services/financial` 放金融查询领域逻辑，例如实体解析、模板路由、模糊事实检索、text-to-SQL。
- 天气、联网搜索、计算器属于 Agent 外部工具层；按需放到未来 `app/agents/tools/`。
- 模板查询、模糊事实检索、text-to-SQL 是金融查询内部策略，不要注册成 Agent 外部工具。
- `plan_agent` 只路由到 agent / subgraph，不直接处理 service executor 细节。

## 当前命名约定

- 新代码优先使用 `financial_query_agent` 和任务类型 `financial_query`。
- `db_agent` 和任务类型 `db` 只作为历史兼容保留，不要在新代码里继续扩散。
- 新代码优先从 `app.services.financial` 导入金融查询对象。
- `app.services.financial_fact_service`、`app.services.financial_entity_resolver` 是历史兼容入口。

## 修改原则

- 优先小 diff，不做无关重构。
- 不要回滚用户已有改动；遇到脏工作区先确认变更来源和影响。
- 行为变化必须同步更新或新增测试。
- 新增或修改代码注释、docstring 使用简体中文。
- 不要把 `.env`、token、密钥、数据库密码等敏感信息写入代码、日志或回复。
- 不新增遥测、埋点或额外网络调用，除非任务明确要求。

## 文档位置

- 稳定规则写在本文件。
- 架构设计、迁移计划、操作步骤写到 `docs/`。
- 重要边界参考：
  - `docs/平台级Harness与工具边界设计.md`
  - `docs/企业级财务事实查询与模板路由方案.md`
  - `docs/TOOL_GUIDE.md`
