from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.guides import GuideDetail, GuideListData, GuidePhaseId
from app.schemas.response import ApiResponse
from app.services.guide_service import get_guide, list_guides

router = APIRouter(prefix="/versions/{version}/guides", tags=["guides"])


@router.get("", response_model=ApiResponse[GuideListData], summary="主线攻略章节列表")
async def guide_list(
    version: str,
    q: Annotated[str, Query(max_length=100)] = "",
    phase: GuidePhaseId | None = None,
) -> ApiResponse[GuideListData]:
    """按关键词和阶段浏览主线、准备与可选章节摘要。"""
    return ApiResponse(data=list_guides(version, q=q, phase=phase))


@router.get("/{slug}", response_model=ApiResponse[GuideDetail], summary="主线攻略章节详情")
async def guide_detail(version: str, slug: str) -> ApiResponse[GuideDetail]:
    """返回完整操作清单、战斗要求、证据出处与原创流程示意。"""
    return ApiResponse(data=get_guide(version, slug))
