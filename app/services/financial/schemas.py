"""金融查询相关的数据结构定义。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

from app.services.financial.entity_resolver import EntityResolver


class FinancialFactExtraction(BaseModel):
    """LLM 从自然语言问题中抽取的原始结构化参数。"""

    companies: list[str] = Field(
        default_factory=list,
        description="公司名、简称或股票代码列表；简单问题通常只有一个",
    )
    years: list[int] = Field(
        default_factory=list,
        description="报告年份或财年列表，例如 [2024]、[2022, 2023, 2024]",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description="财务指标列表，例如 ['营业收入']、['营业收入', '研发费用']",
    )
    operation: Literal["lookup", "latest", "compare", "trend"] = Field(
        default="lookup",
        description="查询意图：精确查数、最新一期、公司对比、趋势查询",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="最多返回多少条结果")

    @computed_field
    @property
    def company(self) -> str:
        return self.companies[0] if self.companies else ""

    @computed_field
    @property
    def year(self) -> int | None:
        return self.years[0] if self.years else None

    @computed_field
    @property
    def metric(self) -> str:
        return self.metrics[0] if self.metrics else ""


class FinancialQueryIntent(BaseModel):
    """系统内部使用的标准化查询意图。"""

    companies: list[str] = Field(
        default_factory=list,
        description="标准化前的公司候选；后续可替换为 company_ids 等稳定实体",
    )
    years: list[int] = Field(
        default_factory=list,
        description="标准化后的年份或财年列表",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description="标准化后的指标列表",
    )
    operation: Literal["lookup", "latest", "compare", "trend"] = Field(
        default="lookup",
        description="查询意图：精确查数、最新一期、公司对比、趋势查询",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="最多返回多少条结果")
    ambiguity: list[dict[str, Any]] = Field(
        default_factory=list,
        description="标准化阶段识别出的歧义信息；当前阶段默认留空",
    )

    @computed_field
    @property
    def company(self) -> str:
        return self.companies[0] if self.companies else ""

    @computed_field
    @property
    def year(self) -> int | None:
        return self.years[0] if self.years else None

    @computed_field
    @property
    def metric(self) -> str:
        return self.metrics[0] if self.metrics else ""

    def has_template_blocking_ambiguity(self) -> bool:
        """判断当前意图是否仍然存在会阻断模板路由的歧义。"""
        return bool(self.ambiguity)

    @classmethod
    def from_extraction(
        cls,
        extraction: FinancialFactExtraction,
    ) -> FinancialQueryIntent:
        """将 LLM 抽取结果转换为当前阶段的内部查询意图。"""
        # 这里先做轻量标准化：公司和指标先归一到内部更稳定的表达，并顺手收集歧义。
        companies, company_ambiguity = EntityResolver.resolve_companies(extraction.companies)
        metrics, metric_ambiguity = EntityResolver.resolve_metrics(extraction.metrics)
        return cls(
            companies=companies,
            years=list(extraction.years),
            metrics=metrics,
            operation=extraction.operation,
            top_k=extraction.top_k,
            ambiguity=[*company_ambiguity, *metric_ambiguity],
        )


class FinancialFactQuery(FinancialQueryIntent):
    """兼容旧调用方的历史名称；后续统一迁移到 FinancialQueryIntent。"""


class FinancialSqlTemplateChoice(BaseModel):
    """模板 SQL 路径的结构化决策结果。"""

    route: Literal["template", "clarify", "sql"] = Field(
        default="sql",
        description="模板节点下一步路由：模板执行、补充信息或复杂 SQL。",
    )
    template_id: str | None = Field(
        default=None,
        description="命中的模板 ID；route=template 时必须可识别。",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="当前仍缺失的关键字段，例如 company、metric、year。",
    )
    reason: str = Field(
        default="",
        description="简短说明为何做出当前路由决策。",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="路由置信度，便于日志与后续观测。",
    )


class FinancialSqlResultRow(BaseModel):
    """统一的 SQL 查询结果行，用于格式化答案与引用。"""

    company_name: str = Field(default="未知公司")
    ticker: str = Field(default="")
    fiscal_year: int | None = Field(default=None)
    period_year: int | None = Field(default=None)
    period_label: str = Field(default="")
    metric_name: str = Field(default="未知指标")
    raw_value: str = Field(default="")
    value: str = Field(default="")
    unit: str = Field(default="")
    currency: str = Field(default="")
    source: str = Field(default="")
    page_num: int | None = Field(default=None)
    doc_id: str = Field(default="")


class GeneratedFinancialSql(BaseModel):
    """复杂查询生成的只读 SQL。"""

    sql: str = Field(default="", description="只读 SELECT SQL，必须是单条语句。")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="SQL 命名参数。",
    )
    reason: str = Field(
        default="",
        description="简述 SQL 的查询思路与口径。",
    )
    route: Literal["execute", "clarify", "sql"] = Field(
        default="execute",
        description="若信息不足则要求补充，否则执行 SQL。",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="复杂查询仍缺失的字段。",
    )

__all__ = [
    "FinancialFactExtraction",
    "FinancialFactQuery",
    "FinancialQueryIntent",
    "FinancialSqlResultRow",
    "FinancialSqlTemplateChoice",
    "GeneratedFinancialSql",
]
