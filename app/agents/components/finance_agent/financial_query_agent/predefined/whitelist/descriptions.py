"""白名单 SQL 模板描述，供 tool_selection prompt 与 catalog 使用。"""

from __future__ import annotations

EXACT_METRIC_LOOKUP = "exact_metric_lookup"
LATEST_METRIC_LOOKUP = "latest_metric_lookup"
COMPARE_METRIC_LOOKUP = "compare_metric_lookup"
TREND_METRIC_LOOKUP = "trend_metric_lookup"

VALID_TEMPLATE_IDS: frozenset[str] = frozenset(
    {
        EXACT_METRIC_LOOKUP,
        LATEST_METRIC_LOOKUP,
        COMPARE_METRIC_LOOKUP,
        TREND_METRIC_LOOKUP,
    }
)

QUERY_DESCRIPTIONS: dict[str, str] = {
    EXACT_METRIC_LOOKUP: (
        "单公司 + 单年份 + 单指标精确查数。"
        "适用于用户询问某公司在特定年份的某项财务指标。"
        "示例：宁德时代 2024 年营业收入是多少？"
    ),
    LATEST_METRIC_LOOKUP: (
        "单公司 + 单指标 + 最新一期查数，用户未指定年份。"
        "适用于用户询问某公司最近/最新/当前的某项指标。"
        "示例：宁德时代最新营收是多少？"
    ),
    COMPARE_METRIC_LOOKUP: (
        "多公司或多指标对比查询。"
        "适用于用户对比两家公司的同一指标，或同一公司的多个指标。"
        "示例：宁德时代和腾讯 2024 年营收对比"
    ),
    TREND_METRIC_LOOKUP: (
        "单公司单指标跨年份趋势查询。"
        "适用于用户询问某公司某项指标的历史变化或近几年趋势。"
        "示例：宁德时代近三年营收趋势"
    ),
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    EXACT_METRIC_LOOKUP: ("company", "metric", "year"),
    LATEST_METRIC_LOOKUP: ("company", "metric"),
    COMPARE_METRIC_LOOKUP: ("company", "metric"),
    TREND_METRIC_LOOKUP: ("company", "metric"),
}

EXAMPLE_QUESTIONS: dict[str, tuple[str, ...]] = {
    EXACT_METRIC_LOOKUP: ("宁德时代 2024 年营业收入是多少？", "腾讯 2023 年净利润"),
    LATEST_METRIC_LOOKUP: ("宁德时代最新营收是多少？", "腾讯最近净利润"),
    COMPARE_METRIC_LOOKUP: ("宁德时代和腾讯 2024 年营收对比", "宁德时代 2024 年营收和研发费用对比"),
    TREND_METRIC_LOOKUP: ("宁德时代近三年营收趋势", "腾讯历年净利润"),
}


def template_catalog_text() -> str:
    lines: list[str] = []
    for template_id in VALID_TEMPLATE_IDS:
        required = ", ".join(REQUIRED_FIELDS[template_id])
        examples = " / ".join(EXAMPLE_QUESTIONS[template_id])
        lines.append(
            f"- {template_id}: {QUERY_DESCRIPTIONS[template_id]}; "
            f"required={required}; examples={examples}"
        )
    return "\n".join(lines)


__all__ = [
    "COMPARE_METRIC_LOOKUP",
    "EXACT_METRIC_LOOKUP",
    "EXAMPLE_QUESTIONS",
    "LATEST_METRIC_LOOKUP",
    "QUERY_DESCRIPTIONS",
    "REQUIRED_FIELDS",
    "TREND_METRIC_LOOKUP",
    "VALID_TEMPLATE_IDS",
    "template_catalog_text",
]
