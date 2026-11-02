from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import DatabaseSession, require_same_origin, require_user
from app.core.config import get_settings
from app.core.rate_limit import check_rate_limit
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.schemas.response import ApiResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session(response: Response, session: auth_service.AuthenticatedSession) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        session.token,
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
        max_age=settings.session_days * 86400,
        expires=session.expires_at,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _limit_auth(request: Request) -> None:
    address = request.client.host if request.client else "unknown"
    check_rate_limit(f"auth:{address}", limit=20, window=300)


@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    dependencies=[Depends(require_same_origin)],
)
async def register(
    payload: RegisterRequest, request: Request, response: Response, db: DatabaseSession
) -> ApiResponse[UserResponse]:
    """使用邮箱和密码注册，成功后自动登录。"""
    _limit_auth(request)
    session = await auth_service.register(db, str(payload.email), payload.password)
    _set_session(response, session)
    return ApiResponse(data=session.user)


@router.post(
    "/login", response_model=ApiResponse[UserResponse], dependencies=[Depends(require_same_origin)]
)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: DatabaseSession
) -> ApiResponse[UserResponse]:
    """使用邮箱和密码登录。"""
    _limit_auth(request)
    session = await auth_service.login(db, str(payload.email), payload.password)
    _set_session(response, session)
    return ApiResponse(data=session.user)


@router.get("/me", response_model=ApiResponse[UserResponse])
async def me(
    user: Annotated[UserResponse, Depends(require_user)], response: Response
) -> ApiResponse[UserResponse]:
    """获取当前账号，未登录时返回 401。"""
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(data=user)


@router.post(
    "/logout", response_model=ApiResponse[None], dependencies=[Depends(require_same_origin)]
)
async def logout(request: Request, response: Response, db: DatabaseSession) -> ApiResponse[None]:
    """退出当前设备。"""
    settings = get_settings()
    await auth_service.logout(db, request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(data=None)
