"""Import annual financial facts JSONL/CSV into PostgreSQL.

Usage:
    python scripts/init_db.py
    python scripts/import_annual_financial_facts.py
    python scripts/import_annual_financial_facts.py --input knowledge/cleaned/annual_financial_facts.csv
    python scripts/import_annual_financial_facts.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.logger import get_logger  # noqa: E402
from app.models.annual_financial_fact import AnnualFinancialFact  # noqa: E402


DEFAULT_INPUT = ROOT_DIR / "knowledge" / "cleaned" / "annual_financial_facts.jsonl"
UPSERT_KEY = ("doc_id", "chunk_index", "row_index", "metric_name", "period_label")

logger = get_logger(service="import_annual_financial_facts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import annual financial facts JSONL/CSV")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count rows without writing to the database",
    )
    return parser.parse_args()


def none_if_blank(value: Any) -> Any:
    return None if value == "" else value


def to_int(value: Any) -> int | None:
    value = none_if_blank(value)
    if value is None:
        return None
    return int(value)


def to_decimal(value: Any) -> Decimal | None:
    value = none_if_blank(value)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def row_from_obj(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": obj.get("doc_id") or "",
        "title": obj.get("title") or "",
        "ticker": none_if_blank(obj.get("ticker")),
        "fiscal_year": to_int(obj.get("fiscal_year")),
        "source": obj.get("source") or "",
        "page_num": to_int(obj.get("page_num")),
        "chunk_index": int(obj.get("chunk_index")),
        "section": none_if_blank(obj.get("section")),
        "table_kind": obj.get("table_kind") or "financial_other",
        "row_index": int(obj.get("row_index")),
        "statement_type": none_if_blank(obj.get("statement_type")),
        "metric_name": obj.get("metric_name") or "",
        "metric_alias": none_if_blank(obj.get("metric_alias")),
        "period_label": none_if_blank(obj.get("period_label")),
        "period_year": to_int(obj.get("period_year")),
        "period_type": none_if_blank(obj.get("period_type")),
        "value": to_decimal(obj.get("value")),
        "raw_value": none_if_blank(obj.get("raw_value")),
        "unit": none_if_blank(obj.get("unit")),
        "currency": none_if_blank(obj.get("currency")),
        "raw_row": none_if_blank(obj.get("raw_row")),
        "raw_table_text": none_if_blank(obj.get("raw_table_text")),
    }


def iter_jsonl_rows(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield row_from_obj(json.loads(line))
            except Exception as exc:
                raise ValueError(f"Failed to parse {path}:{line_no}") from exc


def iter_csv_rows(path: Path) -> Any:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, obj in enumerate(reader, start=2):
            try:
                yield row_from_obj(obj)
            except Exception as exc:
                raise ValueError(f"Failed to parse {path}:{line_no}") from exc


def iter_rows(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        yield from iter_csv_rows(path)
    elif suffix in {".jsonl", ".json"}:
        yield from iter_jsonl_rows(path)
    else:
        raise ValueError(f"Unsupported input format: {path.suffix}. Use .jsonl or .csv")


async def upsert_batch(rows: list[dict[str, Any]]) -> None:
    stmt = insert(AnnualFinancialFact).values(rows)
    update_columns = {
        col.name: getattr(stmt.excluded, col.name)
        for col in AnnualFinancialFact.__table__.columns
        if col.name not in {"id", "created_at", *UPSERT_KEY}
    }
    update_columns["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        constraint="uq_annual_financial_fact_source_metric",
        set_=update_columns,
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt)
        await session.commit()


async def count_existing() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(AnnualFinancialFact))
        return int(result.scalar_one())


async def main_async(args: argparse.Namespace) -> None:
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if not args.input.exists():
        raise FileNotFoundError(args.input)

    total = 0
    unique_total = 0
    skipped_duplicate_keys = 0
    seen_keys: set[tuple[Any, ...]] = set()
    batch: list[dict[str, Any]] = []
    for row in iter_rows(args.input):
        total += 1
        key = tuple(row.get(name) for name in UPSERT_KEY)
        if key in seen_keys:
            skipped_duplicate_keys += 1
            continue
        seen_keys.add(key)
        unique_total += 1
        if args.dry_run:
            continue
        batch.append(row)
        if len(batch) >= args.batch_size:
            await upsert_batch(batch)
            logger.info(f"Imported unique rows: {unique_total}")
            batch = []

    if batch:
        await upsert_batch(batch)

    if args.dry_run:
        logger.info(
            f"Validated rows: {total}, unique_rows={unique_total}, "
            f"skipped_duplicate_keys={skipped_duplicate_keys}"
        )
        return

    existing = await count_existing()
    logger.info(
        f"Import completed. input_rows={total}, unique_rows={unique_total}, "
        f"skipped_duplicate_keys={skipped_duplicate_keys}, table_rows={existing}"
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
