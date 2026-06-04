from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/health")
async def agent_health(current_user: User = Depends(get_current_user)):
    """W3 前占位：验证 Agent 路由走 JWT"""
    return {"status": "agent module ready", "user_id": current_user.id}