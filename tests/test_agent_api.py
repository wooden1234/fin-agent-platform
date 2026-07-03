from app.api.agent import _extract_incremental_text
from langchain_core.messages import AIMessage

from app.api.agent import _extract_final_response


def test_extract_incremental_text_from_cumulative_chunks():
    previous = "哎呀，这个问题可难住我啦😅"
    current = "哎呀，这个问题可难住我啦😅 我现在没有联网获取实时天气信息的能力"

    assert _extract_incremental_text(previous, current) == " 我现在没有联网获取实时天气信息的能力"


def test_extract_incremental_text_from_overlapping_chunks():
    previous = "你可以打开联网搜索功能，"
    current = "功能，或者直接问我“上海今天的实时天气”"

    assert _extract_incremental_text(previous, current) == "或者直接问我“上海今天的实时天气”"


def test_extract_incremental_text_ignores_duplicate_chunks():
    current = "或者你也可以用手机上的天气 App"

    assert _extract_incremental_text(current, current) == ""


def test_extract_final_response_prefers_last_ai_message():
    values = {
        "summary": "这是摘要",
        "messages": [
            AIMessage(content="第一段"),
            AIMessage(content="最终答案"),
        ],
    }

    assert _extract_final_response(values) == "最终答案"


def test_extract_final_response_falls_back_to_summary():
    values = {"summary": "这是摘要", "messages": []}

    assert _extract_final_response(values) == "这是摘要"
