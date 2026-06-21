# 企业级 RAG 知识库

可以。企业级 RAG 知识库不要理解成“把文档切块塞进向量库”，更应该当成一个**数据治理 + 检索系统 + Agent 工具层**来做。

我查了一下官方文档，主流云厂商思路基本一致：RAG 流程是数据接入、转换切块、Embedding、索引、检索、生成；同时要处理权限、引用、更新、结构化数据查询和重排序等问题。Google RAG Engine 把流程明确拆成 ingestion、transformation、embedding、indexing、retrieval、generation；Azure 强调 RAG 质量取决于内容准备、chunking、hybrid search、semantic ranking；AWS Bedrock Knowledge Bases 也强调数据源同步、引用、结构化数据库查询和 reranking；OpenAI Retrieval/Vector Store 也支持语义检索、metadata filtering、ranking tuning。

**企业级处理思路**

不要一套规则处理所有文档。应该先做“知识分层”：

```text
原始文件层：PDF、Word、Excel、网页、数据库原文
清洗文本层：去噪、OCR、版面修复、表格恢复
结构化层：财务指标、合同字段、产品参数、FAQ 等
检索索引层：向量索引 + 关键词索引 + 元数据索引
工具层：SQL tool、RAG tool、文件引用 tool
Agent 层：根据问题选择查数据库还是查文档
```

**核心原则**

企业知识库要先做数据目录，而不是直接 embedding：

```text
文档属于哪个业务域？
谁是权威来源？
更新时间是什么？
哪些用户能看？
是制度、合同、财报、FAQ、邮件还是表格？
适合结构化入库，还是只适合 RAG？
```

每个 chunk 至少要带这些元数据：

```text
doc_id
title
source
business_domain
doc_type
authority_level
effective_date
version
owner
permission_scope
page_num
section
chunk_type
```

**针对不同数据类型分流**

像你现在做财报，其实就是一个典型企业做法：

```text
标准期间财务表 -> 结构化 facts 表 -> SQL 精确查数
复杂附注表 -> 保留表格文本 -> RAG 解释明细
普通正文 -> 切块向量化 -> RAG
图片/扫描件 -> OCR/多模态解析 -> 再入库
数据库数据 -> 不必向量化，直接 SQL tool
```

也就是说，企业里不能什么都丢向量库。**能结构化的就结构化，不能结构化的才走 RAG。**

**检索层建议**

企业 RAG 一般不要只用向量检索，建议：

```text
关键词检索：适合精确术语、编号、法规条款、股票代码
向量检索：适合语义相近问题
元数据过滤：按权限、时间、部门、文档类型过滤
rerank：对召回结果重排序
SQL 查询：处理精确数值和统计
```

Azure 官方也建议 hybrid search，把关键词和向量结合起来提高召回，并使用 semantic ranking 优化相关性。

**权限和安全**

企业级 RAG 最大区别是权限。检索时必须先做 security trimming：

```text
用户是谁？
属于哪个部门？
能看哪些文档？
是否能看财务/人事/合同/客户数据？
```

不能先检索再让模型判断能不能说。权限过滤必须发生在检索阶段。

**回答层要求**

企业回答不能只“看起来合理”，要：

```text
必须引用来源
能返回页码/章节/表格
没有证据就说无法确认
结构化数值要优先查数据库
多来源冲突时提示冲突
```

AWS 文档也明确提到 citations，方便用户回查原始数据源。

**评测体系**

企业知识库上线前要做评测集，不是只人工试几个问题。

至少分三类：

```text
检索评测：正确文档是否在 top-k
回答评测：答案是否正确、是否引用正确
安全评测：无权限用户是否查不到敏感内容
```

常用指标：

```text
Recall@k
MRR
答案准确率
引用命中率
幻觉率
拒答正确率
延迟
成本
```

**落到你的项目**

你现在的金融 RAG 可以这么设计：

```text
annual_financial_facts_clean
  -> SQL 精确查数

annual_financial_tables / note_table chunks
  -> 表格 RAG

annual_reports 正文 chunks
  -> PDF RAG

supervisor/router
  -> 判断用户问题走 SQL 还是 RAG
```

比如：

```text
“688047 2024 年营业收入是多少？”
-> SQL facts

“龙芯中科非经常性损益有哪些？”
-> note_table RAG

“公司解释亏损原因是什么？”
-> 年报正文 RAG

“比较 2024 和 2025 年收入变化”
-> SQL + 生成解释
```

一句话面试表达：

```text
企业级 RAG 不是简单向量库工程，而是知识治理工程。我的做法是先按文档类型和业务语义分层：结构化数据进数据库，非结构化正文进向量库，复杂表格保留原表做 RAG；检索时结合关键词、向量、元数据过滤和 rerank；回答时强制引用来源，并用评测集持续监控准确率、召回率、权限和幻觉率。
```
