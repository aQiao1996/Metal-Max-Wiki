from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import require_same_origin, require_user
from app.core.config import get_settings
from app.core.rate_limit import check_rate_limit
from app.schemas.ai import AnswerData, AskRequest, ModelStatus
from app.schemas.auth import UserResponse
from app.schemas.response import ApiResponse
from app.services.qa_service import ask_question

router = APIRouter(tags=["ai"])


@router.get("/ai/status", response_model=ApiResponse[ModelStatus])
async def model_status(
    user: Annotated[UserResponse, Depends(require_user)],
) -> ApiResponse[ModelStatus]:
    """返回问答模型的配置状态，不暴露地址或密钥。"""
    settings = get_settings()
    return ApiResponse(
        data=ModelStatus(configured=bool(settings.ai_model.strip()), model=settings.ai_model)
    )


@router.post(
    "/versions/{version}/ask",
    response_model=ApiResponse[AnswerData],
    dependencies=[Depends(require_same_origin)],
)
async def ask(
    version: str,
    payload: AskRequest,
    user: Annotated[UserResponse, Depends(require_user)],
    response: Response,
) -> ApiResponse[AnswerData]:
    """登录后在当前版本的已收录资料中提问。"""
    check_rate_limit(f"ask:{user.id}", limit=10, window=60)
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(data=await ask_question(version, payload.question))
