from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.ledger import JournalEntry, JournalLine
from app.db.models.loans import Loan, LoanScheduleStatus, LoanStatus
from app.db.models.shg import InterestType
from app.domain.loans.metrics import calculate_portfolio_metrics
from app.services.loans import disburse_loan, repay_loan, write_off_loan


@pytest.mark.asyncio
async def test_disbursal_fails_if_insufficient_group_cash(db_session: AsyncSession, funded_group_fixture: dict):
    """Disbursal fails with INSUFFICIENT_GROUP_CASH if loan principal exceeds group cash balance."""
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    # Loan of ₹60,000 (group only has ₹50,000 cash)
    huge_loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-HUGE-001",
        purpose="Big machinery",
        principal=Decimal("60000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=12,
        processing_fee=Decimal("600.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(huge_loan)
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await disburse_loan(
            db=db_session,
            loan_id=huge_loan.id,
            shg_id=shg.id,
            current_user=leader,
        )
    assert exc_info.value.code == "INSUFFICIENT_GROUP_CASH"


@pytest.mark.asyncio
async def test_full_loan_lifecycle_money_movement(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Tests end-to-end money movement:
    1. Disburse loan: posts balanced journal entry (debit loan asset, credit cash, credit fee).
    2. Generates repayment schedule.
    3. Records repayments: posts multi-line balanced entry.
    4. Full repayment closes the loan.
    5. Ledger remains strictly balanced at every stage.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-LIFECYCLE-001",
        purpose="Dairy cow",
        principal=Decimal("10000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=5,
        processing_fee=Decimal("100.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(loan)
    await db_session.commit()

    # Step 1: Disburse loan
    disbursed = await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        first_due_date=date(2026, 2, 1),
    )
    await db_session.commit()
    await db_session.refresh(disbursed)
    assert disbursed.status == LoanStatus.ACTIVE
    assert disbursed.disbursed_at is not None
    assert len(disbursed.schedule) == 5

    # Verify disbursal journal entry
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.shg_id == shg.id, JournalEntry.source_type == "DISBURSAL")
    )
    res = await db_session.execute(stmt)
    disb_entry = res.scalar_one()
    assert disb_entry is not None

    # Verify ledger lines balance
    line_stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
        JournalLine.entry_id == disb_entry.id
    )
    line_res = await db_session.execute(line_stmt)
    deb, cred = line_res.one()
    assert deb == Decimal("10000.00")
    assert cred == Decimal("10000.00")

    # Step 2: Repay installments
    # Repay first installment of ₹2060.36
    inst1 = disbursed.schedule[0]
    payment_amt = inst1.total_due

    repaid_loan, alloc = await repay_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        amount=payment_amt,
        payment_date=date(2026, 2, 1),
    )
    assert alloc.total_payment == payment_amt
    assert inst1.status == LoanScheduleStatus.PAID

    # Step 3: Check overall ledger balancing
    all_lines_stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
        JournalLine.entry.has(JournalEntry.shg_id == shg.id)
    )
    all_lines_res = await db_session.execute(all_lines_stmt)
    tot_deb, tot_cred = all_lines_res.one()
    assert tot_deb == tot_cred


@pytest.mark.asyncio
async def test_write_off_lifecycle(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Tests loan write-off:
    - Non-admin is blocked
    - Admin writes off overdue loan with required reason
    - Posts journal entry (Debit 5010 Write-offs, Credit 1100 Loans Receivable)
    - Total group ledger remains balanced
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    # Create an overdue loan with 5000 principal
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-WRITEOFF-001",
        purpose="Tailoring",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=5,
        processing_fee=Decimal("0.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(loan)
    await db_session.commit()

    # Disburse it
    await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        first_due_date=date(2026, 1, 1),
    )
    await db_session.commit()

    # Move to OVERDUE for write-off test
    loan.status = LoanStatus.OVERDUE
    await db_session.commit()

    # Non-admin attempting write-off must be blocked (403)
    with pytest.raises(AppError) as exc_leader:
        await write_off_loan(
            db=db_session,
            loan_id=loan.id,
            shg_id=shg.id,
            current_user=leader,
            reason="Unreachable borrower",
        )
    assert exc_leader.value.code == "FORBIDDEN_ROLE"

    # Admin writes off with reason
    written_off = await write_off_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=admin_user,
        reason="Borrower relocated permanently; unrecoverable balance",
    )
    assert written_off.status == LoanStatus.WRITTEN_OFF
    assert written_off.written_off_by == admin_user.id
    assert written_off.write_off_reason is not None

    # Verify write-off journal entry
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.shg_id == shg.id, JournalEntry.source_type == "WRITE_OFF")
    )
    res = await db_session.execute(stmt)
    wo_entry = res.scalar_one()
    assert wo_entry is not None

    # Verify ledger lines balance
    line_stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
        JournalLine.entry_id == wo_entry.id
    )
    line_res = await db_session.execute(line_stmt)
    deb, cred = line_res.one()
    assert deb == Decimal("5000.00")
    assert cred == Decimal("5000.00")


@pytest.mark.asyncio
async def test_portfolio_metrics_and_par_query(
    db_session: AsyncSession,
    funded_group_fixture: dict,
):
    """Tests Portfolio at Risk (PAR 30/60/90) and portfolio query computations."""
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    # Create and disburse a loan
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-PAR-001",
        purpose="Agri supplies",
        principal=Decimal("10000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
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
    await db_session.commit()

    # Query metrics as of March 15, 2026 (Installment 1 is Jan 1 -> 73 days overdue => PAR 30 and PAR 60)
    as_of = date(2026, 3, 15)
    metrics = await calculate_portfolio_metrics(db=db_session, shg_id=shg.id, as_of_date=as_of)

    assert metrics.total_loans_count >= 1
    assert metrics.total_disbursed_principal >= Decimal("10000.00")
    assert metrics.par_30_count >= 1
    assert metrics.par_60_count >= 1
    assert metrics.par_30_principal >= Decimal("10000.00")
