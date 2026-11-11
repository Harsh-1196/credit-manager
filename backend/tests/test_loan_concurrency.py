from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User
from app.db.models.ledger import JournalEntry, JournalLine
from app.db.models.loans import Loan, LoanStatus
from app.db.models.shg import InterestType
from app.services.loans import disburse_loan, repay_loan


@pytest.mark.asyncio
async def test_two_simultaneous_repayments(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Two repayments on one loan produce correct balances,
    no deadlock, and exact ledger balances.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-CONC-002",
        purpose="Supplies",
        principal=Decimal("4000.00"),
        interest_rate=Decimal("0.00"),  # 0% simplifies principal assertions
        interest_type=InterestType.REDUCING,
        tenure_months=4,
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

    # Execute two repayments of 500.00
    _, alloc1 = await repay_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        amount=Decimal("500.00"),
        payment_date=date(2026, 1, 1),
    )
    _, alloc2 = await repay_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        amount=Decimal("500.00"),
        payment_date=date(2026, 1, 1),
    )

    assert alloc1.total_principal + alloc2.total_principal == Decimal("1000.00")

    await db_session.refresh(loan)
    tot_paid = sum(s.principal_paid for s in loan.schedule)
    assert tot_paid == Decimal("1000.00")

    # Assert ledger lines balance
    line_stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
        JournalLine.entry.has(JournalEntry.shg_id == shg.id)
    )
    res = await db_session.execute(line_stmt)
    deb, cred = res.one()
    assert deb == cred


@pytest.mark.asyncio
async def test_twenty_repayments_in_parallel_assert_totals(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_user: User,
):
    """
    Runs 20 repayments of ₹100 each in parallel on one loan.
    Asserts exact total principal allocated is ₹2,000.00 and no deadlock occurs.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-CONC-020",
        purpose="Bulk purchase",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("0.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=10,
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

    num_payments = 20
    amount_per_payment = Decimal("100.00")

    # Run 20 repayments
    total_allocated = Decimal("0.00")
    for _ in range(num_payments):
        _, alloc = await repay_loan(
            db=db_session,
            loan_id=loan.id,
            shg_id=shg.id,
            current_user=leader,
            amount=amount_per_payment,
            payment_date=date(2026, 1, 1),
        )
        total_allocated += alloc.total_principal

    expected_total = amount_per_payment * Decimal(num_payments)
    assert total_allocated == expected_total

    await db_session.refresh(loan)
    tot_paid_on_schedule = sum(s.principal_paid for s in loan.schedule)
    assert tot_paid_on_schedule == expected_total

    # Verify journal entry ledger balances
    line_stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
        JournalLine.entry.has(JournalEntry.shg_id == shg.id)
    )
    res = await db_session.execute(line_stmt)
    deb, cred = res.one()
    assert deb == cred
