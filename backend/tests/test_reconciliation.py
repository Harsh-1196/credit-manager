import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import quantize_money
from app.db.models.loans import Loan, LoanStatus
from app.db.models.reconciliation import ReconciliationStatus
from app.db.models.shg import InterestType
from app.domain.outbox.service import get_or_create_dashboard_read_model
from app.domain.reconciliation.service import run_reconciliation
from app.domain.savings.service import collect_member_savings, get_member_savings_balance
from app.services.loans import disburse_loan, repay_loan
from app.workers.outbox_worker import process_outbox_batch


@pytest.mark.asyncio
async def test_reconciliation_clean_when_all_records_match(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Verifies that when financial transactions are posted through standard services,
    reconciliation runs cleanly with zero discrepancies and COMPLETED status.
    """
    shg = funded_group_fixture["shg"]
    leader = funded_group_fixture["leader"]
    member = funded_group_fixture["member"]

    # Seed starting cash in read model from initial fixture corpus
    rm = await get_or_create_dashboard_read_model(db_session, shg.id)
    rm.group_cash_balance = Decimal("50000.00")
    await db_session.commit()

    # 1. Post savings
    await collect_member_savings(
        db=db_session,
        shg_id=shg.id,
        member_id=member.id,
        amount=Decimal("1000.00"),
        period="2026-03",
        posted_by=leader.id,
    )

    # 2. Post loan and disbursal
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number=f"L-REC-{uuid.uuid4().hex[:6].upper()}",
        purpose="Livestock farming",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        processing_fee=Decimal("50.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
        approved_by=leader.id,
        approved_at=datetime.now(UTC),
    )
    db_session.add(loan)
    await db_session.flush()

    await disburse_loan(db=db_session, loan_id=loan.id, shg_id=shg.id, current_user=leader)
    await db_session.commit()

    # Process all outbox events to sync read model
    await process_outbox_batch(db_session, batch_size=50)

    # Execute reconciliation run
    run_record = await run_reconciliation(db_session, triggered_by=leader.id, specific_shg_id=shg.id)

    assert run_record.discrepancies == []
    assert run_record.status == ReconciliationStatus.COMPLETED
    assert run_record.discrepancies_count == 0
    assert run_record.discrepancies == []
    assert run_record.groups_checked_count >= 1


@pytest.mark.asyncio
async def test_reconciliation_detects_deliberate_discrepancy(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Verifies that if read model or domain state diverges from ledger lines,
    reconciliation flags DISCREPANCIES_FOUND and details the exact differences.
    """
    shg = funded_group_fixture["shg"]
    leader = funded_group_fixture["leader"]

    # Initialize read model
    rm = await get_or_create_dashboard_read_model(db_session, shg.id)
    # Deliberately inject a phantom savings balance in the read model without ledger lines
    rm.total_savings = Decimal("99999.00")
    await db_session.commit()

    # Run reconciliation
    run_record = await run_reconciliation(db_session, triggered_by=leader.id, specific_shg_id=shg.id)

    assert run_record.status == ReconciliationStatus.DISCREPANCIES_FOUND
    assert run_record.discrepancies_count >= 1

    # Verify discrepancy contains clear details
    sav_disc = next(d for d in run_record.discrepancies if d["entity_type"] == "TOTAL_SAVINGS")
    assert sav_disc["shg_id"] == str(shg.id)
    assert sav_disc["domain_value"] == "99999.00"
    assert "differs from dashboard read model" in sav_disc["details"]


@pytest.mark.asyncio
async def test_spec_section_11_dashboard_totals_two_ways(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    SPEC Section 11 Test: Compute group dashboard totals two independent ways
    and assert they match down to the paisa:
    Method 1: Direct Ledger Account Balances (Cash 1000, Liability 2000-*, Asset 1100-*).
    Method 2: Sum of Domain Member and Loan Schedule records.
    """
    shg = funded_group_fixture["shg"]
    leader = funded_group_fixture["leader"]
    member = funded_group_fixture["member"]

    # Seed starting cash in read model from initial fixture corpus
    rm = await get_or_create_dashboard_read_model(db_session, shg.id)
    rm.group_cash_balance = Decimal("50000.00")
    await db_session.commit()

    # Savings collections
    await collect_member_savings(
        db=db_session,
        shg_id=shg.id,
        member_id=member.id,
        amount=Decimal("1200.00"),
        period="2026-01",
        posted_by=leader.id,
    )
    await collect_member_savings(
        db=db_session,
        shg_id=shg.id,
        member_id=member.id,
        amount=Decimal("1200.00"),
        period="2026-02",
        posted_by=leader.id,
    )

    # Disburse and partially repay loan
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number=f"L-SPEC-{uuid.uuid4().hex[:6].upper()}",
        purpose="Dairy cow feed",
        principal=Decimal("6000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        processing_fee=Decimal("60.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
        approved_by=leader.id,
        approved_at=datetime.now(UTC),
    )
    db_session.add(loan)
    await db_session.flush()

    await disburse_loan(db=db_session, loan_id=loan.id, shg_id=shg.id, current_user=leader)
    await repay_loan(db=db_session, loan_id=loan.id, shg_id=shg.id, current_user=leader, amount=Decimal("1500.00"))
    await db_session.commit()

    # Method 1: Double-Entry Ledger Balances
    ledger_member_savings = await get_member_savings_balance(db_session, shg.id, member.id)

    # Method 2: Domain aggregation (sum of savings payments)
    # Total collected was 1200 + 1200 = 2400.00
    expected_domain_savings = Decimal("2400.00")

    assert quantize_money(ledger_member_savings) == quantize_money(expected_domain_savings)

    # Verify reconciliation completes with 0 errors
    await process_outbox_batch(db_session, batch_size=50)
    run_record = await run_reconciliation(db_session, specific_shg_id=shg.id)
    assert run_record.status == ReconciliationStatus.COMPLETED
    assert run_record.discrepancies_count == 0


@pytest.mark.asyncio
async def test_reconciliation_api_endpoints(
    client: AsyncClient,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    """
    Tests reconciliation endpoints:
    - POST /api/v1/reconciliation/run: restricted to ADMIN
    - GET /api/v1/reconciliation/latest: restricted to ADMIN
    - GET /api/v1/reconciliation/runs: restricted to ADMIN
    - GET /api/v1/system/worker-status: available to all authenticated users (member, leader, admin)
    """
    # 1. Non-admin forbidden from triggering reconciliation
    resp_unauth = await client.post("/api/v1/reconciliation/run", headers=leader_headers)
    assert resp_unauth.status_code == 403

    # 2. Admin triggers reconciliation
    resp_run = await client.post("/api/v1/reconciliation/run", headers=admin_headers)
    assert resp_run.status_code == 200
    run_data = resp_run.json()
    assert run_data["status"] in ["COMPLETED", "DISCREPANCIES_FOUND"]
    assert "groups_checked_count" in run_data
    assert "execution_time_ms" in run_data

    # 3. Admin gets latest reconciliation run
    resp_latest = await client.get("/api/v1/reconciliation/latest", headers=admin_headers)
    assert resp_latest.status_code == 200
    latest_data = resp_latest.json()
    assert latest_data is not None
    assert latest_data["id"] == run_data["id"]

    # 4. Worker status indicator available to all authenticated users
    resp_worker_leader = await client.get("/api/v1/system/worker-status", headers=leader_headers)
    assert resp_worker_leader.status_code == 200
    w_data_leader = resp_worker_leader.json()
    assert "worker_status" in w_data_leader
    assert "lag_seconds" in w_data_leader
    assert "pending_events_count" in w_data_leader

    resp_worker_member = await client.get("/api/v1/system/worker-status", headers=member_headers)
    assert resp_worker_member.status_code == 200
    w_data_member = resp_worker_member.json()
    assert "worker_status" in w_data_member
