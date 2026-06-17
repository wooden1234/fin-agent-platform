"""运行 knowledge/eval/pdf_rag_eval.jsonl，评测 PDF RAG 检索效果。"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.retrieval import get_pdf_retriever, get_retriever  # noqa: E402

EVAL_PATH = ROOT / "knowledge" / "eval" / "pdf_rag_eval.jsonl"
DEFAULT_TOP_K = 3


def load_eval_cases(path: Path = EVAL_PATH) -> list[dict]:
    cases: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def _hit_relevant(hit, case: dict) -> bool:
    meta = hit.metadata or {}
    text = hit.text or ""

    expected_doc = case.get("expected_doc_id", "")
    if expected_doc and meta.get("doc_id") == expected_doc:
        return True

    expected_cat = case.get("expected_category", "")
    if expected_cat and (hit.category == expected_cat or meta.get("category") == expected_cat):
        keywords = case.get("keywords") or []
        if keywords and any(kw in text for kw in keywords):
            return True

    keywords = case.get("keywords") or []
    return bool(keywords) and any(kw in text for kw in keywords)


def _doc_hit(hit, case: dict) -> bool:
    return (hit.metadata or {}).get("doc_id") == case.get("expected_doc_id")


def run_eval(
    *,
    eval_path: Path = EVAL_PATH,
    top_k: int = DEFAULT_TOP_K,
    pdf_only: bool = True,
    categories: list[str] | None = None,
) -> dict:
    cases = load_eval_cases(eval_path)
    if pdf_only:
        retriever = get_pdf_retriever(categories=categories, top_k=top_k, similarity_threshold=None)
    else:
        retriever = get_retriever(categories=categories, top_k=top_k, similarity_threshold=None)

    rows: list[dict] = []
    top3_relevant = 0
    top1_relevant = 0
    doc_at_1 = 0
    category_at_1 = 0

    for case in cases:
        query = case["query"]
        hits = retriever.search(query, top_k=top_k)
        padded = hits + [None] * (top_k - len(hits))

        any_rel = False
        hit_fields: dict = {}
        for j, h in enumerate(padded[:top_k], start=1):
            if h is None:
                hit_fields.update(
                    {
                        f"hit{j}_score": "",
                        f"hit{j}_doc_id": "",
                        f"hit{j}_category": "",
                        f"hit{j}_preview": "",
                        f"hit{j}_relevant": False,
                    }
                )
                continue

            rel = _hit_relevant(h, case)
            any_rel = any_rel or rel
            preview = (h.text or "").replace("\n", " ")[:120]
            hit_fields[f"hit{j}_score"] = round(h.score, 4)
            hit_fields[f"hit{j}_doc_id"] = (h.metadata or {}).get("doc_id", "")
            hit_fields[f"hit{j}_category"] = h.category or (h.metadata or {}).get("category", "")
            hit_fields[f"hit{j}_preview"] = preview
            hit_fields[f"hit{j}_relevant"] = rel

        if any_rel:
            top3_relevant += 1
        if hits and _hit_relevant(hits[0], case):
            top1_relevant += 1
        if hits and _doc_hit(hits[0], case):
            doc_at_1 += 1
        if hits and (
            hits[0].category == case.get("expected_category")
            or (hits[0].metadata or {}).get("category") == case.get("expected_category")
        ):
            category_at_1 += 1

        rows.append(
            {
                "query_id": case.get("query_id"),
                "query": query,
                "query_type": case.get("query_type", ""),
                "expected_category": case.get("expected_category", ""),
                "expected_doc_id": case.get("expected_doc_id", ""),
                "top3_relevant": any_rel,
                "top1_relevant": bool(hits and _hit_relevant(hits[0], case)),
                "doc_at_1": bool(hits and _doc_hit(hits[0], case)),
                **hit_fields,
            }
        )

        print(
            f"[{case.get('query_id')}] top3={any_rel} doc@1={rows[-1]['doc_at_1']} | {query[:40]}..."
        )

    n = len(cases) or 1
    summary = {
        "total": len(cases),
        "top_k": top_k,
        "top3_relevant_rate": top3_relevant / n,
        "top1_relevant_rate": top1_relevant / n,
        "doc_at_1_rate": doc_at_1 / n,
        "category_at_1_rate": category_at_1 / n,
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PDF RAG 检索评测")
    parser.add_argument(
        "--eval",
        type=Path,
        default=EVAL_PATH,
        help="评测集 JSONL 路径",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--include-faq",
        action="store_true",
        help="检索范围包含 FAQ 集合",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="限定 category，如 research_reports annual_reports",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "knowledge" / "eval" / "pdf_rag_eval_results.csv",
    )
    args = parser.parse_args()

    result = run_eval(
        eval_path=args.eval,
        top_k=args.top_k,
        pdf_only=not args.include_faq,
        categories=args.categories,
    )
    summary = result["summary"]
    rows = result["rows"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with args.output.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"\nWrote {args.output}")
    print(
        f"Top-{summary['top_k']} relevant: {summary['top3_relevant_rate']:.1%} "
        f"({int(summary['top3_relevant_rate'] * summary['total'])}/{summary['total']})"
    )
    print(f"Top-1 relevant: {summary['top1_relevant_rate']:.1%}")
    print(f"Doc@1:          {summary['doc_at_1_rate']:.1%}")
    print(f"Category@1:     {summary['category_at_1_rate']:.1%}")


if __name__ == "__main__":
    main()
