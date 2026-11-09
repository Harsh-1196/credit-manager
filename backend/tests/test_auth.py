import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user: User) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "admin_password_123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "admin@test.org"
    assert data["user"]["role"] == "ADMIN"

    # Verify cookies
    cookies = response.cookies
    assert "shg_refresh_token" in cookies
    assert "shg_csrf_token" in cookies


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient, admin_user: User) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "wrong_password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_lockout_after_5_failures(client: AsyncClient, admin_user: User, db_session: AsyncSession) -> None:
    # 5 failed attempts
    for _ in range(5):
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.org", "password": "wrong_password"},
        )
        assert res.status_code == 401

    # 6th attempt should now be locked out (HTTP 429)
    res6 = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "admin_password_123"},
    )
    assert res6.status_code == 429
    data = res6.json()
    assert data["code"] == "ACCOUNT_LOCKED"
    assert "locked_until" in data["details"]


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, admin_user: User) -> None:
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "admin_password_123"},
    )
    old_refresh = login_res.cookies.get("shg_refresh_token")
    assert old_refresh is not None

    # Refresh tokens
    refresh_res = await client.post(
        "/api/v1/auth/refresh",
        cookies={"shg_refresh_token": old_refresh},
    )
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data

    # Verify a new refresh token was set
    new_refresh = refresh_res.cookies.get("shg_refresh_token")
    assert new_refresh is not None
    assert new_refresh != old_refresh


@pytest.mark.asyncio
async def test_refresh_token_reuse_detection(client: AsyncClient, admin_user: User, db_session: AsyncSession) -> None:
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "admin_password_123"},
    )
    first_token = login_res.cookies.get("shg_refresh_token")
    assert first_token is not None

    # Legitimate first rotation
    ref1 = await client.post(
        "/api/v1/auth/refresh",
        cookies={"shg_refresh_token": first_token},
    )
    assert ref1.status_code == 200
    second_token = ref1.cookies.get("shg_refresh_token")
    assert second_token is not None

    # Attacker attempts to replay the already-rotated first_token!
    replay_res = await client.post(
        "/api/v1/auth/refresh",
        cookies={"shg_refresh_token": first_token},
    )
    assert replay_res.status_code == 401
    assert replay_res.json()["code"] == "REFRESH_TOKEN_REUSE_DETECTED"

    # Now verify that even the second legitimate token has been revoked as part of the family
    second_res = await client.post(
        "/api/v1/auth/refresh",
        cookies={"shg_refresh_token": second_token},
    )
    assert second_res.status_code == 401


@pytest.mark.asyncio
async def test_logout_revocation(client: AsyncClient, admin_user: User, db_session: AsyncSession) -> None:
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "admin_password_123"},
    )
    refresh_tok = login_res.cookies.get("shg_refresh_token")
    assert refresh_tok is not None
    access_tok = login_res.json()["access_token"]

    logout_res = await client.post(
        "/api/v1/auth/logout",
        cookies={"shg_refresh_token": refresh_tok},
        headers={"Authorization": f"Bearer {access_tok}"},
    )
    assert logout_res.status_code == 200

    # Refresh should now fail
    ref_res = await client.post(
        "/api/v1/auth/refresh",
        cookies={"shg_refresh_token": refresh_tok},
    )
    assert ref_res.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, admin_user: User, admin_headers: dict[str, str]) -> None:
    res = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "admin@test.org"
    assert data["role"] == "ADMIN"
    assert "group_access" in data


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, admin_user: User, admin_headers: dict[str, str]) -> None:
    res = await client.post(
        "/api/v1/auth/change-password",
        headers=admin_headers,
        json={"current_password": "admin_password_123", "new_password": "NewSecretPassword123!"},
    )
    assert res.status_code == 200

    # Verify new password works
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.org", "password": "NewSecretPassword123!"},
    )
    assert login_res.status_code == 200
