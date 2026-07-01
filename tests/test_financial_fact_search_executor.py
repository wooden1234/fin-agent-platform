"""FinancialFactSearchExecutor 接线测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.financial import FinancialFactQuery, FinancialFactService


@pytest.mark.asyncio
async def test_fact_service_search_delegates_to_fact_search_executor():
    query = FinancialFactQuery(companies=["宁德时代"], metrics=["营业收入"])

    with patch(
        "app.services.financial.fact_service.FinancialFactSearchExecutor.search",
        new=AsyncMock(return_value=["fact"]),
    ) as search_mock:
        result = await FinancialFactService.search(query, limit=3)

    assert result == ["fact"]
    search_mock.assert_awaited_once_with(query, limit=3)


@pytest.mark.asyncio
async def test_fact_service_search_base_keeps_compatibility_wrapper():
    query = FinancialFactQuery(companies=["宁德时代"], metrics=["营业收入"])

    with patch(
        "app.services.financial.fact_service.FinancialFactSearchExecutor.search",
        new=AsyncMock(return_value=["fact"]),
    ) as search_mock:
        result = await FinancialFactService._search_base(
            query,
            limit=2,
            latest_only=True,
        )

    assert result == ["fact"]
    search_mock.assert_awaited_once_with(
        query,
        limit=2,
        latest_only=True,
    )
