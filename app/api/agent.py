import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from app.agents.checkpoint import make_thread_config
from app.agents.graph import get_graph
from app.core.logger import get_logger
from app.core.security import get_current_user
from app.models.user import User
from app.services.conversation_service import ConversationService


router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(service="agent")

def _sse(payload: dict) -> str:
    """格式化为 SSE 行：data: {...}\\n\\n"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

@router.get("/health")
async def agent_health(current_user: User = Depends(get_current_user)):
    """W3 前占位：验证 Agent 路由走 JWT"""
    return {"status": "agent module ready", "user_id": current_user.id}

@router.post("/query")
async def agent_query(
    query: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)):
    thread_id = conversation_id if conversation_id else str(uuid.uuid4())
    thread_config = make_thread_config(thread_id)
    graph = get_graph()
    input_payload = {"messages": [HumanMessage(content=query)]}
    STREAMABLE_NODES = frozenset({"faq_agent", "pdf_agent", "general_agent"})
    async def process_stream():
        assistant_full_response = ""
        try:
            async for msg, metadata in graph.astream(
                input_payload,
                config=thread_config,
                stream_mode="messages",
            ):
                node = metadata.get("langgraph_node")
                if node not in STREAMABLE_NODES:
                    continue
                if not getattr(msg, "content", None):
                    continue
                if getattr(msg, "additional_kwargs", {}).get("tool_calls"):
                    continue
                if not isinstance(msg, AIMessage):
                    continue
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                assistant_full_response += content
                yield _sse({"type": "token", "content": content})
            
            state = await graph.aget_state(thread_config)
            values = (state.values if state else {}) or {}
            citations = values.get("citations") or []
            yield _sse({"type": "done", "citations": citations})

            # 持久化消息到数据库
            if conversation_id and assistant_full_response:
                try:
                    await ConversationService.save_message(
                        user_id=current_user.id,
                        conversation_id=int(conversation_id),
                        messages=[{"role": "user", "content": query}],
                        response=assistant_full_response,
                    )
                    logger.info(
                        "conversation saved: user={}, conv={}",
                        current_user.id, conversation_id,
                    )
                except Exception as save_err:
                    logger.error("Failed to save conversation: {}", save_err)

        except Exception as e:
            logger.exception("agent_query stream error")
            yield _sse({"type": "error", "message": str(e)})
    response = StreamingResponse(process_stream(), media_type="text/event-stream")
    response.headers["X-Conversation-ID"] = thread_id
    response.headers["Cache-Control"] = "no-cache"
    return response

