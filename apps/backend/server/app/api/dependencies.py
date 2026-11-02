from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import BusinessError
from app.db.session import get_session
from app.schemas.auth import UserResponse
from app.services.auth_service import current_user

DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


async def require_user(request: Request, db: DatabaseSession) -> UserResponse:
    """在服务器端保护需要登录的接口。"""
    return await current_user(db, request.cookies.get(get_settings().session_cookie_name))


async def require_same_origin(request: Request) -> None:
    """Cookie 鉴权的写请求只接受站点自身发起的请求。"""
    settings = get_settings()
    allowed = {settings.client_origin.rstrip("/")}
    if settings.environment == "development":
        allowed.update(
            {
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            }
        )
    if request.headers.get("origin") not in allowed:
        raise BusinessError(403, "请求来源不受信任，请从本站重试")
