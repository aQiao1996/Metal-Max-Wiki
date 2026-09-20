from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse[DataT](BaseModel):
    """统一成功响应。"""

    code: Literal[200] = 200
    data: DataT
    message: str = "success"


class ApiError(BaseModel):
    """统一错误响应。"""

    code: int
    timestamp: str
    path: str
    method: str
    message: str


class PaginationMeta(BaseModel):
    """分页元数据。"""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, serialization_alias="pageSize")
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0, serialization_alias="totalPages")
    has_next: bool = Field(serialization_alias="hasNext")
    has_prev: bool = Field(serialization_alias="hasPrev")

    @classmethod
    def create(cls, *, page: int, page_size: int, total: int) -> Self:
        total_pages = (total + page_size - 1) // page_size
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class PaginationResponse[DataT](BaseModel):
    """分页业务数据。"""

    list: list[DataT]
    pagination: PaginationMeta
