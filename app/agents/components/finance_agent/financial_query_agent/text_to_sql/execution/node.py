"""text_to_sql 执行与结果整理节点。"""

from __future__ import annotations

from typing import Any

from app.agents.components.finance_agent.financial_query_agent.services.fact_service import FinancialFactService
from app.agents.components.finance_agent.financial_query_agent.services.schemas import FinancialSqlResultRow


async def execute_generated_sql(
    sql: str,
    *,
    params: dict[str, Any] | None = None,
    limit: int = 5,
) -> list[FinancialSqlResultRow]:
    """执行已通过校验的 SQL，不在这里承担生成与修正逻辑。"""
    return await FinancialFactService.run_generated_sql(
        sql,
        params=params,
        limit=limit,
    )


def format_sql_rows(rows: list[FinancialSqlResultRow]) -> str:
    """统一封装 SQL 结果格式化，结构化查询只返回答案。"""
    if not rows:
        return "（数据库中未找到匹配的财务指标，建议改查 PDF 文档库。）"
    return FinancialFactService.format_sql_answer(rows)


__all__ = ["execute_generated_sql", "format_sql_rows"]
