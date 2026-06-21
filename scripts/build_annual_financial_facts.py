"""Build row-level annual financial facts from exported financial table chunks."""

from __future__ import annotations

import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "knowledge" / "cleaned" / "annual_financial_tables.jsonl"
DEFAULT_JSONL = ROOT / "knowledge" / "cleaned" / "annual_financial_facts.jsonl"
DEFAULT_CSV = ROOT / "knowledge" / "cleaned" / "annual_financial_facts.csv"

FIELDNAMES = [
    "doc_id",
    "title",
    "ticker",
    "fiscal_year",
    "source",
    "page_num",
    "chunk_index",
    "section",
    "table_kind",
    "row_index",
    "statement_type",
    "metric_name",
    "metric_alias",
    "period_label",
    "period_year",
    "period_type",
    "value",
    "raw_value",
    "unit",
    "currency",
    "raw_row",
    "raw_table_text",
]

_SEPARATOR_RE = re.compile(r"^-+$")
_NUMERIC_RE = re.compile(r"^[\(\-+]?\s*[\d,]+(?:\.\d+)?\s*\)?%?$")
_ARABIC_YEAR_RE = re.compile(r"(20\d{2})")
_ZH_YEAR_RE = re.compile(r"([二〇零一二三四五六七八九]{4})年")

_ZH_DIGITS = {
    "〇": "0",
    "零": "0",
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse annual financial markdown tables into row-level facts."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl-output", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--include-raw-table",
        action="store_true",
        help="Keep full raw table text in every output row. CSV can become large.",
    )
    return parser.parse_args()


def split_markdown_row(line: str) -> list[str] | None:
    line = line.strip()
    if not line or "|" not in line:
        return None
    if line.startswith("【表格"):
        return None
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells = [cell.replace(r"\|", "|").strip() for cell in line.split("|")]
    if len(cells) < 2:
        return None
    if all(not cell or _SEPARATOR_RE.match(cell.replace(" ", "")) for cell in cells):
        return None
    return cells


def extract_markdown_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        row = split_markdown_row(line)
        if row:
            rows.append(row)
    return rows


def is_numeric_cell(value: str) -> bool:
    value = value.strip()
    if not value or value in {"-", "--", "—", "不适用", "不適用", "N/A"}:
        return False
    return bool(_NUMERIC_RE.match(value))


def parse_decimal(value: str) -> Decimal | None:
    raw = value.strip()
    if not is_numeric_cell(raw):
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.strip("()").replace(",", "").replace("%", "").replace(" ", "")
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -parsed if negative else parsed


def looks_like_header(row: list[str]) -> bool:
    blob = " ".join(row)
    if any(token in blob for token in ("项目", "項目", "科目", "主要", "截至", "於", "年度", "年末")):
        return True
    if sum(1 for cell in row if parse_period_year(cell) is not None) >= 2:
        return True
    return False


def should_skip_metric(metric: str) -> bool:
    metric = metric.strip()
    if not metric:
        return True
    if metric in {"项目", "項目", "科目", "主要会计数据", "主要會計數據", "主要财务指标", "主要財務指標"}:
        return True
    if metric.endswith(":") or metric.endswith("："):
        return True
    if is_numeric_cell(metric):
        return True
    return False


def extract_unit_currency(text: str) -> tuple[str, str]:
    currency = ""
    unit = ""

    m = re.search(r"单位[:：]\s*([^\n|]+)", text)
    if m:
        unit_blob = m.group(1).strip()
        unit = unit_blob
        currency_match = re.search(r"币种[:：]\s*([^\s|]+)", unit_blob)
        if currency_match:
            currency = currency_match.group(1)

    if "人民幣百萬元" in text or "人民币百万元" in text:
        unit = "百万元"
        currency = "人民币"
    elif "人民幣千元" in text or "人民币千元" in text:
        unit = "千元"
        currency = "人民币"
    elif "人民幣萬元" in text or "人民币万元" in text:
        unit = "万元"
        currency = "人民币"
    elif "币种：人民币" in text or "幣種：人民幣" in text:
        currency = currency or "人民币"

    if "百万元" in unit or "百萬元" in unit:
        unit = "百万元"
    elif "万元" in unit or "萬元" in unit:
        unit = "万元"
    elif "千元" in unit:
        unit = "千元"
    elif "元" in unit and not unit:
        unit = "元"

    return unit, currency


def parse_period_year(label: str) -> int | None:
    m = _ARABIC_YEAR_RE.search(label)
    if m:
        return int(m.group(1))
    m = _ZH_YEAR_RE.search(label)
    if not m:
        return None
    digits = "".join(_ZH_DIGITS.get(ch, "") for ch in m.group(1))
    return int(digits) if len(digits) == 4 else None


def classify_period(label: str) -> str:
    if any(token in label for token in ("同比", "增减", "變動", "变动", "%")):
        return "change_rate"
    if any(token in label for token in ("年末", "12 月 31 日", "十二月三十一日", "於")):
        return "period_end"
    if "季度" in label or "季" in label:
        return "quarter"
    if parse_period_year(label) is not None:
        return "annual"
    return "unknown"


def infer_period_year(label: str, fiscal_year: Any) -> int | None:
    year = parse_period_year(label)
    if year is not None:
        return year
    try:
        fy = int(fiscal_year)
    except (TypeError, ValueError):
        return None
    if any(token in label for token in ("本期", "本年", "本年度", "期末余额", "期末餘額")):
        return fy
    if any(token in label for token in ("上年", "去年", "期初余额", "期初餘額")):
        return fy - 1
    return None


def infer_statement_type(table: dict[str, Any]) -> str:
    section = table.get("section") or ""
    kind = table.get("table_kind") or ""
    if section:
        return section
    return kind


def value_headers(headers: list[str], width: int) -> list[str]:
    if len(headers) >= width:
        return headers[:width]
    return headers + [f"value_{i}" for i in range(len(headers), width)]


def row_to_facts(table: dict[str, Any], row: list[str], headers: list[str], row_index: int) -> list[dict[str, Any]]:
    width = max(len(row), len(headers))
    cells = row + [""] * (width - len(row))
    hdrs = value_headers(headers, width)
    metric = cells[0].strip()
    if should_skip_metric(metric):
        return []

    unit, currency = extract_unit_currency(table.get("text") or "")
    facts: list[dict[str, Any]] = []
    for col_idx, raw_value in enumerate(cells[1:], start=1):
        value = parse_decimal(raw_value)
        if value is None:
            continue
        period_label = hdrs[col_idx].strip() if col_idx < len(hdrs) else f"value_{col_idx}"
        if period_label in {"附注", "附註", "注释", "註釋"}:
            continue
        period_type = classify_period(period_label)
        fact_unit = "%" if period_type == "change_rate" or raw_value.strip().endswith("%") else unit
        period_year = infer_period_year(period_label, table.get("fiscal_year"))
        facts.append(
            {
                "doc_id": table.get("doc_id", ""),
                "title": table.get("title", ""),
                "ticker": table.get("ticker", ""),
                "fiscal_year": table.get("fiscal_year", ""),
                "source": table.get("source", ""),
                "page_num": table.get("page_num", ""),
                "chunk_index": table.get("chunk_index", ""),
                "section": table.get("section", ""),
                "table_kind": table.get("table_kind", ""),
                "row_index": row_index,
                "statement_type": infer_statement_type(table),
                "metric_name": metric,
                "metric_alias": "",
                "period_label": period_label,
                "period_year": period_year or "",
                "period_type": period_type,
                "value": str(value),
                "raw_value": raw_value.strip(),
                "unit": fact_unit,
                "currency": currency,
                "raw_row": " | ".join(cells).strip(),
                "raw_table_text": table.get("text", ""),
            }
        )
    return facts


def parse_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows = extract_markdown_rows(table.get("text") or "")
    if not rows:
        return []

    facts: list[dict[str, Any]] = []
    headers: list[str] | None = None
    for row_index, row in enumerate(rows):
        if looks_like_header(row):
            if parse_period_year(row[0]) is not None and sum(
                1 for cell in row if parse_period_year(cell) is not None
            ) >= 2:
                headers = [""] + row
            else:
                headers = row
            continue
        if headers is None:
            headers = ["metric"] + [f"value_{i}" for i in range(1, len(row))]
        facts.extend(row_to_facts(table, row, headers, row_index))
    return facts


def load_tables(path: Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tables.append(json.loads(line))
    return tables


def write_jsonl(rows: list[dict[str, Any]], output: Path, *, include_raw_table: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for row in rows:
            obj = row if include_raw_table else {**row, "raw_table_text": ""}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def write_csv(rows: list[dict[str, Any]], output: Path, *, include_raw_table: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            obj = row if include_raw_table else {**row, "raw_table_text": ""}
            writer.writerow({name: obj.get(name, "") for name in FIELDNAMES})


def print_summary(tables: list[dict[str, Any]], facts: list[dict[str, Any]]) -> None:
    by_doc: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for fact in facts:
        by_doc[fact["doc_id"]] = by_doc.get(fact["doc_id"], 0) + 1
        by_kind[fact["table_kind"]] = by_kind.get(fact["table_kind"], 0) + 1

    print(f"tables={len(tables)}")
    print(f"facts={len(facts)}")
    print("facts_by_kind:")
    for key, count in sorted(by_kind.items()):
        print(f"  {key}: {count}")
    print("facts_by_doc:")
    for key, count in sorted(by_doc.items()):
        print(f"  {key}: {count}")


def main() -> None:
    args = parse_args()
    tables = load_tables(args.input)
    facts: list[dict[str, Any]] = []
    for table in tables:
        facts.extend(parse_table(table))

    write_jsonl(facts, args.jsonl_output, include_raw_table=args.include_raw_table)
    write_csv(facts, args.csv_output, include_raw_table=args.include_raw_table)
    print_summary(tables, facts)
    print(f"jsonl={args.jsonl_output.relative_to(ROOT)}")
    print(f"csv={args.csv_output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
