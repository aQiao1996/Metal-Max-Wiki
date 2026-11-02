from fastapi import APIRouter

from app.schemas.game_version import GameVersionItem
from app.schemas.response import ApiResponse
from app.services.game_version_service import list_game_versions

router = APIRouter(prefix="/game-versions", tags=["game-versions"])


@router.get(
    "",
    response_model=ApiResponse[list[GameVersionItem]],
    summary="获取游戏版本列表",
)
async def get_game_versions() -> ApiResponse[list[GameVersionItem]]:
    """获取已开放和计划支持的游戏版本。"""

    return ApiResponse[list[GameVersionItem]](data=list_game_versions())
