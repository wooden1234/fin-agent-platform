from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func

from app.core.database import Base


class AnnualFinancialFact(Base):
    __tablename__ = "annual_financial_facts"
    __table_args__ = (
        UniqueConstraint(
            "doc_id",
            "chunk_index",
            "row_index",
            "metric_name",
            "period_label",
            name="uq_annual_financial_fact_source_metric",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Document/source metadata from annual_financial_tables.jsonl.
    doc_id = Column(String(80), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    ticker = Column(String(32), nullable=True, index=True)
    fiscal_year = Column(Integer, nullable=True, index=True)
    source = Column(String(255), nullable=False)
    page_num = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    section = Column(String(255), nullable=True)
    table_kind = Column(String(64), nullable=False, index=True)

    # Parsed table row/value fields.
    row_index = Column(Integer, nullable=False, default=0)
    statement_type = Column(String(128), nullable=True)
    metric_name = Column(String(255), nullable=False, index=True)
    metric_alias = Column(String(255), nullable=True)
    period_label = Column(String(128), nullable=True, index=True)
    period_year = Column(Integer, nullable=True, index=True)
    period_type = Column(String(64), nullable=True)
    value = Column(Numeric(24, 6), nullable=True)
    raw_value = Column(String(128), nullable=True)
    unit = Column(String(64), nullable=True)
    currency = Column(String(32), nullable=True)

    # Traceability/debug fields.
    raw_row = Column(Text, nullable=True)
    raw_table_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
