import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models.savings import SavingsDue, SavingsDueStatus


@pytest.mark.asyncio
async def test_idempotency_conflict_returns_409(
    client: AsyncClient,
    funded_group_fixture: dict,
    db_session: AsyncSession,
) -> None:
    """
    Hardening: Replay with same Idempotency-Key but different request body
    must be rejected with HTTP 409 Conflict.
    """
    shg = funded_group_fixture["shg"]
    member = funded_group_fixture["member"]
    leader = funded_group_fixture["leader"]

    token = create_access_token(leader.id, leader.role.value)
    leader_headers = {"Authorization": f"Bearer {token}"}

    # Seed due
    due = SavingsDue(
        shg_id=shg.id,
        member_id=member.id,
        period="2026-04",
        amount_due=Decimal("500.00"),
        amount_paid=Decimal("0.00"),
        status=SavingsDueStatus.PENDING,
    )
    db_session.add(due)
    await db_session.commit()

    idem_key = f"idem-key-{uuid.uuid4()}"
    headers = {**leader_headers, "Idempotency-Key": idem_key}

    payload_a = {
        "member_id": str(member.id),
        "amount": "500.00",
        "period": "2026-04",
        "fine_amount": "0.00",
    }

    # 1. First request succeeds
    res1 = await client.post("/api/v1/savings/collect", json=payload_a, headers=headers)
    assert res1.status_code == 200

    # 2. Conflicting payload under same key
    payload_b = {
        "member_id": str(member.id),
        "amount": "600.00",  # Changed amount
        "period": "2026-04",
        "fine_amount": "0.00",
    }
    res2 = await client.post("/api/v1/savings/collect", json=payload_b, headers=headers)
    assert res2.status_code == 409
    body = res2.json()
    assert body["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_max_body_size_exceeded_returns_413(
    client: AsyncClient,
    leader_headers: dict[str, str],
) -> None:
    """
    Hardening: Requests exceeding max payload size (2 MB) must be rejected with HTTP 413.
    """
    oversize_headers = {
        **leader_headers,
        "Content-Length": "3000000",  # 3 MB > 2 MB limit
        "Content-Type": "application/json",
    }

    resp = await client.post(
        "/api/v1/savings/collect",
        content=b"{}",
        headers=oversize_headers,
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_rejecting_unknown_fields_returns_422(
    client: AsyncClient,
    funded_group_fixture: dict,
) -> None:
    """
    Hardening: Payloads containing undeclared unknown fields must be rejected with HTTP 422.
    """
    member = funded_group_fixture["member"]
    leader = funded_group_fixture["leader"]

    token = create_access_token(leader.id, leader.role.value)
    leader_headers = {"Authorization": f"Bearer {token}"}

    payload_with_unknown_fields = {
        "member_id": str(member.id),
        "amount": "500.00",
        "period": "2026-05",
        "fine_amount": "0.00",
        "malicious_extra_field": "injected_data",
        "unexpected_admin_flag": True,
    }

    resp = await client.post(
        "/api/v1/savings/collect",
        json=payload_with_unknown_fields,
        headers=leader_headers,
    )
    assert resp.status_code == 422
    err_body = resp.json()
    # Pydantic extra_forbidden validation error details
    details = str(err_body)
    assert "extra_forbidden" in details or "Extra inputs are not permitted" in details or "extra fields" in details.lower()


@pytest.mark.asyncio
async def test_security_headers_enforced(
    client: AsyncClient,
) -> None:
    """
    Hardening: Asserts that all standard security headers are present on responses.
    """
    resp = await client.get("/health")
    assert resp.status_code == 200

    headers = resp.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers.get("Permissions-Policy", "")
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
