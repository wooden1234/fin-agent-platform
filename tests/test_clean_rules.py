from app.retrieval.clean_rules import (
    _chart_caption_from_text,
    _fallback_section_path,
    _first_sentence,
    _resolve_section_path,
    extract_blocks,
)


def test_first_sentence_stops_at_colon():
    text = (
        '2026 年 3 月 26 日，中科曙光发布超节点新品"曙光 scaleX40"：'
        "该产品为世界首个无线缆箱式超节点。"
    )
    assert _first_sentence(text) == (
        '2026 年 3 月 26 日，中科曙光发布超节点新品"曙光 scaleX40"'
    )


def test_chart_caption_from_text():
    text = "[line chart]\n最近一年走势\n| Date | 计算机 |"
    assert _chart_caption_from_text(text) == "最近一年走势"


def test_fallback_section_path_only_when_no_title():
    chart_text = "[line chart]\n最近一年走势\n| Date |"
    assert _fallback_section_path("chart", chart_text, caption="最近一年走势") == "最近一年走势"
    assert _resolve_section_path("事件：", "chart", chart_text) == "事件："
    assert _resolve_section_path("", "chart", chart_text, caption="最近一年走势") == "最近一年走势"


def test_extract_blocks_assigns_chart_caption_as_section():
    pages = [
        [
            {
                "type": "chart",
                "content": {
                    "content": "| Date | 计算机 |\n| --- | --- |",
                    "chart_caption": [{"type": "text", "content": "最近一年走势"}],
                    "chart_footnote": [],
                },
                "sub_type": "line chart",
            }
        ]
    ]
    result = extract_blocks(pages, "research_reports")
    assert len(result.blocks) == 1
    assert result.blocks[0].section_path == "最近一年走势"
