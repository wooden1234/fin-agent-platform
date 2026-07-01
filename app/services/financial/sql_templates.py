"""financial_query 的 SQL 模板注册与参数构建。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select

from app.core.database import AsyncSessionLocal
from app.models.annual_financial_fact import (
    AnnualReportDocument,
    FinancialCompany,
    FinancialMetric,
)
from app.services.financial.entity_resolver import EntityResolver
from app.services.financial.query_router import FinancialQueryRouter
from app.services.financial.schemas import FinancialQueryIntent


@dataclass(frozen=True)
class FinancialSqlTemplateDefinition:
    """模板 SQL 的静态定义。"""

    template_id: str
    description: str
    required_fields: tuple[str, ...]
    examples: tuple[str, ...]
    sql: str


@dataclass(frozen=True)
class BuiltFinancialSqlTemplate:
    """模板 SQL 构建结果。"""

    template_id: str
    sql: str
    params: dict[str, object]
    missing_fields: list[str]


_BASE_SELECT = """
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
FROM fin_core.annual_financial_facts AS fact
JOIN fin_core.annual_financial_tables AS table_ctx ON table_ctx.id = fact.table_id
JOIN fin_core.annual_report_documents AS document ON document.id = table_ctx.document_id
JOIN fin_core.financial_metrics AS metric ON metric.id = fact.metric_id
LEFT JOIN fin_core.financial_companies AS company ON company.id = document.company_id
WHERE document.company_id IN :company_ids
  AND fact.metric_id IN :metric_ids
  AND fact.period_label IS NOT NULL
  AND fact.period_label != ''
  AND fact.period_label NOT LIKE 'value_%%'
  AND (fact.period_type = 'annual' OR fact.period_type IS NULL)
  AND (fact.period_type IS NULL OR fact.period_type NOT IN ('change_rate', 'unknown'))
"""


class FinancialSqlTemplateRegistry:
    """维护模板定义与参数化 SQL 构建逻辑。"""

    _TEMPLATES: dict[str, FinancialSqlTemplateDefinition] = {
        FinancialQueryRouter.EXACT_LOOKUP_TEMPLATE.name: FinancialSqlTemplateDefinition(
            template_id=FinancialQueryRouter.EXACT_LOOKUP_TEMPLATE.name,
            description="单公司、单年份、单指标精确查数",
            required_fields=("company", "metric", "year"),
            examples=("宁德时代 2024 年营业收入是多少？", "腾讯 2023 年净利润"),
            sql=(
                _BASE_SELECT
                + """
  AND COALESCE(fact.period_year, document.fiscal_year) IN :years
ORDER BY COALESCE(fact.period_year, document.fiscal_year) DESC, metric.canonical_name
LIMIT :limit
"""
            ),
        ),
        FinancialQueryRouter.LATEST_LOOKUP_TEMPLATE.name: FinancialSqlTemplateDefinition(
            template_id=FinancialQueryRouter.LATEST_LOOKUP_TEMPLATE.name,
            description="单公司、最新一期、单指标查数",
            required_fields=("company", "metric"),
            examples=("宁德时代最新营收是多少？", "腾讯最近净利润"),
            sql=(
                _BASE_SELECT
                + """
ORDER BY COALESCE(fact.period_year, document.fiscal_year) DESC, metric.canonical_name
LIMIT :limit
"""
            ),
        ),
        FinancialQueryRouter.COMPARE_LOOKUP_TEMPLATE.name: FinancialSqlTemplateDefinition(
            template_id=FinancialQueryRouter.COMPARE_LOOKUP_TEMPLATE.name,
            description="多公司或多指标对比查询",
            required_fields=("company", "metric"),
            examples=("宁德时代和腾讯 2024 年营收对比", "宁德时代 2024 年营收和研发费用对比"),
            sql=(
                _BASE_SELECT
                + """
  AND (:years_empty OR COALESCE(fact.period_year, document.fiscal_year) IN :years)
ORDER BY COALESCE(fact.period_year, document.fiscal_year) DESC, company.name, metric.canonical_name
LIMIT :limit
"""
            ),
        ),
        FinancialQueryRouter.TREND_LOOKUP_TEMPLATE.name: FinancialSqlTemplateDefinition(
            template_id=FinancialQueryRouter.TREND_LOOKUP_TEMPLATE.name,
            description="单公司或单指标跨年份趋势查询",
            required_fields=("company", "metric"),
            examples=("宁德时代近三年营收趋势", "腾讯历年净利润"),
            sql=(
                _BASE_SELECT
                + """
  AND (:years_empty OR COALESCE(fact.period_year, document.fiscal_year) IN :years)
ORDER BY company.name, metric.canonical_name, COALESCE(fact.period_year, document.fiscal_year) ASC
LIMIT :limit
"""
            ),
        ),
    }

    @classmethod
    def template_examples(cls) -> str:
        """为 Prompt 生成紧凑模板描述。"""
        lines: list[str] = []
        for template in cls._TEMPLATES.values():
            examples = " / ".join(template.examples)
            required = ", ".join(template.required_fields)
            lines.append(
                f"- {template.template_id}: {template.description}; required={required}; examples={examples}"
            )
        return "\n".join(lines)

    @classmethod
    def get(cls, template_id: str) -> FinancialSqlTemplateDefinition | None:
        return cls._TEMPLATES.get(template_id)

    @classmethod
    def valid_template_ids(cls) -> set[str]:
        return set(cls._TEMPLATES)

    @classmethod
    async def build(
        cls,
        template_id: str,
        query: FinancialQueryIntent,
        *,
        limit: int = 5,
    ) -> BuiltFinancialSqlTemplate:
        template = cls.get(template_id)
        if template is None:
            return BuiltFinancialSqlTemplate(
                template_id=template_id,
                sql="",
                params={},
                missing_fields=["template"],
            )

        company_ids = await cls._resolve_company_ids(query.companies)
        metric_ids = await cls._resolve_metric_ids(query.metrics)
        years = list(query.years)
        missing_fields = cls._missing_fields(
            template.required_fields,
            query=query,
            company_ids=company_ids,
            metric_ids=metric_ids,
            years=years,
        )
        if missing_fields:
            return BuiltFinancialSqlTemplate(
                template_id=template_id,
                sql="",
                params={},
                missing_fields=missing_fields,
            )

        effective_limit = max(1, min(limit, max(query.top_k, 1)))
        if template_id == FinancialQueryRouter.LATEST_LOOKUP_TEMPLATE.name:
            effective_limit = 1

        return BuiltFinancialSqlTemplate(
            template_id=template_id,
            sql=template.sql.strip(),
            params={
                "company_ids": company_ids,
                "metric_ids": metric_ids,
                "years": years or [-1],
                "years_empty": not years,
                "limit": effective_limit,
            },
            missing_fields=[],
        )

    @staticmethod
    def _missing_fields(
        required_fields: tuple[str, ...],
        *,
        query: FinancialQueryIntent,
        company_ids: list[int],
        metric_ids: list[int],
        years: list[int],
    ) -> list[str]:
        missing_fields: list[str] = []
        if "company" in required_fields and (not query.companies or not company_ids):
            missing_fields.append("company")
        if "metric" in required_fields and (not query.metrics or not metric_ids):
            missing_fields.append("metric")
        if "year" in required_fields and not years:
            missing_fields.append("year")
        return missing_fields

    @staticmethod
    async def _resolve_company_ids(companies: list[str]) -> list[int]:
        exact_terms: set[str] = set()
        ticker_terms: set[str] = set()
        for company in companies:
            for term in EntityResolver.expand_company_terms(company):
                cleaned = term.strip()
                if not cleaned:
                    continue
                if cleaned.isdigit():
                    ticker_terms.add(cleaned)
                else:
                    exact_terms.add(cleaned.lower())

        if not exact_terms and not ticker_terms:
            return []

        async with AsyncSessionLocal() as session:
            conditions = []
            if exact_terms:
                conditions.extend(
                    [
                        func.lower(FinancialCompany.name).in_(exact_terms),
                        func.lower(FinancialCompany.company_key).in_(exact_terms),
                    ]
                )
            if ticker_terms:
                conditions.append(FinancialCompany.ticker.in_(ticker_terms))
            stmt = select(FinancialCompany.id).where(or_(*conditions))
            result = await session.execute(stmt)
            return list(dict.fromkeys(result.scalars().all()))

    @staticmethod
    async def _resolve_metric_ids(metrics: list[str]) -> list[int]:
        exact_terms: set[str] = set()
        fuzzy_terms: set[str] = set()
        for metric in metrics:
            for term in EntityResolver.expand_metric_terms(metric):
                cleaned = term.strip()
                if not cleaned:
                    continue
                exact_terms.add(cleaned.lower())
                fuzzy_terms.add(cleaned)

        if not exact_terms:
            return []

        async with AsyncSessionLocal() as session:
            conditions = [func.lower(FinancialMetric.canonical_name).in_(exact_terms)]
            for term in fuzzy_terms:
                conditions.append(FinancialMetric.aliases.ilike(f"%{term}%"))
            stmt = select(FinancialMetric.id).where(or_(*conditions))
            result = await session.execute(stmt)
            return list(dict.fromkeys(result.scalars().all()))


__all__ = [
    "BuiltFinancialSqlTemplate",
    "FinancialSqlTemplateDefinition",
    "FinancialSqlTemplateRegistry",
]
