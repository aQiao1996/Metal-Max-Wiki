from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.equipment import (
    EquipmentListData,
    EquipmentProfession,
    EquipmentRecord,
    EquipmentSort,
    EquipmentType,
)
from app.schemas.response import ApiResponse
from app.services.equipment_service import get_equipment, list_equipment

router = APIRouter(prefix="/versions/{version}", tags=["equipment"])


@router.get("/equipment", response_model=ApiResponse[EquipmentListData], summary="查询装备")
async def equipment_list(
    version: str,
    equipment_type: Annotated[EquipmentType | None, Query(alias="type")] = None,
    q: Annotated[str, Query(max_length=100)] = "",
    element: Annotated[str, Query(max_length=40)] = "",
    trait: Annotated[str, Query(max_length=40)] = "",
    profession: EquipmentProfession | None = None,
    sort: EquipmentSort = "name-asc",
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> ApiResponse[EquipmentListData]:
    """按类型、名称、属性、特性与职业筛选装备。"""
    return ApiResponse(
        data=list_equipment(
            version,
            equipment_type=equipment_type,
            q=q,
            element=element,
            trait=trait,
            profession=profession,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/equipment/{equipment_id}", response_model=ApiResponse[EquipmentRecord], summary="装备详情"
)
async def equipment_detail(version: str, equipment_id: str) -> ApiResponse[EquipmentRecord]:
    """返回装备属性、来源和核验状态。"""
    return ApiResponse(data=get_equipment(version, equipment_id))


@router.get("/search", response_model=ApiResponse[EquipmentListData], summary="搜索当前版本资料")
async def search(
    version: str,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> ApiResponse[EquipmentListData]:
    """搜索当前已收录的装备，不混入其他版本或示例条目。"""
    return ApiResponse(data=list_equipment(version, q=q, page=page, page_size=page_size))
