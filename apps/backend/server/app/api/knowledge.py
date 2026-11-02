from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.knowledge import (
    KnowledgeCategory,
    KnowledgeListData,
    KnowledgeMount,
    KnowledgeRecord,
    KnowledgeSort,
)
from app.schemas.response import ApiResponse
from app.services.knowledge_service import get_knowledge, list_knowledge

router = APIRouter(prefix="/versions/{version}/wiki", tags=["encyclopedia"])


@router.get("/{category}", response_model=ApiResponse[KnowledgeListData], summary="查询百科分类")
async def knowledge_list(
    version: str,
    category: KnowledgeCategory,
    q: Annotated[str, Query(max_length=100)] = "",
    sort: KnowledgeSort = "name-asc",
    mount: KnowledgeMount = "all",
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> ApiResponse[KnowledgeListData]:
    """按关键词、排序和战车动力配置浏览百科。"""
    return ApiResponse(
        data=list_knowledge(
            version, category, q=q, sort=sort, mount=mount, page=page, page_size=page_size
        )
    )


@router.get(
    "/{category}/{record_id}", response_model=ApiResponse[KnowledgeRecord], summary="百科条目详情"
)
async def knowledge_detail(
    version: str, category: KnowledgeCategory, record_id: str
) -> ApiResponse[KnowledgeRecord]:
    """返回事实正文、战车配置、掉落与可追溯来源。"""
    return ApiResponse(data=get_knowledge(version, category, record_id))
