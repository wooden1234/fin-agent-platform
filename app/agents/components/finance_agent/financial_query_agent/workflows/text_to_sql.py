"""text_to_sql workflow 适配层。"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.states import FinAgentState
from app.agents.components.finance_agent.financial_query_agent.common import (
    financial_query_output,
    query_from_state,
)
from app.agents.components.finance_agent.financial_query_agent.text_to_sql import (
    build_fewshot_examples,
    build_schema_prompt,
    correct_sql,
    default_middleware_chain,
    execute_generated_sql,
    format_sql_rows,
    generate_sql,
    validate_generated_sql,
)
from app.agents.components.finance_agent.financial_query_agent.text_to_sql.middleware import (
    halt_updates,
)
from app.agents.components.finance_agent.financial_query_agent.text_to_sql.state import (
    TextToSqlState,
)
from app.core.logger import get_logger

logger = get_logger(service="financial_query")

DEFAULT_TEXT_TO_SQL_TOP_K = 5
DEFAULT_TEXT_TO_SQL_MAX_ATTEMPTS = 3
FINANCIAL_QUERY_SQL_UNSAFE_ANSWER = (
    "当前问题需要生成 SQL，但生成结果未通过只读安全校验。请补充更具体的查询条件后重试。"
)
FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER = (
    "当前问题超出安全模板和低风险通用搜索范围，建议回退到更灵活的查询规划，例如 text-to-SQL，或先将问题拆得更具体。"
)

_MIDDLEWARE_CHAIN = default_middleware_chain()


async def _run_text_to_sql(question: str, config: RunnableConfig = None) -> dict:
    state: TextToSqlState = {
        "question": question,
        "schema_prompt": build_schema_prompt(),
        "fewshot_examples": build_fewshot_examples(question),
        "top_k": DEFAULT_TEXT_TO_SQL_TOP_K,
        "max_attempts": DEFAULT_TEXT_TO_SQL_MAX_ATTEMPTS,
        "attempts": 0,
    }

    current_state, halt_result = await _MIDDLEWARE_CHAIN.run_before_generate(state, config)
    if halt_result:
        return {**current_state, **halt_updates(halt_result)}

    generated = await generate_sql(
        current_state["question"],
        schema_prompt=current_state["schema_prompt"],
        fewshot_examples=current_state["fewshot_examples"],
        config=config,
    )
    halt_result = await _MIDDLEWARE_CHAIN.run_after_generate(current_state, generated, config)
    if halt_result:
        return {**current_state, **halt_updates(halt_result)}

    current_state.update(
        {
            "sql": generated.sql,
            "sql_params": generated.params,
            "route_reason": generated.reason,
            "missing_fields": generated.missing_fields,
        }
    )

    while True:
        attempts = int(current_state.get("attempts", 0)) + 1
        validation = validate_generated_sql(current_state.get("sql", ""))
        validation_errors = [validation.error] if validation.error else []
        current_state.update(
            {
                "attempts": attempts,
                "validated_sql": validation.validated_sql,
                "validation_error": validation.error,
                "validation_errors": validation_errors,
            }
        )
        if validation.ok:
            break
        if attempts >= int(current_state.get("max_attempts", DEFAULT_TEXT_TO_SQL_MAX_ATTEMPTS)):
            return current_state

        corrected = await correct_sql(
            current_state["question"],
            schema_prompt=current_state["schema_prompt"],
            fewshot_examples=current_state["fewshot_examples"],
            sql=current_state.get("sql", ""),
            params=current_state.get("sql_params", {}),
            validation_errors=validation_errors,
            config=config,
        )
        halt_result = await _MIDDLEWARE_CHAIN.run_after_correct(current_state, corrected, config)
        if halt_result:
            return {**current_state, **halt_updates(halt_result)}

        current_state.update(
            {
                "sql": corrected.sql,
                "sql_params": corrected.params,
                "route_reason": corrected.reason,
                "missing_fields": corrected.missing_fields,
            }
        )

    try:
        rows = await execute_generated_sql(
            current_state.get("validated_sql", "") or current_state.get("sql", ""),
            params=current_state.get("sql_params", {}),
            limit=int(current_state.get("top_k", DEFAULT_TEXT_TO_SQL_TOP_K)),
        )
        current_state["rows"] = rows
        current_state["execution_error"] = ""
    except Exception:
        logger.exception("text_to_sql_workflow execution failed")
        current_state["rows"] = []
        current_state["execution_error"] = "sql_execution_failed"
    return current_state


async def text_to_sql_workflow(
    state: FinAgentState,
    config: RunnableConfig = None,
) -> dict:
    """复杂查询工作流适配层。"""
    question = str(state.get("financial_query_text") or query_from_state(state)).strip()
    result = await _run_text_to_sql(question, config)

    base_updates = {
        "financial_query_text": question,
        "financial_query_schema_prompt": str(result.get("schema_prompt", "")),
        "financial_query_fewshot_examples": str(result.get("fewshot_examples", "")),
        "financial_query_sql_attempts": int(result.get("attempts", 0)),
        "financial_query_sql": str(result.get("sql", "")),
        "financial_query_sql_params": dict(result.get("sql_params", {})),
        "financial_query_validated_sql": str(result.get("validated_sql", "")),
        "financial_query_validation_error": str(result.get("validation_error", "")),
        "financial_query_validation_errors": list(result.get("validation_errors", [])),
        "financial_query_missing_fields": list(result.get("missing_fields", [])),
        "financial_query_plan_reason": str(result.get("route_reason", "")),
    }

    if bool(result.get("halted")) and str(result.get("halt_reason", "")) == "clarify":
        answer = str(result.get("halt_answer", "")) or "请补充更明确的公司名称、财务指标或统计年份后，我再继续生成查询。"
        return {
            **base_updates,
            **financial_query_output(state, answer=answer, step="text_to_sql"),
            "financial_query_next_action_sql": "clarify",
        }

    if str(result.get("validation_error", "")):
        return {
            **base_updates,
            **financial_query_output(
                state,
                answer=FINANCIAL_QUERY_SQL_UNSAFE_ANSWER,
                step="text_to_sql",
            ),
            "financial_query_next_action_sql": "end",
        }

    if str(result.get("execution_error", "")):
        return {
            **base_updates,
            **financial_query_output(
                state,
                answer=FINANCIAL_QUERY_TEXT_TO_SQL_FALLBACK_ANSWER,
                step="text_to_sql",
            ),
            "financial_query_next_action_sql": "end",
        }

    answer = format_sql_rows(list(result.get("rows", [])))
    return {
        **base_updates,
        **financial_query_output(
            state,
            answer=answer,
            step="text_to_sql",
        ),
        "financial_query_next_action_sql": "execute",
    }


__all__ = [
    "correct_sql",
    "execute_generated_sql",
    "generate_sql",
    "text_to_sql_workflow",
]
