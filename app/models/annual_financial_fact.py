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

    id = Column(Integer, primary_key=True, index=True)
    company_key = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    ticker = Column(String(32), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    documents = relationship("AnnualReportDocument", back_populates="company")


class AnnualReportDocument(Base):
    """Annual report document metadata split out of fact rows."""

    __tablename__ = "annual_report_documents"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String(80), nullable=False, unique=True, index=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    fiscal_year = Column(Integer, nullable=True, index=True)
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
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("annual_report_documents.id"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    page_num = Column(Integer, nullable=True)
    section = Column(String(255), nullable=True)
    table_kind = Column(String(64), nullable=False, index=True)
    raw_table_text = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    document = relationship("AnnualReportDocument", back_populates="tables")
    facts = relationship("AnnualFinancialFact", back_populates="table")


class FinancialMetric(Base):
    """Canonical financial metric dictionary."""

    __tablename__ = "financial_metrics"

    id = Column(Integer, primary_key=True, index=True)
    canonical_name = Column(String(255), nullable=False, unique=True, index=True)
    aliases = Column(String(512), nullable=True)
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
    )

    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("annual_financial_tables.id"), nullable=False, index=True)
    metric_id = Column(Integer, ForeignKey("financial_metrics.id"), nullable=False, index=True)

    row_index = Column(Integer, nullable=False, default=0)
    period_label = Column(String(128), nullable=True, index=True)
    period_year = Column(Integer, nullable=True, index=True)
    period_type = Column(String(64), nullable=True)
    value = Column(Numeric(24, 6), nullable=True)
    raw_value = Column(String(128), nullable=True)
    unit = Column(String(64), nullable=True)
    currency = Column(String(32), nullable=True)
    raw_row = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    table = relationship("AnnualFinancialTable", back_populates="facts")
    metric = relationship("FinancialMetric", back_populates="facts")
