"""fin_core 五表结构白名单，源自 migrate_annual_financial_facts_normalized.sql。"""

from __future__ import annotations

from dataclasses import dataclass

FIN_CORE_SCHEMA = "fin_core"

ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        f"{FIN_CORE_SCHEMA}.financial_companies",
        f"{FIN_CORE_SCHEMA}.annual_report_documents",
        f"{FIN_CORE_SCHEMA}.annual_financial_tables",
        f"{FIN_CORE_SCHEMA}.financial_metrics",
        f"{FIN_CORE_SCHEMA}.annual_financial_facts",
    }
)


@dataclass(frozen=True)
class FinCoreTableDefinition:
    schema: str
    name: str
    description: str
    columns: tuple[str, ...]
    primary_key: str
    foreign_keys: tuple[str, ...] = ()


FIN_CORE_TABLES: dict[str, FinCoreTableDefinition] = {
    "financial_companies": FinCoreTableDefinition(
        schema=FIN_CORE_SCHEMA,
        name="financial_companies",
        description="公司维度表",
        columns=("id", "company_key", "name", "ticker", "created_at", "updated_at"),
        primary_key="id",
    ),
    "annual_report_documents": FinCoreTableDefinition(
        schema=FIN_CORE_SCHEMA,
        name="annual_report_documents",
        description="年报文档元数据",
        columns=("id", "doc_id", "company_id", "title", "fiscal_year", "source", "created_at", "updated_at"),
        primary_key="id",
        foreign_keys=("company_id -> financial_companies.id",),
    ),
    "annual_financial_tables": FinCoreTableDefinition(
        schema=FIN_CORE_SCHEMA,
        name="annual_financial_tables",
        description="文档内财务表格分块",
        columns=(
            "id",
            "document_id",
            "chunk_index",
            "page_num",
            "section",
            "table_kind",
            "raw_table_text",
            "created_at",
            "updated_at",
        ),
        primary_key="id",
        foreign_keys=("document_id -> annual_report_documents.id",),
    ),
    "financial_metrics": FinCoreTableDefinition(
        schema=FIN_CORE_SCHEMA,
        name="financial_metrics",
        description="财务指标字典",
        columns=("id", "canonical_name", "aliases", "statement_type", "created_at", "updated_at"),
        primary_key="id",
    ),
    "annual_financial_facts": FinCoreTableDefinition(
        schema=FIN_CORE_SCHEMA,
        name="annual_financial_facts",
        description="窄表事实：单表单单指标单期间数值",
        columns=(
            "id",
            "table_id",
            "metric_id",
            "row_index",
            "period_label",
            "period_year",
            "period_type",
            "value",
            "raw_value",
            "unit",
            "currency",
            "raw_row",
            "created_at",
            "updated_at",
        ),
        primary_key="id",
        foreign_keys=(
            "table_id -> annual_financial_tables.id",
            "metric_id -> financial_metrics.id",
        ),
    ),
}

STANDARD_JOIN_SQL = f"""
FROM {FIN_CORE_SCHEMA}.annual_financial_facts AS fact
JOIN {FIN_CORE_SCHEMA}.annual_financial_tables AS table_ctx
  ON table_ctx.id = fact.table_id
JOIN {FIN_CORE_SCHEMA}.annual_report_documents AS document
  ON document.id = table_ctx.document_id
JOIN {FIN_CORE_SCHEMA}.financial_metrics AS metric
  ON metric.id = fact.metric_id
LEFT JOIN {FIN_CORE_SCHEMA}.financial_companies AS company
  ON company.id = document.company_id
""".strip()

BASE_FACT_FILTERS = """
  AND fact.period_label IS NOT NULL
  AND fact.period_label != ''
  AND fact.period_label NOT LIKE 'value_%'
  AND (fact.period_type = 'annual' OR fact.period_type IS NULL)
  AND (fact.period_type IS NULL OR fact.period_type NOT IN ('change_rate', 'unknown'))
""".strip()

TEMPLATE_SELECT_SQL = f"""
SELECT
  company.name AS company_name,
  company.ticker AS ticker,
  document.fiscal_year AS fiscal_year,
  fact.period_year AS period_year,
  fact.period_label AS period_label,
  metric.canonical_name AS metric_name,
  COALESCE(fact.raw_value, '') AS raw_value,
  COALESCE(CAST(fact.value AS TEXT), '') AS value,
  COALESCE(fact.unit, '') AS unit,
  COALESCE(fact.currency, '') AS currency,
  COALESCE(document.source, '') AS source,
  table_ctx.page_num AS page_num,
  COALESCE(document.doc_id, '') AS doc_id
{STANDARD_JOIN_SQL}
WHERE document.company_id IN :company_ids
  AND fact.metric_id IN :metric_ids
{BASE_FACT_FILTERS}
""".strip()


def schema_prompt() -> str:
    lines = [f"Schema: {FIN_CORE_SCHEMA}", ""]
    for table in FIN_CORE_TABLES.values():
        cols = ", ".join(table.columns)
        fks = f"; FK: {', '.join(table.foreign_keys)}" if table.foreign_keys else ""
        lines.append(f"- {table.schema}.{table.name}: {table.description}; columns={cols}{fks}")
    lines.extend(["", "推荐 Join 路径：", STANDARD_JOIN_SQL, "", "模板查询过滤口径：", BASE_FACT_FILTERS])
    return "\n".join(lines)


__all__ = [
    "ALLOWED_TABLES",
    "BASE_FACT_FILTERS",
    "FIN_CORE_SCHEMA",
    "FIN_CORE_TABLES",
    "FinCoreTableDefinition",
    "STANDARD_JOIN_SQL",
    "TEMPLATE_SELECT_SQL",
    "schema_prompt",
]
