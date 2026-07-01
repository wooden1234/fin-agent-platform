"""FinancialTemplateExecutor 单元测试。"""

from dataclasses import dataclass

import pytest

from app.services.financial import (
    FinancialFactQuery,
    FinancialQueryRouter,
    FinancialTemplateExecutor,
)


@dataclass
class _Fact:
    company: str
    metric: str
    year: int
    value: int


def _display_company(fact: _Fact) -> str:
    return fact.company


def _display_metric_name(fact: _Fact) -> str:
    return fact.metric


def _fact_year(fact: _Fact) -> int:
    return fact.year


def _fact_year_sort_key_desc(fact: _Fact) -> tuple[int, int]:
    return (0, -fact.year)


def _fact_year_sort_key_asc(fact: _Fact) -> tuple[int, int]:
    return (0, fact.year)


async def _run_template(template_name: str, facts: list[_Fact], query: FinancialFactQuery):
    calls: list[dict] = []

    async def search_fn(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return facts

    result = await FinancialTemplateExecutor.run_template(
        getattr(FinancialQueryRouter, template_name),
        query,
        search_fn=search_fn,
        display_company=_display_company,
        display_metric_name=_display_metric_name,
        fact_year=_fact_year,
        fact_year_sort_key_desc=_fact_year_sort_key_desc,
        fact_year_sort_key_asc=_fact_year_sort_key_asc,
        limit=2,
    )
    return result, calls


@pytest.mark.asyncio
async def test_latest_template_passes_latest_only_to_search():
    query = FinancialFactQuery(companies=["宁德时代"], metrics=["营业收入"])
    facts = [_Fact("宁德时代", "营业收入", 2024, 1)]

    result, calls = await _run_template("LATEST_LOOKUP_TEMPLATE", facts, query)

    assert result == facts
    assert calls[0]["kwargs"] == {"limit": 2, "latest_only": True}


@pytest.mark.asyncio
async def test_compare_template_dedupes_and_sorts_latest_first():
    query = FinancialFactQuery(
        companies=["宁德时代", "腾讯"],
        years=[2023, 2024],
        metrics=["营业收入"],
    )
    facts = [
        _Fact("腾讯", "营业收入", 2023, 1),
        _Fact("宁德时代", "营业收入", 2024, 1),
        _Fact("宁德时代", "营业收入", 2024, 2),
        _Fact("腾讯", "营业收入", 2024, 1),
    ]

    result, calls = await _run_template("COMPARE_LOOKUP_TEMPLATE", facts, query)

    assert result == [
        _Fact("宁德时代", "营业收入", 2024, 1),
        _Fact("腾讯", "营业收入", 2024, 1),
    ]
    assert calls[0]["kwargs"]["limit"] == 12


@pytest.mark.asyncio
async def test_trend_template_dedupes_and_sorts_year_ascending():
    query = FinancialFactQuery(
        companies=["宁德时代"],
        years=[2022, 2023, 2024],
        metrics=["营业收入"],
    )
    facts = [
        _Fact("宁德时代", "营业收入", 2024, 1),
        _Fact("宁德时代", "营业收入", 2022, 1),
        _Fact("宁德时代", "营业收入", 2022, 2),
        _Fact("宁德时代", "营业收入", 2023, 1),
    ]

    result, calls = await _run_template("TREND_LOOKUP_TEMPLATE", facts, query)

    assert result == [
        _Fact("宁德时代", "营业收入", 2022, 1),
        _Fact("宁德时代", "营业收入", 2023, 1),
    ]
    assert calls[0]["kwargs"]["limit"] == 9
