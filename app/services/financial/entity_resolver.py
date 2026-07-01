"""财务事实查询的实体标准化辅助模块。"""

from __future__ import annotations

import re
from typing import Any

_SPACE_RE = re.compile(r"\s+")


def _normalize_text(value: str) -> str:
    return _SPACE_RE.sub("", value or "").strip().lower()


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


class EntityResolver:
    """将公司名和指标名归一到更稳定的内部表达。"""

    COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
        "CATL": ("CATL", "宁德时代", "宁德", "catl"),
        "Tencent": ("Tencent", "腾讯", "tencent"),
        "Loongson": ("Loongson", "龙芯", "龙芯中科", "loongson"),
        "Cambricon": ("Cambricon", "寒武纪", "cambricon"),
    }

    METRIC_ALIASES: dict[str, tuple[str, ...]] = {
        "营业收入": ("营业收入", "营收", "收入", "营业额"),
        "归属于上市公司股东的净利润": (
            "归属于上市公司股东的净利润",
            "归母净利润",
            "净利润",
            "净利",
        ),
        "研发费用": ("研发费用", "研发"),
        "经营活动产生的现金流量净额": (
            "经营活动产生的现金流量净额",
            "经营现金流",
            "现金流",
        ),
    }

    @classmethod
    def resolve_companies(
        cls,
        companies: list[str],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        return cls._resolve_entities(
            companies,
            cls.COMPANY_ALIASES,
            entity_type="company",
        )

    @classmethod
    def resolve_metrics(
        cls,
        metrics: list[str],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        return cls._resolve_entities(
            metrics,
            cls.METRIC_ALIASES,
            entity_type="metric",
        )

    @classmethod
    def expand_company_terms(cls, company: str) -> list[str]:
        cleaned = company.strip()
        if not cleaned:
            return []
        if cleaned.isdigit():
            return [cleaned]

        canonical = cls._match_exact(cleaned, cls.COMPANY_ALIASES)
        if canonical is not None:
            return _dedupe_keep_order(list(cls.COMPANY_ALIASES[canonical]))
        return [cleaned]

    @classmethod
    def expand_metric_terms(cls, metric: str) -> list[str]:
        cleaned = metric.strip()
        if not cleaned:
            return []

        canonical = cls._match_exact(cleaned, cls.METRIC_ALIASES)
        if canonical is not None:
            return [canonical]
        return [cleaned]

    @classmethod
    def _resolve_entities(
        cls,
        raw_values: list[str],
        aliases: dict[str, tuple[str, ...]],
        *,
        entity_type: str,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        # 这一层只做轻量规则标准化：精确 alias、包含匹配和歧义收集，不直接访问数据库。
        resolved: list[str] = []
        ambiguity: list[dict[str, Any]] = []

        for raw_value in raw_values:
            cleaned = raw_value.strip()
            if not cleaned:
                continue

            if cleaned.isdigit():
                resolved.append(cleaned)
                continue

            canonical = cls._match_exact(cleaned, aliases)
            if canonical is not None:
                resolved.append(canonical)
                continue

            candidates = cls._match_by_containment(cleaned, aliases)
            if len(candidates) == 1:
                resolved.append(candidates[0])
                continue

            if len(candidates) > 1:
                ambiguity.append(
                    {
                        "entity_type": entity_type,
                        "input": cleaned,
                        "candidates": candidates,
                        "reason": "multiple_alias_matches",
                    }
                )

            resolved.append(cleaned)

        return _dedupe_keep_order(resolved), ambiguity

    @classmethod
    def _match_exact(
        cls,
        raw_value: str,
        aliases: dict[str, tuple[str, ...]],
    ) -> str | None:
        normalized = _normalize_text(raw_value)
        for canonical, values in aliases.items():
            options = (canonical, *values)
            if normalized in {_normalize_text(value) for value in options}:
                return canonical
        return None

    @classmethod
    def _match_by_containment(
        cls,
        raw_value: str,
        aliases: dict[str, tuple[str, ...]],
    ) -> list[str]:
        normalized = _normalize_text(raw_value)
        matches: list[str] = []
        for canonical, values in aliases.items():
            options = (canonical, *values)
            if any(
                normalized in _normalize_text(value) or _normalize_text(value) in normalized
                for value in options
            ):
                matches.append(canonical)
        return _dedupe_keep_order(matches)


__all__ = ["EntityResolver"]
