"""text_to_sql 校验节点。"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.components.finance_agent.financial_query_agent.services.sql_executor import FinancialSqlExecutor, SqlValidationError


@dataclass(frozen=True)
class SqlValidationResult:
    validated_sql: str
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def validate_generated_sql(sql: str) -> SqlValidationResult:
    """当前先复用白名单校验，后续可在此叠加语义与 Schema 校验。"""
    try:
        validated_sql = FinancialSqlExecutor.validate_readonly_sql(sql)
        return SqlValidationResult(validated_sql=validated_sql)
    except SqlValidationError as exc:
        return SqlValidationResult(validated_sql="", error=str(exc))


__all__ = ["SqlValidationResult", "validate_generated_sql"]
