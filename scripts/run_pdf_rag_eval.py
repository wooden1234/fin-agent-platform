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


def _doc_match(hit, case: dict) -> bool:
    return (hit.metadata or {}).get("doc_id") == case.get("expected_doc_id")


def _category_match(hit, case: dict) -> bool:
    cat = case.get("expected_category", "")
    return hit.category == cat or (hit.metadata or {}).get("category") == cat


def _keyword_match(text: str, keywords: list[str]) -> bool:
    return bool(keywords) and any(kw in (text or "") for kw in keywords)


def _hit_relevant(hit, case: dict, *, require_doc: bool = False) -> bool:
    """相关判定：优先 doc_id 精确命中；否则 category + keyword 同时满足。"""
    if _doc_match(hit, case):
        return True
    if require_doc:
        return False
    keywords = case.get("keywords") or []
    return _category_match(hit, case) and _keyword_match(hit.text, keywords)


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
    top3_doc = 0
    top3_keyword = 0
    top1_doc = 0

    for case in cases:
        query = case["query"]
        hits = retriever.search(query, top_k=top_k)
        padded = hits + [None] * (top_k - len(hits))

        hit_fields: dict = {}
        any_doc = False
        any_kw = False
        for j, h in enumerate(padded[:top_k], start=1):
            if h is None:
                hit_fields.update(
                    {
                        f"hit{j}_score": "",
                        f"hit{j}_doc_id": "",
                        f"hit{j}_category": "",
                        f"hit{j}_preview": "",
                        f"hit{j}_doc_match": False,
                        f"hit{j}_keyword_match": False,
                    }
                )
                continue

            doc_ok = _doc_match(h, case)
            kw_ok = _keyword_match(h.text, case.get("keywords") or [])
            any_doc = any_doc or doc_ok
            any_kw = any_kw or (doc_ok or (_category_match(h, case) and kw_ok))

            preview = (h.text or "").replace("\n", " ")[:120]
            hit_fields[f"hit{j}_score"] = round(h.score, 4)
            hit_fields[f"hit{j}_doc_id"] = (h.metadata or {}).get("doc_id", "")
            hit_fields[f"hit{j}_category"] = h.category or (h.metadata or {}).get("category", "")
            hit_fields[f"hit{j}_preview"] = preview
            hit_fields[f"hit{j}_doc_match"] = doc_ok
            hit_fields[f"hit{j}_keyword_match"] = kw_ok

        if any_doc:
            top3_doc += 1
        if any_kw:
            top3_keyword += 1
        if hits and _doc_match(hits[0], case):
            top1_doc += 1

        rows.append(
            {
                "query_id": case.get("query_id"),
                "query": query,
                "query_type": case.get("query_type", ""),
                "expected_category": case.get("expected_category", ""),
                "expected_doc_id": case.get("expected_doc_id", ""),
                "source_hint": case.get("source_hint", ""),
                "top3_doc_match": any_doc,
                "top3_relevant": any_kw,
                "top1_doc_match": bool(hits and _doc_match(hits[0], case)),
                **hit_fields,
            }
        )

        print(
            f"[{case.get('query_id')}] doc@3={any_doc} rel@3={any_kw} doc@1={rows[-1]['top1_doc_match']} "
            f"| {query[:36]}..."
        )

    n = len(cases) or 1
    summary = {
        "total": len(cases),
        "top_k": top_k,
        "top3_doc_match_rate": top3_doc / n,
        "top3_relevant_rate": top3_keyword / n,
        "top1_doc_match_rate": top1_doc / n,
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PDF RAG 检索评测")
    parser.add_argument("--eval", type=Path, default=EVAL_PATH)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--include-faq", action="store_true")
    parser.add_argument("--categories", nargs="+", default=None)
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
    print(f"Doc@3:  {summary['top3_doc_match_rate']:.1%} ({int(summary['top3_doc_match_rate'] * summary['total'])}/{summary['total']})")
    print(f"Rel@3:  {summary['top3_relevant_rate']:.1%}  (doc 或 category+keyword)")
    print(f"Doc@1:  {summary['top1_doc_match_rate']:.1%}")


if __name__ == "__main__":
    main()
