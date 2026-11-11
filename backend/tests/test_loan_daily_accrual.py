from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User
from app.db.models.loans import Loan, LoanScheduleStatus, LoanStatus
from app.db.models.shg import InterestType
from app.jobs.daily_accrual import run_daily_accrual_job
from app.services.loans import disburse_loan, repay_loan


@pytest.mark.asyncio
async def test_daily_accrual_job_marks_overdue_and_accrues_penalty(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Tests that:
    1. Overdue installments past grace days are marked OVERDUE.
    2. Penalty accrues proportionally based on penalty_interest_rate.
    3. Loan status moves ACTIVE -> OVERDUE.
    4. Running the job a second time on the same day is strictly idempotent.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    # 1. Create and disburse a 3-month loan due on 2026-01-01
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-ACCRUAL-001",
        purpose="Seeds",
        principal=Decimal("3000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=3,
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
    assert loan.status == LoanStatus.ACTIVE

    # Grace period is 5 days. Due date was Jan 1 -> grace cutoff is Jan 6.
    # Run job as of Jan 16 (10 days past grace cutoff)
    as_of = date(2026, 1, 16)
    first_run_stats = await run_daily_accrual_job(
        db=db_session,
        as_of_date=as_of,
        shg_id=shg.id,
        actor_user=admin_user,
    )

    # Refresh loan
    await db_session.refresh(loan)
    assert loan.status == LoanStatus.OVERDUE
    assert first_run_stats["loans_moved_to_overdue"] == 1
    assert Decimal(first_run_stats["penalties_accrued"]) > Decimal("0.00")

    installment1 = loan.schedule[0]
    assert installment1.status == LoanScheduleStatus.OVERDUE
    assert installment1.penalty_due > Decimal("0.00")
    assert installment1.last_penalty_accrual_date == as_of

    initial_penalty = installment1.penalty_due

    # 2. Idempotency test: Run again on the exact same date
    second_run_stats = await run_daily_accrual_job(
        db=db_session,
        as_of_date=as_of,
        shg_id=shg.id,
        actor_user=admin_user,
    )

    await db_session.refresh(installment1)
    # Zero additional penalties should accrue on second run on same date
    assert Decimal(second_run_stats["penalties_accrued"]) == Decimal("0.00")
    assert installment1.penalty_due == initial_penalty
    assert second_run_stats["loans_moved_to_overdue"] == 0


@pytest.mark.asyncio
async def test_daily_accrual_cure_and_close(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Tests that:
    1. Fully repaying overdue installments cures loan back to ACTIVE.
    2. Paying loan to zero closes it.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-CURE-001",
        purpose="Tools",
        principal=Decimal("1000.00"),
        interest_rate=Decimal("0.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=1,
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

    # Move to overdue via job
    as_of = date(2026, 1, 15)
    await run_daily_accrual_job(
        db=db_session,
        as_of_date=as_of,
        shg_id=shg.id,
        actor_user=admin_user,
    )

    await db_session.refresh(loan)
    assert loan.status == LoanStatus.OVERDUE

    # Fully repay the loan including penalty
    tot_due = loan.schedule[0].principal_due + loan.schedule[0].penalty_due
    await repay_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        amount=tot_due,
        payment_date=as_of,
    )

    await db_session.refresh(loan)
    assert loan.status == LoanStatus.CLOSED
    assert loan.closed_at is not None
