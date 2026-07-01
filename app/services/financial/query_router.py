"""金融查询内部路由策略。"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.financial.schemas import FinancialQueryIntent


@dataclass(frozen=True)
class FinancialQueryTemplate:
    """预定义查询模板；未命中时再回退到通用搜索。"""

    name: str
    description: str


class FinancialQueryRouter:
    """决定金融查询应走模板、低风险通用搜索还是后续兜底策略。"""

    SAFE_GENERIC_SEARCH_ROUTE = "generic_search_safe"
    NEEDS_CLARIFICATION_ROUTE = "needs_clarification"
    TEXT_TO_SQL_FALLBACK_ROUTE = "text_to_sql_fallback"

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

    @classmethod
    def match_template(
        cls,
        question: str,
        query: FinancialQueryIntent,
    ) -> FinancialQueryTemplate | None:
        """将简单结构化问题路由到预定义查询模板。"""
        normalized_question = question.strip()
        has_company = len(query.companies) == 1 and bool(query.company.strip())
        has_metric = len(query.metrics) == 1 and bool(query.metric.strip())
        has_year = len(query.years) == 1 and query.year is not None
        has_multiple_companies = len(query.companies) > 1
        has_multiple_years = len(query.years) > 1
        has_multiple_metrics = len(query.metrics) > 1

        # 模板查询默认追求“高确定性命中”；一旦 resolver 仍然保留歧义，就先不要强行套模板。
        if query.has_template_blocking_ambiguity():
            return None

        # 优先尊重 LLM 已识别出的 operation，再用问法和字段形态做兜底推断。
        if query.operation == "compare" and (
            has_multiple_companies or has_multiple_metrics
        ):
            return cls.COMPARE_LOOKUP_TEMPLATE

        if query.operation == "trend" and has_metric and (
            has_company or has_multiple_years
        ):
            return cls.TREND_LOOKUP_TEMPLATE

        if query.operation == "latest" and has_company and has_metric:
            return cls.LATEST_LOOKUP_TEMPLATE

        if has_company and has_metric and has_year:
            return cls.EXACT_LOOKUP_TEMPLATE

        if has_multiple_companies and has_metric:
            return cls.COMPARE_LOOKUP_TEMPLATE

        if has_company and has_metric and (
            has_multiple_years
            or any(
                keyword in normalized_question
                for keyword in ["趋势", "近年", "近几年", "历年"]
            )
        ):
            return cls.TREND_LOOKUP_TEMPLATE

        if (
            has_company
            and has_metric
            and not has_year
            and any(
                keyword in normalized_question
                for keyword in ["最新", "最近", "今年", "当前"]
            )
        ):
            return cls.LATEST_LOOKUP_TEMPLATE

        return None

    @classmethod
    def route_generic_search(cls, query: FinancialQueryIntent) -> str:
        """决定模板未命中后是否还能继续走安全的结构化搜索。"""
        if query.has_template_blocking_ambiguity():
            return cls.NEEDS_CLARIFICATION_ROUTE
        if cls.is_low_risk_generic_search(query):
            return cls.SAFE_GENERIC_SEARCH_ROUTE
        return cls.TEXT_TO_SQL_FALLBACK_ROUTE

    @staticmethod
    def is_low_risk_generic_search(query: FinancialQueryIntent) -> bool:
        """当前“低风险通用搜索”仅指单公司、指标锚定的简单查数。"""
        return (
            query.operation == "lookup"
            and len(query.companies) == 1
            and len(query.metrics) >= 1
        )


__all__ = [
    "FinancialQueryRouter",
    "FinancialQueryTemplate",
]
