"""FinancialFactService 单元测试（无 DB 依赖部分）。"""

from decimal import Decimal
from types import SimpleNamespace

from app.services.financial import (
    FinancialFactQuery,
    FinancialFactService,
    FinancialSqlResultRow,
)


def _fact(**kwargs):
    defaults = {
        "title": "CATL Annual Report 2024",
        "ticker": "300750",
        "fiscal_year": 2024,
        "period_year": 2024,
        "metric_name": "营业收入",
        "raw_value": "362,012,554",
        "value": Decimal("362012554"),
        "unit": "千元",
        "currency": "人民币",
        "source": "CATL_Annual_Report_2024.pdf",
        "page_num": 12,
        "doc_id": "PDF-AR-CATL-2024",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_resolve_company_terms_aliases():
    catl_terms = FinancialFactService.resolve_company_terms("宁德时代")
    tencent_terms = FinancialFactService.resolve_company_terms("腾讯")

    assert catl_terms[0] == "CATL"
    assert "宁德时代" in catl_terms
    assert tencent_terms[0] == "Tencent"
    assert "腾讯" in tencent_terms


def test_resolve_metric_terms_aliases():
    terms = FinancialFactService.resolve_metric_terms("营收")
    assert "营业收入" in terms


def test_format_answer_single_fact():
    answer = FinancialFactService.format_answer([_fact()])
    assert "CATL" in answer
    assert "2024" in answer
    assert "营业收入" in answer
    assert "362,012,554" in answer


def test_format_answer_empty():
    answer = FinancialFactService.format_answer([])
    assert "未找到" in answer


def test_to_citations():
    citations = FinancialFactService.to_citations([_fact()])
    assert len(citations) == 1
    assert citations[0]["source"] == "CATL_Annual_Report_2024.pdf"
    assert citations[0]["page"] == 12


def test_format_sql_answer_single_row():
    row = FinancialSqlResultRow(
        company_name="宁德时代",
        fiscal_year=2024,
        period_year=2024,
        metric_name="营业收入",
        raw_value="362,012,554",
        unit="千元",
        currency="人民币",
        source="CATL_Annual_Report_2024.pdf",
        page_num=12,
    )

    answer = FinancialFactService.format_sql_answer([row])
    assert "宁德时代" in answer
    assert "营业收入" in answer
    assert "362,012,554" in answer


def test_sql_rows_to_citations():
    row = FinancialSqlResultRow(
        company_name="宁德时代",
        metric_name="营业收入",
        raw_value="362,012,554",
        unit="千元",
        source="CATL_Annual_Report_2024.pdf",
        page_num=12,
    )

    citations = FinancialFactService.sql_rows_to_citations([row])
    assert citations[0]["source"] == "CATL_Annual_Report_2024.pdf"
    assert citations[0]["page"] == 12


def test_match_template_exact_lookup():
    template = FinancialFactService.match_template(
        "宁德时代 2024 年营业收入是多少？",
        FinancialFactQuery(
            companies=["宁德时代"],
            years=[2024],
            metrics=["营业收入"],
        ),
    )
    assert template is not None
    assert template.name == "exact_metric_lookup"


def test_match_template_latest_lookup():
    template = FinancialFactService.match_template(
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


def test_query_backward_compatible_properties():
    query = FinancialFactQuery(
        companies=["宁德时代", "腾讯"],
        years=[2024, 2023],
        metrics=["营业收入", "研发费用"],
    )
    assert query.company == "宁德时代"
    assert query.year == 2024
    assert query.metric == "营业收入"
