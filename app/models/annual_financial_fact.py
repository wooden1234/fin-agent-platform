from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class FinancialCompany(Base):
    """Normalized company dimension for annual-report facts."""

    __tablename__ = "financial_companies"
    __table_args__ = {"schema": "fin_core"}

    id = Column(Integer, primary_key=True, index=True)
    # 公司规范化唯一标识，用于合并别名和跨文档归一。
    company_key = Column(String(255), nullable=False, unique=True, index=True)
    # 公司展示名称。
    name = Column(String(255), nullable=False, index=True)
    # 股票代码；部分文档源可能缺失，因此允许为空。
    ticker = Column(String(32), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    documents = relationship("AnnualReportDocument", back_populates="company")


class AnnualReportDocument(Base):
    """Annual report document metadata split out of fact rows."""

    __tablename__ = "annual_report_documents"
    __table_args__ = {"schema": "fin_core"}

    id = Column(Integer, primary_key=True, index=True)
    # 外部文档唯一标识，用于和原始解析产物稳定对齐。
    doc_id = Column(String(80), nullable=False, unique=True, index=True)
    # 所属公司主键；未完成归属时允许为空。
    company_id = Column(
        Integer,
        ForeignKey("fin_core.financial_companies.id"),
        nullable=True,
        index=True,
    )
    # 文档标题，通常是年报名称。
    title = Column(String(255), nullable=False)
    # 文档对应财年。
    fiscal_year = Column(Integer, nullable=True, index=True)
    # 原始文件名或来源标识，便于追溯。
    source = Column(String(255), nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("FinancialCompany", back_populates="documents")
    tables = relationship("AnnualFinancialTable", back_populates="document")


class AnnualFinancialTable(Base):
    """Table/chunk context shared by many extracted financial facts."""

    __tablename__ = "annual_financial_tables"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_annual_financial_table_document_chunk",
        ),
        {"schema": "fin_core"},
    )

    id = Column(Integer, primary_key=True, index=True)
    # 所属年报文档主键。
    document_id = Column(
        Integer,
        ForeignKey("fin_core.annual_report_documents.id"),
        nullable=False,
        index=True,
    )
    # 文档内表格分块序号，用于保证定位稳定。
    chunk_index = Column(Integer, nullable=False)
    # 表格所在页码。
    page_num = Column(Integer, nullable=True)
    # 表格所在章节或标题。
    section = Column(String(255), nullable=True)
    # 表格类别，如利润表、资产负债表、现金流量表。
    table_kind = Column(String(64), nullable=False, index=True)
    # 原始表格文本，便于回溯抽取上下文。
    raw_table_text = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    document = relationship("AnnualReportDocument", back_populates="tables")
    facts = relationship("AnnualFinancialFact", back_populates="table")


class FinancialMetric(Base):
    """Canonical financial metric dictionary."""

    __tablename__ = "financial_metrics"
    __table_args__ = {"schema": "fin_core"}

    id = Column(Integer, primary_key=True, index=True)
    # 指标规范名，作为统一查询口径。
    canonical_name = Column(String(255), nullable=False, unique=True, index=True)
    # 指标别名集合，便于查询阶段做归一。
    aliases = Column(String(512), nullable=True)
    # 指标所属报表类型，用于缩小匹配范围。
    statement_type = Column(String(128), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    facts = relationship("AnnualFinancialFact", back_populates="metric")


class AnnualFinancialFact(Base):
    """Narrow fact table: one metric value for one period in one source table."""

    __tablename__ = "annual_financial_facts"
    __table_args__ = (
        UniqueConstraint(
            "table_id",
            "row_index",
            "metric_id",
            "period_label",
            name="uq_annual_financial_fact_source_metric",
        ),
        {"schema": "fin_core"},
    )

    id = Column(Integer, primary_key=True, index=True)
    # 来源财务表主键。
    table_id = Column(
        Integer,
        ForeignKey("fin_core.annual_financial_tables.id"),
        nullable=False,
        index=True,
    )
    # 对应指标主键。
    metric_id = Column(
        Integer,
        ForeignKey("fin_core.financial_metrics.id"),
        nullable=False,
        index=True,
    )

    # 指标所在原始表行序号，用于区分同表内多行事实。
    row_index = Column(Integer, nullable=False, default=0)
    # 原始期间标签，如“2024年”“本期”“上年同期”。
    period_label = Column(String(128), nullable=True, index=True)
    # 标准化后的年份，便于结构化筛选。
    period_year = Column(Integer, nullable=True, index=True)
    # 期间类型，如 annual、quarterly；主要用于清洗和过滤。
    period_type = Column(String(64), nullable=True)
    # 标准化后的数值结果，便于排序和计算。
    value = Column(Numeric(24, 6), nullable=True)
    # 原始文本值，保留展示口径和人工核对依据。
    raw_value = Column(String(128), nullable=True)
    # 数值单位，如元、万元、千元。
    unit = Column(String(64), nullable=True)
    # 币种信息，如人民币、美元。
    currency = Column(String(32), nullable=True)
    # 原始整行文本，便于回溯抽取上下文。
    raw_row = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    table = relationship("AnnualFinancialTable", back_populates="facts")
    metric = relationship("FinancialMetric", back_populates="facts")
