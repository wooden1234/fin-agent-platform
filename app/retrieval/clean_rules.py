"""加载并应用 knowledge/raw/clean_rules.yaml 中的 PDF 清洗规则。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RULES_PATH = ROOT_DIR / "knowledge" / "raw" / "clean_rules.yaml"


@dataclass
class TableRules:
    skip_keywords: list[str] = field(default_factory=list)
    financial_keywords: list[str] = field(default_factory=list)
    default_class: str = "normal"


@dataclass
class CategoryRules:
    name: str
    chunk_strategy: str = "section"
    drop_block_types: set[str] = field(default_factory=set)
    keep_block_types: set[str] = field(default_factory=set)
    noise_paragraph_patterns: list[re.Pattern[str]] = field(default_factory=list)
    skip_section_keywords: list[str] = field(default_factory=list)
    skip_before_first_level1_title: bool = False
    table: TableRules = field(default_factory=TableRules)
    page_number_to_metadata: bool = True
    strip_checkbox_suffix: bool = True


@dataclass
class CleanRuleSet:
    global_rules: dict[str, Any]
    categories: dict[str, CategoryRules]

    def for_category(self, category: str) -> CategoryRules:
        return self.categories.get(category, self.categories["_default"])

    @classmethod
    def from_yaml(cls, path: Path = RULES_PATH) -> CleanRuleSet:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        global_cfg = raw.get("global", {})
        global_table = global_cfg.get("table", {})

        base_drop = set(global_cfg.get("drop_block_types", []))
        base_keep = set(global_cfg.get("keep_block_types", []))
        base_noise = _compile_patterns(global_cfg.get("noise_paragraph_patterns", []))
        base_table = TableRules(
            skip_keywords=list(global_table.get("skip_keywords", [])),
            financial_keywords=list(global_table.get("financial_keywords", [])),
            default_class=global_table.get("default_class", "normal"),
        )

        categories: dict[str, CategoryRules] = {}
        for name, cfg in raw.get("categories", {}).items():
            cover = cfg.get("cover", {})
            cat_table_cfg = {**global_table, **cfg.get("table", {})}
            categories[name] = CategoryRules(
                name=name,
                chunk_strategy=cfg.get("chunk_strategy", "section"),
                drop_block_types=base_drop,
                keep_block_types=base_keep,
                noise_paragraph_patterns=_compile_patterns(
                    list(global_cfg.get("noise_paragraph_patterns", []))
                    + list(cfg.get("noise_paragraph_patterns", []))
                ),
                skip_section_keywords=list(cfg.get("skip_section_keywords", [])),
                skip_before_first_level1_title=bool(
                    cover.get("skip_before_first_level1_title", False)
                ),
                table=TableRules(
                    skip_keywords=list(cat_table_cfg.get("skip_keywords", [])),
                    financial_keywords=list(cat_table_cfg.get("financial_keywords", [])),
                    default_class=cat_table_cfg.get("default_class", "normal"),
                ),
                page_number_to_metadata=bool(
                    global_cfg.get("page_number_to_metadata", True)
                ),
                strip_checkbox_suffix=bool(
                    global_cfg.get("strip_checkbox_suffix", True)
                ),
            )

        categories["_default"] = CategoryRules(
            name="_default",
            drop_block_types=base_drop,
            keep_block_types=base_keep,
            noise_paragraph_patterns=base_noise,
            table=base_table,
            page_number_to_metadata=bool(global_cfg.get("page_number_to_metadata", True)),
            strip_checkbox_suffix=bool(global_cfg.get("strip_checkbox_suffix", True)),
        )
        return cls(global_rules=global_cfg, categories=categories)


def _compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns if p]


def _extract_text_from_block(block: dict[str, Any]) -> str:
    btype = block.get("type", "")
    content = block.get("content", {})

    if btype == "paragraph":
        parts = content.get("paragraph_content", [])
        return "".join(p.get("content", "") for p in parts).strip()
    if btype == "title":
        parts = content.get("title_content", [])
        return "".join(p.get("content", "") for p in parts).strip()
    if btype == "list":
        parts = content.get("list_content", [])
        return "".join(p.get("content", "") for p in parts).strip()
    if btype == "page_header":
        parts = content.get("page_header_content", [])
        return "".join(p.get("content", "") for p in parts).strip()
    if btype == "page_footer":
        parts = content.get("page_footer_content", [])
        return "".join(p.get("content", "") for p in parts).strip()
    if btype == "page_number":
        parts = content.get("page_number_content", [])
        return "".join(p.get("content", "") for p in parts).strip()
    if btype == "table":
        return content.get("html", "") or ""
    if btype == "chart":
        return _extract_chart_text(block)
    return block.get("text", "").strip()


def _extract_chart_text(block: dict[str, Any]) -> str:
    content = block.get("content", {})
    parts: list[str] = []
    for key in ("chart_caption", "chart_footnote"):
        for item in content.get(key) or []:
            text = item.get("content", "").strip()
            if text:
                parts.append(text)
    body = (content.get("content") or "").strip()
    if body:
        parts.append(body)
    sub_type = block.get("sub_type")
    if sub_type:
        parts.insert(0, f"[{sub_type}]")
    return "\n".join(parts).strip()


def _title_level(block: dict[str, Any]) -> int | None:
    if block.get("type") != "title":
        return None
    return block.get("content", {}).get("level")


def parse_page_number_label(label: str) -> tuple[int | None, int | None]:
    """解析 '4 / 219' → (4, 219)。"""
    m = re.search(r"(\d+)\s*/\s*(\d+)", label)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def is_noise_paragraph(text: str, rules: CategoryRules) -> bool:
    t = text.strip()
    if not t:
        return True
    for pat in rules.noise_paragraph_patterns:
        if pat.search(t):
            return True
    return False


def clean_paragraph_text(text: str, rules: CategoryRules) -> str:
    if not rules.strip_checkbox_suffix:
        return text.strip()
    cleaned = re.sub(r"[□√]\s*(是|否|适用|不适用)\s*", "", text).strip()
    return cleaned


def should_skip_section(title: str, rules: CategoryRules) -> bool:
    for kw in rules.skip_section_keywords:
        if kw in title:
            return True
    return False


def classify_table(html: str, caption: str, section_path: str, rules: CategoryRules) -> str:
    blob = f"{caption} {section_path} {html}"
    for kw in rules.table.skip_keywords:
        if kw in blob:
            return "skip"
    for kw in rules.table.financial_keywords:
        if kw in blob:
            return "financial"
    return rules.table.default_class


def find_content_list_v2(parsed_dir: Path) -> Path | None:
    matches = sorted(parsed_dir.glob("*_content_list_v2.json"))
    return matches[0] if matches else None


def load_pages_from_v2(path: Path) -> list[list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"unexpected v2 format: {path}")
    return data


@dataclass
class CleanStats:
    dropped_by_type: dict[str, int]
    dropped_noise_paragraph: int
    dropped_cover_paragraph: int
    dropped_skip_section: int
    tables: dict[str, int]
    charts: int
    kept_blocks: int

    def summary(self) -> str:
        lines = [
            f"kept_blocks={self.kept_blocks}",
            f"dropped_noise_paragraph={self.dropped_noise_paragraph}",
            f"dropped_cover_paragraph={self.dropped_cover_paragraph}",
            f"dropped_skip_section={self.dropped_skip_section}",
            f"dropped_by_type={self.dropped_by_type}",
            f"tables={self.tables}",
            f"charts={self.charts}",
        ]
        return "\n".join(lines)


def analyze_document(
    pages: list[list[dict[str, Any]]],
    category: str,
    ruleset: CleanRuleSet | None = None,
    *,
    part_start: int = 1,
) -> CleanStats:
    """ dry-run：统计规则命中情况，不写库。"""
    ruleset = ruleset or load_rules()
    rules = ruleset.for_category(category)

    dropped_by_type: dict[str, int] = {}
    tables: dict[str, int] = {"skip": 0, "normal": 0, "financial": 0}
    charts = 0
    dropped_noise = 0
    dropped_cover = 0
    dropped_section = 0
    kept = 0

    seen_level1 = False
    skip_current_section = False
    section_path = ""

    for page_idx, page in enumerate(pages):
        page_label = ""
        for block in page:
            btype = block.get("type", "")

            if btype == "page_number":
                page_label = _extract_text_from_block(block)
                continue

            if btype in rules.drop_block_types:
                dropped_by_type[btype] = dropped_by_type.get(btype, 0) + 1
                continue

            if btype == "title":
                title = _extract_text_from_block(block)
                level = _title_level(block) or 1
                if level == 1:
                    seen_level1 = True
                skip_current_section = should_skip_section(title, rules)
                if skip_current_section:
                    dropped_section += 1
                    continue
                section_path = title
                kept += 1
                continue

            if skip_current_section:
                dropped_section += 1
                continue

            if btype == "paragraph":
                text = _extract_text_from_block(block)
                if rules.skip_before_first_level1_title and not seen_level1:
                    dropped_cover += 1
                    continue
                if is_noise_paragraph(text, rules):
                    dropped_noise += 1
                    continue
                cleaned = clean_paragraph_text(text, rules)
                if not cleaned:
                    dropped_noise += 1
                    continue
                kept += 1
                continue

            if btype == "table":
                html = _extract_text_from_block(block)
                caption = ""
                content = block.get("content", {})
                caps = content.get("table_caption") or []
                if caps:
                    caption = " ".join(str(c) for c in caps)
                tclass = classify_table(html, caption, section_path, rules)
                tables[tclass] = tables.get(tclass, 0) + 1
                if tclass != "skip":
                    kept += 1
                continue

            if btype == "chart":
                text = _extract_text_from_block(block)
                if text:
                    charts += 1
                    kept += 1
                continue

            if btype in rules.keep_block_types:
                kept += 1

    return CleanStats(
        dropped_by_type=dropped_by_type,
        dropped_noise_paragraph=dropped_noise,
        dropped_cover_paragraph=dropped_cover,
        dropped_skip_section=dropped_section,
        tables=tables,
        charts=charts,
        kept_blocks=kept,
    )


@lru_cache(maxsize=1)
def load_rules() -> CleanRuleSet:
    return CleanRuleSet.from_yaml(RULES_PATH)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Dry-run PDF clean rules stats")
    parser.add_argument("parsed_dir", type=Path, help="knowledge/parsed/... 解压目录")
    parser.add_argument(
        "--category",
        default="research_reports",
        help="manifest category，决定套用哪套规则",
    )
    args = parser.parse_args()

    v2 = find_content_list_v2(args.parsed_dir)
    if not v2:
        raise SystemExit(f"未找到 content_list_v2.json: {args.parsed_dir}")

    pages = load_pages_from_v2(v2)
    stats = analyze_document(pages, args.category)
    print(f"file: {v2}")
    print(f"category: {args.category}")
    print(stats.summary())


if __name__ == "__main__":
    main()
