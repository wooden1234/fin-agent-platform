"""财务事实查询兼容入口。"""

from app.services.financial.fact_service import (
    FinancialFactService,
)
from app.services.financial.fact_search_executor import FinancialFactSearchExecutor
from app.services.financial.query_router import (
    FinancialQueryRouter,
    FinancialQueryTemplate,
)
from app.services.financial.schemas import (
    FinancialFactExtraction,
    FinancialFactQuery,
    FinancialQueryIntent,
)
from app.services.financial.template_executor import FinancialTemplateExecutor

__all__ = [
    "FinancialFactExtraction",
    "FinancialFactQuery",
    "FinancialFactSearchExecutor",
    "FinancialFactService",
    "FinancialTemplateExecutor",
    "FinancialQueryRouter",
    "FinancialQueryIntent",
    "FinancialQueryTemplate",
]
