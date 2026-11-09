import pytest
from fastapi import status
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == {"status": "ok"}
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_ready_endpoint(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_request_id_passthrough(client: AsyncClient) -> None:
    custom_req_id = "test-custom-request-id-999"
    response = await client.get("/health", headers={"X-Request-ID": custom_req_id})
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Request-ID") == custom_req_id


@pytest.mark.asyncio
async def test_api_v1_health_and_ready(client: AsyncClient) -> None:
    res1 = await client.get("/api/v1/health")
    assert res1.status_code == status.HTTP_200_OK
    assert res1.json() == {"status": "ok"}

    res2 = await client.get("/api/v1/ready")
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_custom_app_error_format(client: AsyncClient) -> None:
    from app.core.errors import AppError
    from app.main import app

    @app.get("/test-custom-app-error")
    async def trigger_app_error() -> None:
        raise AppError(
            code="LOAN_INVALID_TRANSITION",
            message="Cannot move loan from CLOSED to APPROVED.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"current_status": "CLOSED", "target_status": "APPROVED"},
        )

    response = await client.get("/test-custom-app-error")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["code"] == "LOAN_INVALID_TRANSITION"
    assert data["message"] == "Cannot move loan from CLOSED to APPROVED."
    assert data["details"]["current_status"] == "CLOSED"
    assert data["details"]["target_status"] == "APPROVED"
    assert "request_id" in data
