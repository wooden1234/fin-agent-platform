"""text_to_sql 子图内部状态。"""

from __future__ import annotations

from typing import Any, NotRequired
from typing_extensions import Literal, TypedDict

from app.agents.components.finance_agent.financial_query_agent.services.schemas import FinancialSqlResultRow


class TextToSqlState(TypedDict):
    """text_to_sql 子图在重试循环中使用的局部状态。"""

    question: str
    schema_prompt: NotRequired[str]
    fewshot_examples: NotRequired[str]
    top_k: NotRequired[int]
    max_attempts: NotRequired[int]
    sql: NotRequired[str]
    sql_params: NotRequired[dict[str, Any]]
    route_reason: NotRequired[str]
    missing_fields: NotRequired[list[str]]
    validated_sql: NotRequired[str]
    validation_error: NotRequired[str]
    validation_errors: NotRequired[list[str]]
    next_step: NotRequired[Literal["validate", "correct", "execute", "end"]]
    attempts: NotRequired[int]
    rows: NotRequired[list[FinancialSqlResultRow]]
    execution_error: NotRequired[str]
    halted: NotRequired[bool]
    halt_reason: NotRequired[str]
    halt_answer: NotRequired[str]


__all__ = ["TextToSqlState"]
