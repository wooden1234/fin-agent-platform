"""FinancialQueryRouter 单元测试。"""

from app.services.financial import FinancialFactQuery, FinancialQueryRouter


def test_router_match_template_exact_lookup():
    template = FinancialQueryRouter.match_template(
        "宁德时代 2024 年营业收入是多少？",
        FinancialFactQuery(
            companies=["宁德时代"],
            years=[2024],
            metrics=["营业收入"],
        ),
    )

    assert template is not None
    assert template.name == "exact_metric_lookup"


def test_router_match_template_latest_lookup():
    template = FinancialQueryRouter.match_template(
        "宁德时代最新营收是多少？",
        FinancialFactQuery(
            companies=["宁德时代"],
            metrics=["营业收入"],
            operation="latest",
            top_k=1,
        ),
    )

    assert template is not None
    assert template.name == "latest_metric_lookup"


def test_router_generic_search_needs_clarification_on_ambiguity():
    route = FinancialQueryRouter.route_generic_search(
        FinancialFactQuery(
            companies=["宁德"],
            metrics=["利润"],
            ambiguity=[{"entity_type": "metric", "input": "利润"}],
        )
    )

    assert route == FinancialQueryRouter.NEEDS_CLARIFICATION_ROUTE


def test_router_generic_search_allows_low_risk_lookup():
    route = FinancialQueryRouter.route_generic_search(
        FinancialFactQuery(
            companies=["宁德时代"],
            metrics=["营业收入"],
        )
    )

    assert route == FinancialQueryRouter.SAFE_GENERIC_SEARCH_ROUTE


def test_router_generic_search_falls_back_to_text_to_sql():
    route = FinancialQueryRouter.route_generic_search(
        FinancialFactQuery(
            companies=[],
            metrics=["营业收入"],
        )
    )

    assert route == FinancialQueryRouter.TEXT_TO_SQL_FALLBACK_ROUTE
