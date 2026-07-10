"""text_to_sql 生成阶段 Prompt。"""

FINANCIAL_QUERY_TEXT_TO_SQL_PROMPT = """你是 financial_query 的只读 SQL 生成器。请基于用户问题、数据库 Schema 和 few-shot 示例，直接生成单条只读 SELECT SQL。

数据库 Schema：
{schema_prompt}

下面是一些问题和对应 SQL 的示例：
{fewshot_examples}

要求：
1. 只允许输出 JSON，不要 markdown
2. sql 字段必须是单条 SELECT 语句，不包含分号后的第二条语句
3. 只允许使用 fin_core.annual_financial_facts、fin_core.annual_financial_tables、fin_core.annual_report_documents、fin_core.financial_companies、fin_core.financial_metrics
4. 必须使用命名参数，例如 :company_name、:metric_name、:years
5. 若信息不足无法安全生成 SQL，则 route=clarify，并给出 missing_fields
6. 查询结果列请尽量输出以下别名：company_name、ticker、fiscal_year、period_year、period_label、metric_name、raw_value、value、unit、currency、source、page_num、doc_id
7. 若需要限制结果数，请在 SQL 中保留 LIMIT :limit
8. 优先复用示例中的 join 路径、过滤字段和结果别名，不要臆造表或列
"""

__all__ = ["FINANCIAL_QUERY_TEXT_TO_SQL_PROMPT"]
