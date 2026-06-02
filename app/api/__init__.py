from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.conversation import router as conversations_router

api_router = APIRouter()

api_router.include_router(auth_router, tags=["authentication"])
api_router.include_router(conversations_router)  # prefix 已在 conversations.py 里写了