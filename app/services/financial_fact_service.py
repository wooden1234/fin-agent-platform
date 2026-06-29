"""annual_financial_facts 结构化查询服务（供 db_agent 使用）。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

from app.core.database import AsyncSessionLocal
from app.models.annual_financial_fact import (
    AnnualFinancialFact,
    AnnualFinancialTable,
    AnnualReportDocument,
    FinancialCompany,
    FinancialMetric,
)

# 常见公司简称 → 年报 title 中的英文关键词
COMPANY_ALIASES: dict[str, list[str]] = {
    "宁德时代": ["CATL"],
    "宁德": ["CATL"],
    "catl": ["CATL"],
    "腾讯": ["Tencent"],
    "tencent": ["Tencent"],
    "龙芯": ["Loongson"],
    "loongson": ["Loongson"],
    "寒武纪": ["Cambricon"],
    "cambricon": ["Cambricon"],
}

# 口语指标 → 库中 metric_name 关键词
METRIC_ALIASES: dict[str, list[str]] = {
    "营收": ["营业收入"],
    "收入": ["营业收入"],
    "营业额": ["营业收入"],
    "净利润": ["归属于上市公司股东的净利润", "净利润"],
    "净利": ["归属于上市公司股东的净利润"],
    "归母净利润": ["归属于上市公司股东的净利润"],
    "研发": ["研发费用"],
    "现金流": ["经营活动产生的现金流量净额"],
}


class FinancialFactQuery(BaseModel):
    """从自然语言问题中抽取的结构化查询参数。"""

    companies: list[str] = Field(
        default_factory=list,
        description="公司名、简称或股票代码列表；简单问题通常只有一个",
    )
    years: list[int] = Field(
        default_factory=list,
        description="报告年份或财年列表，例如 [2024]、[2022, 2023, 2024]",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description="财务指标列表，例如 ['营业收入']、['营业收入', '研发费用']",
    )
    operation: Literal["lookup", "latest", "compare", "trend"] = Field(
        default="lookup",
        description="查询意图：精确查数、最新一期、公司对比、趋势查询",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="最多返回多少条结果")

    @computed_field
    @property
    def company(self) -> str:
        return self.companies[0] if self.companies else ""

    @computed_field
    @property
    def year(self) -> int | None:
        return self.years[0] if self.years else None

    @computed_field
    @property
    def metric(self) -> str:
        return self.metrics[0] if self.metrics else ""


@dataclass(frozen=True)
class FinancialQueryTemplate:
    """预定义查询模板；未命中时再回退到通用搜索。"""

    name: str
    description: str


class FinancialFactService:
    """查询 annual_financial_facts 并格式化为 Agent 可读文本。"""

    EXACT_LOOKUP_TEMPLATE = FinancialQueryTemplate(
        name="exact_metric_lookup",
        description="单公司、单年份、单指标精确查数",
    )
    LATEST_LOOKUP_TEMPLATE = FinancialQueryTemplate(
        name="latest_metric_lookup",
        description="单公司、未指定年份、查询最新一期指标",
    )
    COMPARE_LOOKUP_TEMPLATE = FinancialQueryTemplate(
        name="compare_metric_lookup",
        description="多公司或多指标对比查询",
    )
    TREND_LOOKUP_TEMPLATE = FinancialQueryTemplate(
        name="trend_metric_lookup",
        description="单公司或单指标跨年份趋势查询",
    )

    @staticmethod
    def resolve_company_terms(company: str) -> list[str]:
        key = company.strip()
        if not key:
            return []
        lowered = key.lower()
        if lowered in COMPANY_ALIASES:
            return COMPANY_ALIASES[lowered]
        if key in COMPANY_ALIASES:
            return COMPANY_ALIASES[key]
        return [key]

    @staticmethod
    def resolve_metric_terms(metric: str) -> list[str]:
        key = metric.strip()
        if not key:
            return []
        if key in METRIC_ALIASES:
            return METRIC_ALIASES[key]
        return [key]

    @classmethod
    def match_template(
        cls,
        question: str,
        query: FinancialFactQuery,
    ) -> FinancialQueryTemplate | None:
        """将简单结构化问题路由到预定义查询模板。"""
        normalized_question = question.strip()
        has_company = len(query.companies) == 1 and bool(query.company.strip())
        has_metric = len(query.metrics) == 1 and bool(query.metric.strip())
        has_year = len(query.years) == 1 and query.year is not None
        has_multiple_companies = len(query.companies) > 1
        has_multiple_years = len(query.years) > 1
        has_multiple_metrics = len(query.metrics) > 1

        # 优先尊重 LLM 已识别出的 operation，再用问法和字段形态做兜底推断。
        if query.operation == "compare" and (has_multiple_companies or has_multiple_metrics):
            return cls.COMPARE_LOOKUP_TEMPLATE

        if query.operation == "trend" and has_metric and (has_company or has_multiple_years):
            return cls.TREND_LOOKUP_TEMPLATE

        if query.operation == "latest" and has_company and has_metric:
            return cls.LATEST_LOOKUP_TEMPLATE

        if has_company and has_metric and has_year:
            return cls.EXACT_LOOKUP_TEMPLATE

        if has_multiple_companies and has_metric:
            return cls.COMPARE_LOOKUP_TEMPLATE

        if has_company and has_metric and (
            has_multiple_years
            or any(keyword in normalized_question for keyword in ["趋势", "近年", "近几年", "历年"])
        ):
            return cls.TREND_LOOKUP_TEMPLATE

        if (
            has_company
            and has_metric
            and not has_year
            and any(keyword in normalized_question for keyword in ["最新", "最近", "今年", "当前"])
        ):
            return cls.LATEST_LOOKUP_TEMPLATE

        return None

    @classmethod
    async def execute_query(
        cls,
        question: str,
        query: FinancialFactQuery,
        *,
        limit: int | None = None,
    ) -> tuple[list[AnnualFinancialFact], str]:
        limit = limit or query.top_k
        template = cls.match_template(question, query)
        if template is not None:
            facts = await cls.run_template(template, query, limit=limit)
            return facts, template.name
        facts = await cls.search(query, limit=limit)
        return facts, "generic_search"

    @classmethod
    async def run_template(
        cls,
        template: FinancialQueryTemplate,
        query: FinancialFactQuery,
        *,
        limit: int = 5,
    ) -> list[AnnualFinancialFact]:
        if template.name == cls.EXACT_LOOKUP_TEMPLATE.name:
            return await cls._search_exact_metric_lookup(query, limit=limit)
        if template.name == cls.LATEST_LOOKUP_TEMPLATE.name:
            return await cls._search_latest_metric_lookup(query, limit=limit)
        if template.name == cls.COMPARE_LOOKUP_TEMPLATE.name:
            return await cls._search_compare_metric_lookup(query, limit=limit)
        if template.name == cls.TREND_LOOKUP_TEMPLATE.name:
            return await cls._search_trend_metric_lookup(query, limit=limit)
        return await cls.search(query, limit=limit)

    @classmethod
    async def search(
        cls,
        query: FinancialFactQuery,
        *,
        limit: int = 5,
    ) -> list[AnnualFinancialFact]:
        return await cls._search_base(query, limit=limit)

    @classmethod
    async def _search_exact_metric_lookup(
        cls,
        query: FinancialFactQuery,
        *,
        limit: int = 5,
    ) -> list[AnnualFinancialFact]:
        return await cls._search_base(query, limit=limit)

    @classmethod
    async def _search_latest_metric_lookup(
        cls,
        query: FinancialFactQuery,
        *,
        limit: int = 1,
    ) -> list[AnnualFinancialFact]:
        return await cls._search_base(query, limit=limit, latest_only=True)

    @classmethod
    async def _search_compare_metric_lookup(
        cls,
        query: FinancialFactQuery,
        *,
        limit: int = 5,
    ) -> list[AnnualFinancialFact]:
        # 对比查询往往需要多拿一些候选行，再按“公司-指标-年份”去重后保留代表结果。
        company_count = max(1, len(query.companies))
        metric_count = max(1, len(query.metrics))
        year_count = max(1, len(query.years))
        search_limit = max(limit, company_count * metric_count * year_count * 3)
        facts = await cls._search_base(query, limit=search_limit)

        grouped: dict[tuple[str, str, int | str], AnnualFinancialFact] = {}
        for fact in facts:
            company = cls._display_company(fact)
            metric_name = cls._display_metric_name(fact)
            year = cls._fact_year(fact)
            key = (company, metric_name, year)
            grouped.setdefault(key, fact)

        sorted_facts = sorted(
            grouped.values(),
            key=lambda fact: (
                cls._fact_year_sort_key(fact, desc=True),
                cls._display_metric_name(fact),
                cls._display_company(fact),
            ),
        )
        return sorted_facts[:limit]

    @classmethod
    async def _search_trend_metric_lookup(
        cls,
        query: FinancialFactQuery,
        *,
        limit: int = 5,
    ) -> list[AnnualFinancialFact]:
        # 趋势查询更关注时间序列完整性，所以会优先放大按年份取回的候选集。
        year_count = max(limit, len(query.years) or limit)
        search_limit = max(limit, year_count * max(1, len(query.metrics)) * 3)
        facts = await cls._search_base(query, limit=search_limit)

        grouped: dict[tuple[str, str, int | str], AnnualFinancialFact] = {}
        for fact in facts:
            company = cls._display_company(fact)
            metric_name = cls._display_metric_name(fact)
            year = cls._fact_year(fact)
            key = (company, metric_name, year)
            grouped.setdefault(key, fact)

        sorted_facts = sorted(
            grouped.values(),
            key=lambda fact: (
                cls._display_company(fact),
                cls._display_metric_name(fact),
                cls._fact_year_sort_key(fact, desc=False),
            ),
        )
        return sorted_facts[:limit]

    @classmethod
    async def _search_base(
        cls,
        query: FinancialFactQuery,
        *,
        limit: int = 5,
        latest_only: bool = False,
    ) -> list[AnnualFinancialFact]:
        # 先把自然语言里的公司/指标别名摊平，底层统一走模糊匹配。
        company_terms: list[str] = []
        for company in query.companies:
            company_terms.extend(cls.resolve_company_terms(company))

        metric_terms: list[str] = []
        for metric in query.metrics:
            metric_terms.extend(cls.resolve_metric_terms(metric))

        if not company_terms and not query.company.strip().isdigit():
            return []

        async with AsyncSessionLocal() as session:
            conditions: list = []

            company_conditions = []
            for term in company_terms:
                company_conditions.append(FinancialCompany.name.ilike(f"%{term}%"))
                company_conditions.append(AnnualReportDocument.title.ilike(f"%{term}%"))
            for company in query.companies:
                ticker = company.strip()
                if ticker.isdigit():
                    company_conditions.append(FinancialCompany.ticker == ticker)
            if not company_conditions:
                return []
            conditions.append(or_(*company_conditions))

            if query.years:
                year_conditions = []
                for year in query.years:
                    year_conditions.append(AnnualFinancialFact.period_year == year)
                    year_conditions.append(
                        and_(
                            AnnualFinancialFact.period_year.is_(None),
                            AnnualReportDocument.fiscal_year == year,
                        )
                    )
                conditions.append(
                    or_(*year_conditions)
                )

            if metric_terms:
                metric_conditions = []
                for term in metric_terms:
                    metric_conditions.append(
                        FinancialMetric.canonical_name.ilike(f"%{term}%")
                    )
                    metric_conditions.append(
                        FinancialMetric.aliases.ilike(f"%{term}%")
                    )
                conditions.append(or_(*metric_conditions))

            conditions.extend(cls._clean_row_filters())

            # 底层统一按“最近年份优先”排序；上层对比/趋势查询再按各自语义二次整理。
            stmt = (
                select(AnnualFinancialFact)
                .join(AnnualFinancialFact.table)
                .join(AnnualFinancialTable.document)
                .outerjoin(AnnualReportDocument.company)
                .join(AnnualFinancialFact.metric)
                .options(
                    joinedload(AnnualFinancialFact.table)
                    .joinedload(AnnualFinancialTable.document)
                    .joinedload(AnnualReportDocument.company),
                    joinedload(AnnualFinancialFact.metric),
                )
                .where(and_(*conditions))
                .order_by(
                    AnnualFinancialFact.period_year.desc(),
                    AnnualReportDocument.fiscal_year.desc(),
                    FinancialMetric.canonical_name,
                )
                .limit(limit)
            )
            result = await session.execute(stmt)
            facts = list(result.scalars().all())
            if latest_only and facts:
                return facts[:1]
            return facts

    @staticmethod
    def _clean_row_filters() -> list:
        """对齐 financial_table_pipeline 的 clean view 规则。"""
        return [
            AnnualFinancialFact.period_label.isnot(None),
            AnnualFinancialFact.period_label != "",
            ~AnnualFinancialFact.period_label.like("value_%"),
            or_(
                AnnualFinancialFact.period_type == "annual",
                AnnualFinancialFact.period_type.is_(None),
            ),
            or_(
                AnnualFinancialFact.period_type.is_(None),
                ~AnnualFinancialFact.period_type.in_(["change_rate", "unknown"]),
            ),
        ]

    @staticmethod
    def _document(fact: AnnualFinancialFact):
        table = getattr(fact, "table", None)
        return getattr(table, "document", None) if table is not None else None

    @staticmethod
    def _table(fact: AnnualFinancialFact):
        return getattr(fact, "table", None)

    @staticmethod
    def _metric(fact: AnnualFinancialFact):
        return getattr(fact, "metric", None)

    @classmethod
    def _display_company(cls, fact: AnnualFinancialFact) -> str:
        document = cls._document(fact)
        company = getattr(document, "company", None) if document is not None else None
        if company is not None and getattr(company, "name", None):
            return company.name
        title = getattr(fact, "title", None) or getattr(document, "title", "") or ""
        if " Annual Report" in title:
            return title.split(" Annual Report")[0]
        ticker = getattr(fact, "ticker", None) or getattr(company, "ticker", None)
        return title or ticker or "未知公司"

    @classmethod
    def _display_metric_name(cls, fact: AnnualFinancialFact) -> str:
        metric = cls._metric(fact)
        return getattr(fact, "metric_name", None) or getattr(
            metric, "canonical_name", "未知指标"
        )

    @classmethod
    def _fact_year(cls, fact: AnnualFinancialFact) -> int | str:
        document = cls._document(fact)
        return (
            fact.period_year
            or getattr(fact, "fiscal_year", None)
            or getattr(document, "fiscal_year", None)
            or "未知年份"
        )

    @classmethod
    def _fact_year_sort_key(cls, fact: AnnualFinancialFact, *, desc: bool) -> tuple[int, int]:
        # 未知年份统一排在最后，避免干扰趋势和对比结果的主序。
        year = cls._fact_year(fact)
        if isinstance(year, int):
            return (0, -year if desc else year)
        return (1, 0)

    @staticmethod
    def _display_value(fact: AnnualFinancialFact) -> str:
        if fact.raw_value:
            return fact.raw_value
        if fact.value is None:
            return "—"
        if isinstance(fact.value, Decimal):
            normalized = fact.value.normalize()
            return format(normalized, "f").rstrip("0").rstrip(".")
        return str(fact.value)

    @classmethod
    def format_answer(cls, facts: list[AnnualFinancialFact]) -> str:
        if not facts:
            return "（数据库中未找到匹配的财务指标，建议改查 PDF 文档库。）"

        # 这里保持“一行一个事实”，把跨公司/跨年份的组织交给上游 summarize。
        lines: list[str] = []
        for fact in facts:
            company = cls._display_company(fact)
            document = cls._document(fact)
            year = cls._fact_year(fact)
            value = cls._display_value(fact)
            unit = fact.unit or ""
            currency = f"，{fact.currency}" if fact.currency else ""
            table = cls._table(fact)
            page_num = getattr(fact, "page_num", None) or getattr(table, "page_num", None)
            page = f"第{page_num}页" if page_num else "未知页码"
            metric_name = cls._display_metric_name(fact)
            source = getattr(fact, "source", None) or getattr(document, "source", "")
            lines.append(
                f"{company} {year}年 {metric_name}为 {value}{unit}{currency}"
                f"（来源：{source} {page}）"
            )
        return "\n".join(lines)

    @staticmethod
    def to_citations(facts: list[AnnualFinancialFact]) -> list[dict]:
        citations: list[dict] = []
        for fact in facts:
            document = FinancialFactService._document(fact)
            table = FinancialFactService._table(fact)
            metric_name = FinancialFactService._display_metric_name(fact)
            snippet = f"{metric_name}: {fact.raw_value or fact.value}"
            if fact.unit:
                snippet = f"{snippet}{fact.unit}"
            citation: dict = {
                "source": getattr(fact, "source", None)
                or getattr(document, "source", None)
                or getattr(fact, "doc_id", None)
                or getattr(document, "doc_id", "")
                or "",
                "snippet": snippet[:200],
            }
            page_num = getattr(fact, "page_num", None) or getattr(table, "page_num", None)
            if page_num is not None:
                citation["page"] = page_num
            citations.append(citation)
        return citations
