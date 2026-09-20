import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.schemas.response import ApiResponse, PaginationMeta, PaginationResponse

application = create_app()


@application.get("/validated")
async def validated(limit: int) -> dict[str, int]:
    return {"limit": limit}


@application.get("/unexpected-error")
async def unexpected_error() -> None:
    raise RuntimeError("测试异常")


@pytest.mark.asyncio
async def test_validation_error_uses_unified_error_response() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.get("/validated", params={"limit": "invalid"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == 422
    assert payload["message"] == "请求参数验证失败"
    assert payload["path"] == "/validated"
    assert payload["method"] == "GET"
    assert payload["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_unexpected_error_uses_unified_error_response() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {
        "code": 500,
        "timestamp": response.json()["timestamp"],
        "path": "/unexpected-error",
        "method": "GET",
        "message": "服务器内部错误",
    }
    assert response.json()["timestamp"].endswith("Z")


def test_pagination_response_uses_moge_field_names() -> None:
    pagination = PaginationMeta.create(page=2, page_size=20, total=45)
    page_data = PaginationResponse[str](list=["item"], pagination=pagination)
    response = ApiResponse[PaginationResponse[str]](data=page_data)

    assert response.model_dump(mode="json", by_alias=True) == {
        "code": 200,
        "data": {
            "list": ["item"],
            "pagination": {
                "page": 2,
                "pageSize": 20,
                "total": 45,
                "totalPages": 3,
                "hasNext": True,
                "hasPrev": True,
            },
        },
        "message": "success",
    }
