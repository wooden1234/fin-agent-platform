"""text_to_sql 生成阶段所需上下文。"""

from __future__ import annotations

from app.agents.components.finance_agent.financial_query_agent.retrievers.sql_examples import (
    FinancialSqlExampleRetriever,
)

_EXAMPLE_RETRIEVER = FinancialSqlExampleRetriever()

FINANCIAL_SQL_SCHEMA_PROMPT = """\
表 fin_core.financial_companies：
- id: 公司主键
- company_key: 公司规范化标识
- name: 公司名称
- ticker: 股票代码

表 fin_core.annual_report_documents：
- id: 文档主键
- doc_id: 文档唯一标识
- company_id: 对应公司主键，关联 financial_companies.id
- title: 文档标题
- fiscal_year: 财年
- source: 原始文件名或来源

表 fin_core.annual_financial_tables：
- id: 表格主键
- document_id: 对应年报文档主键，关联 annual_report_documents.id
- chunk_index: 文档内表格序号
- page_num: 页码
- section: 所在章节
- table_kind: 报表类别

表 fin_core.financial_metrics：
- id: 指标主键
- canonical_name: 指标规范名
- aliases: 指标别名
- statement_type: 指标所属报表类型

表 fin_core.annual_financial_facts：
- id: 事实主键
- table_id: 对应财务表主键，关联 annual_financial_tables.id
- metric_id: 对应指标主键，关联 financial_metrics.id
- row_index: 原始表格行号
- period_label: 原始期间标签
- period_year: 标准化年份
- period_type: 期间类型
- value: 标准化数值
- raw_value: 原始文本值
- unit: 单位
- currency: 币种
- raw_row: 原始行文本

推荐 Join 路径：
annual_financial_facts AS fact
JOIN annual_financial_tables AS table_ctx ON table_ctx.id = fact.table_id
JOIN annual_report_documents AS document ON document.id = table_ctx.document_id
JOIN financial_metrics AS metric ON metric.id = fact.metric_id
LEFT JOIN financial_companies AS company ON company.id = document.company_id
"""


def build_schema_prompt() -> str:
    """集中维护 Schema 文本，避免生成与修正阶段口径不一致。"""
    return FINANCIAL_SQL_SCHEMA_PROMPT


def build_fewshot_examples(question: str, *, k: int = 3) -> str:
    """先按规则检索 few-shot，后续可无缝替换成向量检索。"""
    examples = _EXAMPLE_RETRIEVER.get_examples(question, k=k)
    return _EXAMPLE_RETRIEVER.format_examples(examples)


__all__ = ["FINANCIAL_SQL_SCHEMA_PROMPT", "build_fewshot_examples", "build_schema_prompt"]

