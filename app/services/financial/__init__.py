"""金融领域服务的统一入口。"""

from app.services.financial.entity_resolver import EntityResolver
from app.services.financial.fact_search_executor import FinancialFactSearchExecutor
from app.services.financial.fact_service import (
    FinancialFactService,
)
from app.services.financial.query_router import (
    FinancialQueryRouter,
    FinancialQueryTemplate,
)
from app.services.financial.schemas import (
    FinancialFactExtraction,
    FinancialFactQuery,
    FinancialSqlResultRow,
    FinancialSqlTemplateChoice,
    GeneratedFinancialSql,
    FinancialQueryIntent,
)
from app.services.financial.sql_executor import FinancialSqlExecutor, SqlValidationError
from app.services.financial.sql_templates import FinancialSqlTemplateRegistry
from app.services.financial.template_executor import FinancialTemplateExecutor

__all__ = [
    "EntityResolver",
    "FinancialFactExtraction",
    "FinancialFactQuery",
    "FinancialFactSearchExecutor",
    "FinancialFactService",
    "FinancialSqlExecutor",
    "FinancialSqlResultRow",
    "FinancialSqlTemplateChoice",
    "FinancialSqlTemplateRegistry",
    "FinancialTemplateExecutor",
    "GeneratedFinancialSql",
    "FinancialQueryRouter",
    "FinancialQueryIntent",
    "FinancialQueryTemplate",
    "SqlValidationError",
]
