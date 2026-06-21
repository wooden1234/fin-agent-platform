"""Export financial table chunks from cleaned annual report JSONL files."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "knowledge" / "cleaned" / "annual_reports"
DEFAULT_JSONL = ROOT / "knowledge" / "cleaned" / "annual_financial_tables.jsonl"
DEFAULT_CSV = ROOT / "knowledge" / "cleaned" / "annual_financial_tables.csv"

PERIODIC_HEADER_KEYWORDS = (
    "本期数",
    "上年同期数",
    "本报告期",
    "上年同期",
    "本期发生额",
    "上期发生额",
    "本期發生額",
    "上期發生額",
    "期末余额",
    "期初余额",
    "期末餘額",
    "期初餘額",
    "年末",
    "期末",
    "期初",
    "同比",
    "增减",
    "增減",
    "变动比例",
    "變動比例",
    "比上年",
    "止年度",
    "年度",
    "十二月三十一日",
    "12月31日",
    "12 月 31 日",
    "季度",
    "月份",
    "三個月",
    "三个月",
    "第一季度",
    "第二季度",
    "第三季度",
    "第四季度",
)
PERIODIC_TABLE_KINDS = {
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "major_accounting_data",
}


TABLE_KIND_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "balance_sheet",
        (
            "资产负债表",
            "資產負債表",
            "财务状况表",
            "財務狀況表",
            "资产总计",
            "資產總額",
            "负债合计",
            "負債總額",
            "所有者权益",
            "權益及負債",
        ),
    ),
    (
        "income_statement",
        (
            "利润表",
            "利潤表",
            "损益表",
            "損益表",
            "综合收益表",
            "綜合收益表",
            "全面收益表",
            "收入",
            "营业收入",
            "營業收入",
            "营业利润",
            "經營盈利",
            "净利润",
            "盈利",
            "每股收益",
        ),
    ),
    (
        "cash_flow_statement",
        (
            "现金流量表",
            "現金流量表",
            "现金流量净额",
            "現金流量淨額",
            "经营活动产生的现金流量",
            "經營活動產生的現金流量",
        ),
    ),
    (
        "major_accounting_data",
        ("主要会计数据", "主要會計數據", "主要财务指标", "主要財務指標", "近三年"),
    ),
    ("equity_changes", ("股东权益变动", "股東權益變動", "所有者权益变动", "權益變動")),
    (
        "segment_revenue",
        (
            "分行业",
            "分產品",
            "分地区",
            "分部",
            "主营业务",
            "營業收入構成",
            "按分部劃分",
        ),
    ),
    ("r_and_d", ("研发费用", "研發開支", "研发投入", "研發投入", "研发人员", "研發人員")),
    ("employee_compensation", ("应付职工薪酬", "應付職工薪酬", "职工薪酬", "員工")),
]


def _clean_table_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_markdown_row(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|") or "|" not in line[1:]:
        return None
    if line.endswith("|"):
        line = line[:-1]
    cells = [cell.replace(r"\|", "|").strip() for cell in line[1:].split("|")]
    if len(cells) < 2:
        return None
    if all(not cell or re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
        return None
    return cells


def markdown_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        row = split_markdown_row(line)
        if row:
            rows.append(row)
    return rows


def row_has_periodic_header(row: list[str]) -> bool:
    cells = row[1:] if len(row) > 1 else row
    blob = " ".join(cells)
    if re.search(r"20\d{2}", blob):
        return True
    if re.search(r"[二〇零一二三四五六七八九]{4}年", blob):
        return True
    return any(keyword in blob for keyword in PERIODIC_HEADER_KEYWORDS)


def classify_fact_parse_mode(table_kind: str, text: str) -> str:
    if table_kind not in PERIODIC_TABLE_KINDS:
        return "note_table"

    rows = markdown_rows(text)
    if not rows:
        return "unknown"
    header_scan = rows[:4]
    if any(row_has_periodic_header(row) for row in header_scan):
        return "periodic_fact"
    return "note_table"


def classify_table_kind(section: str, text: str) -> str:
    blob = f"{section} {text}"
    for kind, keywords in TABLE_KIND_KEYWORDS:
        if any(keyword in blob for keyword in keywords):
            return kind
    return "financial_other"


def iter_financial_tables(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunks_path in sorted(input_dir.glob("*/chunks.jsonl")):
        with chunks_path.open(encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                meta = obj.get("metadata") or {}
                if meta.get("block_type") != "table":
                    continue
                if meta.get("table_class") != "financial":
                    continue

                text = obj.get("text", "")
                section = meta.get("section_path") or meta.get("section") or ""
                table_kind = classify_table_kind(section, text)
                fact_parse_mode = classify_fact_parse_mode(table_kind, text)
                rows.append(
                    {
                        "doc_id": meta.get("doc_id", ""),
                        "title": meta.get("title", ""),
                        "ticker": meta.get("ticker", ""),
                        "fiscal_year": meta.get("fiscal_year", ""),
                        "source": meta.get("source", ""),
                        "page_num": meta.get("page_num", ""),
                        "chunk_index": meta.get("chunk_index", ""),
                        "section": section,
                        "table_kind": table_kind,
                        "fact_parse_mode": fact_parse_mode,
                        "table_split_strategy": meta.get("table_split_strategy", ""),
                        "table_header_inherited": meta.get("table_header_inherited", ""),
                        "table_part_index": meta.get("table_part_index", ""),
                        "table_part_count": meta.get("table_part_count", ""),
                        "text": text,
                        "text_flat": _clean_table_text(text),
                    }
                )
    return rows


def write_jsonl(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "doc_id",
        "title",
        "ticker",
        "fiscal_year",
        "source",
        "page_num",
        "chunk_index",
        "section",
        "table_kind",
        "fact_parse_mode",
        "table_split_strategy",
        "table_header_inherited",
        "table_part_index",
        "table_part_count",
        "text_flat",
    ]
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def print_summary(rows: list[dict[str, Any]]) -> None:
    by_kind: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    by_doc: dict[str, int] = {}
    for row in rows:
        by_kind[row["table_kind"]] = by_kind.get(row["table_kind"], 0) + 1
        by_mode[row["fact_parse_mode"]] = by_mode.get(row["fact_parse_mode"], 0) + 1
        by_doc[row["doc_id"]] = by_doc.get(row["doc_id"], 0) + 1

    print(f"financial_table_chunks={len(rows)}")
    print("by_fact_parse_mode:")
    for mode, count in sorted(by_mode.items()):
        print(f"  {mode}: {count}")
    print("by_kind:")
    for kind, count in sorted(by_kind.items()):
        print(f"  {kind}: {count}")
    print("by_doc:")
    for doc_id, count in sorted(by_doc.items()):
        print(f"  {doc_id}: {count}")


def format_output_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export financial table chunks from cleaned annual reports."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl-output", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    rows = iter_financial_tables(args.input_dir)
    write_jsonl(rows, args.jsonl_output)
    write_csv(rows, args.csv_output)
    print_summary(rows)
    print(f"jsonl={format_output_path(args.jsonl_output)}")
    print(f"csv={format_output_path(args.csv_output)}")


if __name__ == "__main__":
    main()
