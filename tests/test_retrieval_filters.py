from app.retrieval.filters import infer_pdf_metadata_filters, metadata_matches


def test_infer_pdf_metadata_filters_for_annual_report_query():
    filters = infer_pdf_metadata_filters("宁德时代2024年年报营业收入是多少？")

    assert filters["category"] == "annual_reports"
    assert filters["company"] == "CATL"
    assert filters["year"] == 2024


def test_metadata_matches_company_year_and_category():
    metadata = {
        "category": "annual_reports",
        "title": "CATL Annual Report 2024",
        "source": "CATL_Annual_Report_2024.pdf",
        "ticker": "CATL",
        "fiscal_year": 2024,
    }

    assert metadata_matches(
        metadata,
        {"category": "annual_reports", "company": "宁德时代", "year": 2024},
    )
    assert not metadata_matches(metadata, {"company": "腾讯"})


def test_metadata_matches_source_substring():
    metadata = {
        "category": "policy",
        "title": "Artificial Intelligence Policy",
        "source": "Artificial_Intelligence_Policy.pdf",
        "doc_id": "PDF-POL-04",
    }

    assert metadata_matches(metadata, {"source": "Artificial_Intelligence"})
    assert metadata_matches(metadata, {"doc_id": "PDF-POL-04"})
