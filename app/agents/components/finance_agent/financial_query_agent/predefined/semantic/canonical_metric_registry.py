"""canonical metric registry：用户指标语义 -> 统一 canonical -> 公司级 source metric。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.agents.components.finance_agent.financial_query_agent.predefined.intent import (
    FinancialQueryIntent,
)
from app.agents.components.finance_agent.financial_query_agent.predefined.semantic.company_resolver import (
    CompanyResolver,
    ResolvedCompany,
)
from app.agents.components.finance_agent.financial_query_agent.predefined.semantic.models import (
    CanonicalMetricMatch,
    CompanyMetricMatch,
)
from app.agents.components.finance_agent.financial_query_agent.predefined.semantic.registry_seed import (
    CANONICAL_METRICS,
    COMPANY_OVERRIDES,
    company_metric_names,
    resolve_canonical_code,
)
from app.agents.components.finance_agent.financial_query_agent.services.entity_resolver import (
    EntityResolver,
)
from app.core.database import AsyncSessionLocal
from app.models.annual_financial_fact import (
    AnnualFinancialFact,
    AnnualFinancialTable,
    AnnualReportDocument,
    FinancialMetric,
)


class CanonicalMetricRegistry:
    """将用户说法标准化成统一财务语义，再映射到公司级可查询指标。"""

    @classmethod
    async def resolve(
        cls,
        intent: FinancialQueryIntent,
        *,
        companies_by_canonical: dict[str, ResolvedCompany] | None = None,
    ) -> list[CanonicalMetricMatch]:
        companies = intent.companies or [""]
        companies_by_canonical = companies_by_canonical or await CompanyResolver.resolve_by_canonical(
            intent.companies
        )
        matches: list[CanonicalMetricMatch] = []
        for requested_metric in intent.metrics:
            canonical_code = resolve_canonical_code(requested_metric)
            if not canonical_code:
                matches.append(
                    CanonicalMetricMatch(
                        canonical_metric_code="",
                        canonical_metric_name="",
                        requested_metric=requested_metric,
                        company_metric_matches=[],
                    )
                )
                continue
            definition = CANONICAL_METRICS[canonical_code]
            company_matches: list[CompanyMetricMatch] = []
            for company in companies:
                company_key = EntityResolver._canonical_company(company) if company else ""
                resolved_company = companies_by_canonical.get(company_key)
                metric_names = company_metric_names(company_key, canonical_code)
                has_override = bool(
                    company_key
                    and canonical_code in COMPANY_OVERRIDES.get(company_key, {})
                )
                resolved = await cls._resolve_company_metric(
                    company_key=company_key,
                    company_id=resolved_company.company_id if resolved_company else None,
                    metric_names=metric_names,
                    has_override=has_override,
                )
                if resolved is not None:
                    company_matches.append(resolved)
            matches.append(
                CanonicalMetricMatch(
                    canonical_metric_code=canonical_code,
                    canonical_metric_name=definition.name,
                    requested_metric=requested_metric,
                    company_metric_matches=company_matches,
                )
            )
        return matches

    @classmethod
    async def _resolve_company_metric(
        cls,
        *,
        company_key: str,
        company_id: int | None,
        metric_names: list[str],
        has_override: bool,
    ) -> CompanyMetricMatch | None:
        if not metric_names:
            return None
        metric_id, metric_name = await cls._lookup_metric_id(
            company_id=company_id,
            metric_names=metric_names,
        )
        if metric_id is None:
            return CompanyMetricMatch(
                company_key=company_key,
                company_id=company_id,
                metric_id=None,
                metric_name=metric_names[0],
                match_type="company_override" if has_override else "global_alias",
                confidence=0.0,
            )
        return CompanyMetricMatch(
            company_key=company_key,
            company_id=company_id,
            metric_id=metric_id,
            metric_name=metric_name,
            match_type="company_override" if has_override else "global_alias",
            confidence=0.98 if has_override else 0.95,
        )

    @classmethod
    async def _lookup_metric_id(
        cls,
        *,
        company_id: int | None,
        metric_names: list[str],
    ) -> tuple[int | None, str]:
        lowered_names = [name.lower() for name in metric_names if name.strip()]
        if not lowered_names:
            return None, ""

        async with AsyncSessionLocal() as session:
            if company_id is not None:
                exact_id, exact_name = await cls._lookup_metric_for_company(
                    session,
                    company_id=company_id,
                    lowered_names=lowered_names,
                    metric_names=metric_names,
                    exact_only=True,
                )
                if exact_id is not None:
                    return exact_id, exact_name

                fuzzy_id, fuzzy_name = await cls._lookup_metric_for_company(
                    session,
                    company_id=company_id,
                    lowered_names=lowered_names,
                    metric_names=metric_names,
                    exact_only=False,
                )
                if fuzzy_id is not None:
                    return fuzzy_id, fuzzy_name
                return None, metric_names[0]

            stmt = (
                select(FinancialMetric.id, FinancialMetric.canonical_name)
                .where(func.lower(FinancialMetric.canonical_name).in_(lowered_names))
                .limit(1)
            )
            row = (await session.execute(stmt)).first()
            if row is not None:
                return row.id, row.canonical_name
        return None, metric_names[0]

    @staticmethod
    async def _lookup_metric_for_company(
        session,
        *,
        company_id: int,
        lowered_names: list[str],
        metric_names: list[str],
        exact_only: bool,
    ) -> tuple[int | None, str | None]:
        base = (
            select(FinancialMetric.id, FinancialMetric.canonical_name)
            .join(AnnualFinancialFact, AnnualFinancialFact.metric_id == FinancialMetric.id)
            .join(AnnualFinancialTable, AnnualFinancialTable.id == AnnualFinancialFact.table_id)
            .join(AnnualReportDocument, AnnualReportDocument.id == AnnualFinancialTable.document_id)
            .where(AnnualReportDocument.company_id == company_id)
        )
        if exact_only:
            stmt = base.where(func.lower(FinancialMetric.canonical_name).in_(lowered_names)).limit(1)
            row = (await session.execute(stmt)).first()
            return (row.id, row.canonical_name) if row is not None else (None, None)

        for name in metric_names:
            stmt = base.where(
                func.lower(FinancialMetric.canonical_name).like(f"%{name.lower()}%")
            ).limit(1)
            row = (await session.execute(stmt)).first()
            if row is not None:
                return row.id, row.canonical_name
        return None, None


__all__ = ["CanonicalMetricRegistry"]
