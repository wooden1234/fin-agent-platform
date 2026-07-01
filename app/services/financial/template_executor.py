"""金融查询模板执行器。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.services.financial.query_router import (
    FinancialQueryRouter,
    FinancialQueryTemplate,
)
from app.services.financial.schemas import FinancialQueryIntent

FinancialFactT = TypeVar("FinancialFactT")
SearchFn = Callable[..., Awaitable[list[FinancialFactT]]]
DisplayTextFn = Callable[[FinancialFactT], str]
FactYearFn = Callable[[FinancialFactT], int | str]
FactYearSortKeyFn = Callable[[FinancialFactT], tuple[int, int]]


class FinancialTemplateExecutor:
    """执行已命中的金融查询模板。

    基础事实召回由调用方注入，避免模板层直接依赖数据库查询实现。
    """

    @classmethod
    async def run_template(
        cls,
        template: FinancialQueryTemplate,
        query: FinancialQueryIntent,
        *,
        search_fn: SearchFn[FinancialFactT],
        display_company: DisplayTextFn[FinancialFactT],
        display_metric_name: DisplayTextFn[FinancialFactT],
        fact_year: FactYearFn[FinancialFactT],
        fact_year_sort_key_desc: FactYearSortKeyFn[FinancialFactT],
        fact_year_sort_key_asc: FactYearSortKeyFn[FinancialFactT],
        limit: int = 5,
    ) -> list[FinancialFactT]:
        # 当前模板系统还是轻量分发器：模板之间共享一套基础搜索，再做少量结果后处理。
        if template.name == FinancialQueryRouter.EXACT_LOOKUP_TEMPLATE.name:
            return await cls._search_exact_metric_lookup(
                query,
                search_fn=search_fn,
                limit=limit,
            )
        if template.name == FinancialQueryRouter.LATEST_LOOKUP_TEMPLATE.name:
            return await cls._search_latest_metric_lookup(
                query,
                search_fn=search_fn,
                limit=limit,
            )
        if template.name == FinancialQueryRouter.COMPARE_LOOKUP_TEMPLATE.name:
            return await cls._search_compare_metric_lookup(
                query,
                search_fn=search_fn,
                display_company=display_company,
                display_metric_name=display_metric_name,
                fact_year=fact_year,
                fact_year_sort_key_desc=fact_year_sort_key_desc,
                limit=limit,
            )
        if template.name == FinancialQueryRouter.TREND_LOOKUP_TEMPLATE.name:
            return await cls._search_trend_metric_lookup(
                query,
                search_fn=search_fn,
                display_company=display_company,
                display_metric_name=display_metric_name,
                fact_year=fact_year,
                fact_year_sort_key_asc=fact_year_sort_key_asc,
                limit=limit,
            )
        return await search_fn(query, limit=limit)

    @staticmethod
    async def _search_exact_metric_lookup(
        query: FinancialQueryIntent,
        *,
        search_fn: SearchFn[FinancialFactT],
        limit: int = 5,
    ) -> list[FinancialFactT]:
        return await search_fn(query, limit=limit)

    @staticmethod
    async def _search_latest_metric_lookup(
        query: FinancialQueryIntent,
        *,
        search_fn: SearchFn[FinancialFactT],
        limit: int = 1,
    ) -> list[FinancialFactT]:
        return await search_fn(query, limit=limit, latest_only=True)

    @staticmethod
    async def _search_compare_metric_lookup(
        query: FinancialQueryIntent,
        *,
        search_fn: SearchFn[FinancialFactT],
        display_company: DisplayTextFn[FinancialFactT],
        display_metric_name: DisplayTextFn[FinancialFactT],
        fact_year: FactYearFn[FinancialFactT],
        fact_year_sort_key_desc: FactYearSortKeyFn[FinancialFactT],
        limit: int = 5,
    ) -> list[FinancialFactT]:
        # 对比查询往往需要多拿一些候选行，再按“公司-指标-年份”去重后保留代表结果。
        company_count = max(1, len(query.companies))
        metric_count = max(1, len(query.metrics))
        year_count = max(1, len(query.years))
        search_limit = max(limit, company_count * metric_count * year_count * 3)
        facts = await search_fn(query, limit=search_limit)

        grouped: dict[tuple[str, str, int | str], FinancialFactT] = {}
        for fact in facts:
            company = display_company(fact)
            metric_name = display_metric_name(fact)
            year = fact_year(fact)
            key = (company, metric_name, year)
            grouped.setdefault(key, fact)

        sorted_facts = sorted(
            grouped.values(),
            key=lambda fact: (
                fact_year_sort_key_desc(fact),
                display_metric_name(fact),
                display_company(fact),
            ),
        )
        return sorted_facts[:limit]

    @staticmethod
    async def _search_trend_metric_lookup(
        query: FinancialQueryIntent,
        *,
        search_fn: SearchFn[FinancialFactT],
        display_company: DisplayTextFn[FinancialFactT],
        display_metric_name: DisplayTextFn[FinancialFactT],
        fact_year: FactYearFn[FinancialFactT],
        fact_year_sort_key_asc: FactYearSortKeyFn[FinancialFactT],
        limit: int = 5,
    ) -> list[FinancialFactT]:
        # 趋势查询更关注时间序列完整性，所以会优先放大按年份取回的候选集。
        year_count = max(limit, len(query.years) or limit)
        search_limit = max(limit, year_count * max(1, len(query.metrics)) * 3)
        facts = await search_fn(query, limit=search_limit)

        grouped: dict[tuple[str, str, int | str], FinancialFactT] = {}
        for fact in facts:
            company = display_company(fact)
            metric_name = display_metric_name(fact)
            year = fact_year(fact)
            key = (company, metric_name, year)
            grouped.setdefault(key, fact)

        sorted_facts = sorted(
            grouped.values(),
            key=lambda fact: (
                display_company(fact),
                display_metric_name(fact),
                fact_year_sort_key_asc(fact),
            ),
        )
        return sorted_facts[:limit]


__all__ = ["FinancialTemplateExecutor"]
