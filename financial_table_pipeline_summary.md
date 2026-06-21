# 财务表格结构化入库优化总结

## 背景

项目需要从上市公司年报 PDF 中抽取财务数据，用于后续 Agent 精确查数和财务问答。

原始流程是：

```text
PDF 解析
  -> 文本/表格切块
  -> 导出 annual_financial_tables
  -> 拆成 annual_financial_facts
  -> 入库
```

在早期实现中，所有财务表格都被尽量拆成统一的长表：

```text
公司 + 年报 + 指标 + 期间 + 数值
```

这个设计本身适合做精确查询，但实际入库后发现数据质量不稳定。

## 遇到的问题

### 1. 表格切块破坏了表头

部分财务表跨页或过长，被按字符切开后，后续 chunk 只剩数据行，没有表头。

例如原始表应该是：

```text
项目 | 期末余额 | 期初余额
货币资金 | 303,511,993 | 264,306,515
```

但切块后可能变成：

```text
货币资金 | 303,511,993 | 264,306,515
```

解析脚本不知道第二列、第三列分别是什么，只能生成：

```text
value_1
value_2
```

这会导致结构化表里出现大量不可信的 `period_label`。

### 2. 标准期间表和复杂附注表混在一起

不是所有财务表都适合拆成 facts。

标准期间表适合拆成结构化数据，例如：

```text
项目 | 2024年 | 2023年
营业收入 | 50,425.72 | 50,569.44
```

复杂附注表更适合保留原文做 RAG，例如：

```text
项目 | 金额 | 原因 | 占比
政府补助 | 1,000 | 与收益相关 | 20%
```

如果强行把复杂附注表拆成 `metric_name + period_label + value`，会把 `金额`、`合计`、`毛利率`、`累计利得` 等字段误当成期间列，导致 facts 表变脏。

### 3. 查询结果容易混杂

同一个指标可能来自不同表：

```text
年度主要会计数据
利润表变动分析表
分季度表
合并资产负债表
母公司资产负债表
```

例如只用：

```sql
WHERE metric_name = '营业收入'
```

会同时查到年度数、本期数、上年同期数、季度数、同比变动比例等。

所以后续查询必须结合：

```text
period_type
period_year
section
table_kind
```

## 优化方案

### 1. 在切块阶段区分财务表

普通正文继续按长度切块。

财务表不再按字符硬切，而是按 Markdown 表格行切分，并且每个切块都保留表头。

优化后：

```text
chunk 1:
项目 | 期末余额 | 期初余额
货币资金 | ...

chunk 2:
项目 | 期末余额 | 期初余额
存货 | ...
固定资产 | ...
```

这样后续解析 facts 时能拿到真实列名，减少 `value_1/value_2`。

相关实现：

```text
app/retrieval/ingest_pdf.py
```

新增元数据：

```text
table_split_strategy = financial_row_aware
table_header_inherited = true/false
table_part_index
table_part_count
```

### 2. 处理跨页续表

如果当前财务表块没有表头，但它和上一张财务表属于同一个 section，就尝试继承上一张表的表头。

例如：

```text
上一块：
项目 | 期末余额 | 期初余额
货币资金 | 100 | 80

下一块：
存货 | 50 | 40
```

会补成：

```text
项目 | 期末余额 | 期初余额
存货 | 50 | 40
```

### 3. 增加表格分流

在导出 `annual_financial_tables` 时新增字段：

```text
fact_parse_mode
```

取值：

```text
periodic_fact  标准期间表，可以拆 facts
note_table     复杂附注表，只保留原表做 RAG
unknown        暂不确定
```

判断逻辑：

如果表头包含年份、期间、期初期末、本期上期、同比变动、季度等信息，则认为是标准期间表。

例如：

```text
2024年
2023年
本期数
上年同期数
期末余额
期初余额
变动比例(%)
第一季度
第二季度
```

否则归为复杂附注表，保留在表格文本层，不拆 facts。

相关实现：

```text
scripts/export_annual_financial_tables.py
```

### 4. facts 构建只解析标准期间表

`scripts/build_annual_financial_facts.py` 默认只处理：

```text
fact_parse_mode = periodic_fact
```

复杂附注表不再进入 `annual_financial_facts`，避免污染结构化查询表。

如果需要调试，也保留了参数：

```bash
python scripts/build_annual_financial_facts.py --parse-all-tables
```

## 当前数据处理策略

现在形成了两层数据：

### annual_financial_facts

用于精确查数。

适合问题：

```text
龙芯中科 2024 年营业收入是多少？
宁德时代 2024 年期末货币资金是多少？
腾讯 2025 年经营盈利是多少？
688047 2024 年营业成本同比变化多少？
```

### annual_financial_tables / PDF RAG

用于复杂表格解释和明细问答。

适合问题：

```text
非经常性损益由哪些项目构成？
政府补助明细是什么？
分产品收入和毛利率是多少？
金融资产分类情况如何？
```

## 查询注意事项

facts 表是一张长表，同一个指标可能在多个表里出现。

查询年度指标时，建议限定：

```sql
WHERE period_type = 'annual'
  AND period_year = fiscal_year
```

查询资产负债表项目时，建议限定 section：

```sql
WHERE section LIKE '%合并资产负债表%'
```

建议给 Agent 使用一层 clean view：

```sql
CREATE OR REPLACE VIEW annual_financial_facts_clean AS
SELECT *
FROM annual_financial_facts
WHERE period_label IS NOT NULL
  AND period_label <> ''
  AND period_label NOT LIKE 'value_%'
  AND period_type <> 'unknown';
```

## 效果

优化前，结构化 facts 中混有大量：

```text
value_1
value_2
金额
合计
累计利得
占利润总额比例
```

这些字段不适合作为期间列。

优化后，流程会先把表格分成：

```text
periodic_fact -> 拆 facts
note_table    -> 保留原表做 RAG
```

这样做的收益是：

```text
1. 减少 value_1/value_2 这类无语义列名
2. 避免复杂附注表污染结构化 facts
3. SQL 查数更稳定
4. RAG 仍然保留复杂表格上下文
5. Agent 可以根据问题类型选择 SQL 或 RAG
```

## 面试表达

可以这样总结：

```text
我没有简单地把 PDF 表格全部拆成一张事实表，因为年报里的表格形态差异很大。

我把表格分成两类：
一类是标准期间表，表头是年份、本期数、期末余额等，适合拆成结构化 facts，用 SQL 精确查数；
另一类是复杂附注表，表头是金额、原因、合计、毛利率等说明性字段，更适合保留原表走 RAG。

同时我在切块阶段对财务表做了特殊处理：按表格行切分、重复表头，并对跨页续表继承表头，避免后续解析时出现 value_1/value_2 这种无语义字段。

最终形成 SQL facts + 表格 RAG 的双通道：精确数值问题走数据库，明细解释问题走 RAG。
```

## 后续评测方向

### 数据质量评测

```sql
SELECT
  COUNT(*) FILTER (WHERE period_type = 'unknown') AS unknown_count,
  COUNT(*) FILTER (WHERE period_label LIKE 'value_%') AS value_label_count,
  COUNT(*) AS total_count
FROM annual_financial_facts;
```

### SQL 查数评测

准备标准问答：

```text
龙芯中科 2024 年营业收入是多少？
宁德时代 2024 年期末货币资金是多少？
腾讯 2025 年经营盈利是多少？
```

评测：

```text
数值是否正确
单位是否正确
年份是否正确
是否选对合并/母公司口径
```

### RAG 表格评测

准备复杂表问题：

```text
非经常性损益主要有哪些项目？
分产品收入和毛利率是多少？
政府补助明细是什么？
```

评测：

```text
是否召回正确表格
是否引用正确来源
是否遗漏关键项目
是否把说明性表格误当成年度 facts
```
