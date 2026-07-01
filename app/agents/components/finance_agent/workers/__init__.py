"""Worker 注册表"""

WORKER_REGISTRY = {
    "faq": {
        "node": "faq_agent",
        "description": "通用金融知识问答（交易规则、术语、常识）",
    },
    "pdf": {
        "node": "pdf_agent",
        "description": "PDF 文档问答（年报解读、政策文件、引用出处）",
    },
    "financial_query_agent": {
        "node": "financial_query_agent",
        "description": "结构化财务数值查询（营收、利润、指标）",
    },
}

__all__ = ["WORKER_REGISTRY"]
