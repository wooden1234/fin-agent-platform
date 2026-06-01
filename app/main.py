from fastapi import FastAPI

app = FastAPI(
    title="fin-agent-platform",
    version="0.1.0",
    description="金融 Multi-Agent 智能客服（W1 地基）",
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fin-agent-platform"}
