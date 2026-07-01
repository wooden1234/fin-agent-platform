"""FinancialSqlExecutor 单元测试。"""

import pytest

from app.services.financial.sql_executor import FinancialSqlExecutor, SqlValidationError


def test_validate_readonly_sql_accepts_financial_select():
    sql = """
    SELECT company.name
    FROM fin_core.financial_companies AS company
    LIMIT :limit
    """

    validated = FinancialSqlExecutor.validate_readonly_sql(sql)
    assert validated.lower().startswith("select")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE fin_core.financial_companies SET name = 'x'",
        "SELECT * FROM fin_core.financial_companies; DELETE FROM fin_core.financial_metrics",
        "SELECT * FROM public.users",
    ],
)
def test_validate_readonly_sql_rejects_unsafe_or_non_whitelist_sql(sql: str):
    with pytest.raises(SqlValidationError):
        FinancialSqlExecutor.validate_readonly_sql(sql)
