import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.savings import SavingsDueStatus
from app.db.models.shg import SHG, Member
from app.domain.savings.service import (
    calculate_late_fine,
    collect_member_savings,
    generate_savings_dues_for_period,
    get_member_savings_balance,
    withdraw_member_savings,
)


@pytest.mark.asyncio
async def test_generate_savings_dues_for_period(
    db_session: AsyncSession,
    test_group: SHG,
) -> None:
    dues = await generate_savings_dues_for_period(db_session, test_group.id, "2025-03")
    assert len(dues) == 1
    assert dues[0].period == "2025-03"
    assert dues[0].amount_due == Decimal("200.00")
    assert dues[0].amount_paid == Decimal("0.00")
    assert dues[0].status == SavingsDueStatus.PENDING

    # Generating again for the same period should not duplicate
    dues_repeat = await generate_savings_dues_for_period(db_session, test_group.id, "2025-03")
    assert len(dues_repeat) == 0


def test_calculate_late_fine() -> None:
    # monthly_saving_amount is 200, late_fine_per_day is 5.00, fine_grace_days is 5
    # Cap is 100% of monthly_saving_amount = 200.00

    # Within grace period (e.g. 3 days late, as of 2025-03-04)
    fine_zero = calculate_late_fine(
        period="2025-03",
        as_of_date=date(2025, 3, 4),
        late_fine_per_day=Decimal("5.00"),
        fine_grace_days=5,
        max_fine_cap=Decimal("200.00"),
    )
    assert fine_zero == Decimal("0.00")

    # 10 days late (as of 2025-03-11) -> 10 - 5 = 5 days chargeable @ 5/day = 25.00
    fine_normal = calculate_late_fine(
        period="2025-03",
        as_of_date=date(2025, 3, 11),
        late_fine_per_day=Decimal("5.00"),
        fine_grace_days=5,
        max_fine_cap=Decimal("200.00"),
    )
    assert fine_normal == Decimal("25.00")

    # 100 days late -> 95 days @ 5/day = 475.00, but capped at 200.00
    fine_capped = calculate_late_fine(
        period="2025-03",
        as_of_date=date(2025, 6, 9),
        late_fine_per_day=Decimal("5.00"),
        fine_grace_days=5,
        max_fine_cap=Decimal("200.00"),
    )
    assert fine_capped == Decimal("200.00")


@pytest.mark.asyncio
async def test_collect_and_withdraw_member_savings(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    # Fetch member
    stmt = select(Member).where(Member.shg_id == test_group.id)
    res = await db_session.execute(stmt)
    member = res.scalars().first()
    assert member is not None

    # Initial balance is 0
    init_balance = await get_member_savings_balance(db_session, test_group.id, member.id)
    assert init_balance == Decimal("0.00")

    # Generate dues
    await generate_savings_dues_for_period(db_session, test_group.id, "2025-01")

    # Collect savings 200.00
    due, new_bal = await collect_member_savings(
        db=db_session,
        shg_id=test_group.id,
        member_id=member.id,
        amount=Decimal("200.00"),
        period="2025-01",
        posted_by=admin_user.id,
        entry_date=date(2025, 1, 15),
    )
    assert due.status == SavingsDueStatus.PAID
    assert due.amount_paid == Decimal("200.00")
    assert new_bal == Decimal("200.00")

    # Verify balance query returns 200.00
    bal_after_col = await get_member_savings_balance(db_session, test_group.id, member.id)
    assert bal_after_col == Decimal("200.00")

    # Withdraw 50.00
    rem_bal = await withdraw_member_savings(
        db=db_session,
        shg_id=test_group.id,
        member_id=member.id,
        amount=Decimal("50.00"),
        posted_by=admin_user.id,
        reason="Emergency expense",
        entry_date=date(2025, 1, 20),
    )
    assert rem_bal == Decimal("150.00")
    bal_after_withdraw = await get_member_savings_balance(db_session, test_group.id, member.id)
    assert bal_after_withdraw == Decimal("150.00")

    # Attempt withdraw > balance should fail
    with pytest.raises(AppError) as exc:
        await withdraw_member_savings(
            db=db_session,
            shg_id=test_group.id,
            member_id=member.id,
            amount=Decimal("500.00"),
            posted_by=admin_user.id,
            reason="Exceeds balance",
            entry_date=date(2025, 1, 21),
        )
    assert exc.value.code == "INSUFFICIENT_SAVINGS_BALANCE"


@pytest.mark.asyncio
async def test_idempotency_replay_and_conflict(
    client: AsyncClient,
    test_group: SHG,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    stmt = select(Member).where(Member.shg_id == test_group.id)
    res = await db_session.execute(stmt)
    member = res.scalars().first()
    assert member is not None

    idem_key = str(uuid.uuid4())
    headers = {**admin_headers, "Idempotency-Key": idem_key}

    payload1 = {
        "member_id": str(member.id),
        "amount": "200.00",
        "collected_date": "2025-01-10",
        "period": "2025-01",
    }

    # 1. First call: success 200
    r1 = await client.post("/api/v1/savings/collect", json=payload1, headers=headers)
    assert r1.status_code == 200
    data1 = r1.json()
    assert "due" in data1

    # 2. Replay with identical key and payload: returns cached response (200) with same body
    r2 = await client.post("/api/v1/savings/collect", json=payload1, headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["due"]["id"] == data1["due"]["id"]

    # 3. Call with same key but DIFFERENT payload: returns 409 Conflict
    payload_diff = {
        "member_id": str(member.id),
        "amount": "500.00",  # Different amount
        "collected_date": "2025-01-10",
        "period": "2025-01",
    }
    r3 = await client.post("/api/v1/savings/collect", json=payload_diff, headers=headers)
    assert r3.status_code == 409
    assert r3.json()["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_member_passbook_api_and_admin_reversal(
    client: AsyncClient,
    test_group: SHG,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    stmt = select(Member).where(Member.shg_id == test_group.id)
    res = await db_session.execute(stmt)
    member = res.scalars().first()
    assert member is not None

    # Collect savings
    payload = {
        "member_id": str(member.id),
        "amount": "300.00",
        "collected_date": "2025-02-01",
        "period": "2025-02",
    }
    col_res = await client.post(
        "/api/v1/savings/collect",
        json=payload,
        headers={**admin_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert col_res.status_code == 200

    # Get passbook
    pb_res = await client.get(f"/api/v1/members/{member.id}/passbook", headers=admin_headers)
    assert pb_res.status_code == 200
    pb_data = pb_res.json()
    assert pb_data["total_savings_balance"] == "300.00"
    assert len(pb_data["entries"]) == 1
    pb_entry = pb_data["entries"][0]
    assert pb_entry["credit"] == "300.00"
    assert pb_entry["debit"] == ""
    assert pb_entry["balance"] == "300.00"
    entry_id = pb_entry["entry_id"]

    # Reverse entry as admin
    rev_payload = {"reason": "Entered in error for wrong month"}
    rev_res = await client.post(
        f"/api/v1/ledger/entries/{entry_id}/reverse",
        json=rev_payload,
        headers=admin_headers,
    )
    assert rev_res.status_code == 200
    rev_data = rev_res.json()
    assert rev_data["reverses_entry_id"] == entry_id

    # Passbook now has 2 entries and running balance is 0.00
    pb_res2 = await client.get(f"/api/v1/members/{member.id}/passbook", headers=admin_headers)
    assert pb_res2.status_code == 200
    pb_data2 = pb_res2.json()
    assert pb_data2["total_savings_balance"] == "0.00"
    assert len(pb_data2["entries"]) == 2
    # The reversal entry debited 300.00
    assert pb_data2["entries"][1]["debit"] == "300.00"
    assert pb_data2["entries"][1]["credit"] == ""
    assert pb_data2["entries"][1]["balance"] == "0.00"
    assert pb_data2["entries"][1]["is_reversal"] is True
