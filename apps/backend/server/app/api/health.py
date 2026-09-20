from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.response import ApiResponse


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthResponse])
async def health() -> ApiResponse[HealthResponse]:
    return ApiResponse[HealthResponse](
        data=HealthResponse(status="ok", service="metalmax-wiki-api")
    )
