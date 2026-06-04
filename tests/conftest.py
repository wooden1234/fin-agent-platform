"""pytest 公共配置：加载项目根目录 .env。"""

from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)


def _has_embedding_api_key() -> bool:
    import os

    return bool(os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))


requires_embedding_key = pytest.mark.skipif(
    not _has_embedding_api_key(),
    reason="未配置 QWEN_API_KEY / DASHSCOPE_API_KEY，跳过 Embedding 集成测试",
)
