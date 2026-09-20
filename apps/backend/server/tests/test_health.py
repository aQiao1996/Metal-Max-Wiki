import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "data": {"status": "ok", "service": "metalmax-wiki-api"},
        "message": "success",
    }


@pytest.mark.asyncio
async def test_not_found_uses_unified_error_response() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == 404
    assert payload["message"] == "请求的资源不存在"
    assert payload["path"] == "/missing"
    assert payload["method"] == "GET"
    assert payload["timestamp"].endswith("Z")
