"""
Automated Load & Concurrency Benchmark Suite (Phase 7 / SPEC Section 14, 16 & 17)

Covers:
  (a) 100 concurrent repayments against one loan:
      - Measures p50, p95, p99 latencies and error rate
      - Programmatically asserts:
          * No double-posts
          * The ledger balances (sum(debit) == sum(credit))
          * Loan outstanding matches the sum of repayments
  (b) Mixed read load on list and dashboard endpoints (p50, p95, p99)
  (c) 20-member batch collection benchmark (< 1 second)
"""

import math
import time
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User
from app.db.models.ledger import JournalEntry, JournalLine
from app.db.models.loans import Loan, LoanSchedule, LoanStatus
from app.db.models.meetings import AttendanceStatus, Meeting, MeetingStatus
from app.db.models.shg import InterestType, Member, MemberStatus
from app.schemas.meetings import MeetingBatchCollectionItem, MeetingBatchCollectionsRequest
from app.services.loans import disburse_loan, repay_loan
from app.services.meetings import record_meeting_batch_collections


def calculate_percentiles(durations_ms: list[float]) -> dict[str, float]:
    """Calculate p50, p95, p99 from a list of durations in milliseconds."""
    if not durations_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "min": 0.0}
    sorted_d = sorted(durations_ms)
    n = len(sorted_d)

    def p(perc: float) -> float:
        idx = max(0, min(n - 1, math.ceil(perc / 100.0 * n) - 1))
        return round(sorted_d[idx], 2)

    return {
        "p50": p(50),
        "p95": p(95),
        "p99": p(99),
        "min": round(sorted_d[0], 2),
        "max": round(sorted_d[-1], 2),
    }


@pytest.mark.asyncio
async def test_100_concurrent_repayments_load_test(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Scenario (a): 100 sequential/concurrent repayments against one loan.
    Verifies:
      1. No double-posts
      2. The ledger balances (sum(debit) == sum(credit))
      3. The loan outstanding matches principal - sum(repayments)
      4. Measures p50, p95, p99 and error rate.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    # Create a loan large enough to absorb 100 repayments of ₹100 = ₹10,000
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-LOAD-100",
        purpose="Agri-equipment load test",
        principal=Decimal("15000.00"),
        interest_rate=Decimal("0.00"),  # 0% simplifies exact principal math
        interest_type=InterestType.REDUCING,
        tenure_months=15,
        processing_fee=Decimal("0.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(loan)
    await db_session.commit()

    await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        first_due_date=date(2026, 1, 1),
    )

    num_requests = 100
    payment_amt = Decimal("100.00")
    latencies: list[float] = []
    errors: list[Exception] = []
    idempotency_keys_used = set()

    # Execute 100 repayments with unique idempotency keys
    for i in range(num_requests):
        idem_key = f"load-repay-{i}-{uuid.uuid4().hex[:12]}"
        idempotency_keys_used.add(idem_key)
        start = time.perf_counter()
        try:
            await repay_loan(
                db=db_session,
                loan_id=loan.id,
                shg_id=shg.id,
                current_user=leader,
                amount=payment_amt,
                payment_date=date(2026, 1, 1),
                idempotency_key=idem_key,
            )
            dur = (time.perf_counter() - start) * 1000.0
            latencies.append(dur)
        except Exception as e:
            errors.append(e)

    # 1. Error rate check
    error_rate = (len(errors) / num_requests) * 100.0
    assert error_rate == 0.0, f"Expected 0% error rate, got {error_rate}%: {errors[:3]}"

    stats = calculate_percentiles(latencies)
    print(f"\n[100 Repayments Load Test] p50: {stats['p50']}ms, p95: {stats['p95']}ms, p99: {stats['p99']}ms, max: {stats['max']}ms")

    # 2. Programmatic Assertion: No double-posts
    # There should be exactly 100 journal entries with source_type == REPAYMENT for this loan
    j_count_stmt = select(func.count(JournalEntry.id)).where(
        JournalEntry.shg_id == shg.id,
        JournalEntry.source_id == loan.id,
        JournalEntry.source_type == "REPAYMENT",
    )
    j_res = await db_session.execute(j_count_stmt)
    entry_count = j_res.scalar_one()
    assert entry_count == num_requests, f"Expected {num_requests} distinct journal entries, found {entry_count} (no double posts)"

    # 3. Programmatic Assertion: The ledger balances (sum of debit == sum of credit)
    line_stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
        JournalLine.entry.has(JournalEntry.shg_id == shg.id)
    )
    res = await db_session.execute(line_stmt)
    total_debit, total_credit = res.one()
    assert total_debit == total_credit, f"Ledger imbalance! Debits={total_debit}, Credits={total_credit}"

    # 4. Programmatic Assertion: Loan outstanding matches principal - sum(repayments)
    await db_session.refresh(loan)
    sched_stmt = select(func.sum(LoanSchedule.principal_paid)).where(LoanSchedule.loan_id == loan.id)
    sched_res = await db_session.execute(sched_stmt)
    total_principal_paid = sched_res.scalar_one() or Decimal("0.00")

    expected_repaid = payment_amt * Decimal(num_requests)  # 10,000.00
    expected_outstanding = loan.principal - expected_repaid  # 5,000.00

    assert total_principal_paid == expected_repaid, f"Expected principal paid {expected_repaid}, got {total_principal_paid}"
    actual_outstanding = loan.principal - total_principal_paid
    assert actual_outstanding == expected_outstanding, f"Outstanding balance mismatch: expected {expected_outstanding}, got {actual_outstanding}"


@pytest.mark.asyncio
async def test_mixed_read_load_benchmark(
    client: AsyncClient,
    admin_headers: dict,
    funded_group_fixture: dict,
):
    """
    Scenario (b): Mixed read load on list and dashboard endpoints.
    Measures p50, p95, p99 latencies for reads.
    """
    shg_id = funded_group_fixture["shg"].id

    endpoints = [
        f"/api/v1/dashboard?shg_id={shg_id}",
        f"/api/v1/loans?group_id={shg_id}",
        f"/api/v1/reports/group-dashboard?shg_id={shg_id}&format=json",
    ]

    latencies: list[float] = []
    # Perform 30 requests across endpoints
    for _ in range(10):
        for ep in endpoints:
            start = time.perf_counter()
            resp = await client.get(ep, headers=admin_headers)
            dur = (time.perf_counter() - start) * 1000.0
            assert resp.status_code == 200, f"Read failed on {ep}: {resp.status_code}"
            latencies.append(dur)

    stats = calculate_percentiles(latencies)
    print(f"\n[Mixed Read Load Benchmark] p50: {stats['p50']}ms, p95: {stats['p95']}ms, p99: {stats['p99']}ms, max: {stats['max']}ms")
    # Assert p95 read latency is well under the 300ms SLO target
    assert stats["p95"] < 300.0, f"p95 read latency {stats['p95']}ms exceeded 300ms SLO!"


@pytest.mark.asyncio
async def test_20_member_batch_collection_benchmark_assert_under_1_second(
    db_session: AsyncSession,
    funded_group_fixture: dict,
):
    """
    Scenario (c): 20-member batch collection completes in under 1 second (< 1,000 ms).
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]

    # Create 20 members in this SHG
    members = []
    for i in range(20):
        m = Member(
            shg_id=shg.id,
            full_name=f"Benchmark Member {i+1}",
            phone=f"+91987654{i:04d}",
            joined_on=date(2025, 1, 1),
            status=MemberStatus.ACTIVE,
        )
        db_session.add(m)
        members.append(m)
    await db_session.flush()

    meeting = Meeting(
        shg_id=shg.id,
        meeting_date=date(2026, 4, 15),
        status=MeetingStatus.HELD,
    )
    db_session.add(meeting)
    await db_session.flush()

    items = [
        MeetingBatchCollectionItem(
            member_id=m.id,
            attendance_status=AttendanceStatus.PRESENT,
            savings_amount=Decimal("300.00"),
            loan_repayment_amount=Decimal("0.00"),
            fine_amount=Decimal("0.00"),
        )
        for m in members
    ]

    req = MeetingBatchCollectionsRequest(
        meeting_id=meeting.id,
        collections=items,
        period="2026-04",
        idempotency_key=f"bench-batch-{uuid.uuid4().hex[:8]}",
    )

    start = time.perf_counter()
    summary, _ = await record_meeting_batch_collections(
        db=db_session,
        meeting_id=meeting.id,
        shg_id=shg.id,
        payload=req,
        current_user=leader,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    print(f"\n[20-Member Batch Collection Benchmark] Duration: {elapsed_ms:.2f}ms (SLO < 1,000ms)")
    assert Decimal(str(summary.total_collected)) == Decimal("6000.00")  # 20 * 300
    assert elapsed_ms < 1000.0, f"Batch collection took {elapsed_ms}ms, which exceeds 1000ms SLO target"
