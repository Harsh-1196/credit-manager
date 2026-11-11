import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.shg import InterestType
from app.domain.loans.allocation import allocate_repayment


def _create_mock_loan(principal: Decimal = Decimal("10000.00")) -> Loan:
    return Loan(
        id=uuid.uuid4(),
        shg_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        loan_number="LN-ALLOC-TEST",
        purpose="Livestock",
        principal=principal,
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=10,
        status=LoanStatus.ACTIVE,
        applied_by=uuid.uuid4(),
    )


def _create_mock_schedule(
    principal_per_inst: Decimal = Decimal("1000.00"),
    interest_per_inst: Decimal = Decimal("100.00"),
    tenure: int = 5,
    start_date: date = date(2026, 1, 1),
) -> list[LoanSchedule]:
    items = []
    for i in range(1, tenure + 1):
        items.append(
            LoanSchedule(
                id=uuid.uuid4(),
                installment_no=i,
                due_date=date(2026, i, 1),
                principal_due=principal_per_inst,
                interest_due=interest_per_inst,
                total_due=principal_per_inst + interest_per_inst,
                principal_paid=Decimal("0.00"),
                interest_paid=Decimal("0.00"),
                penalty_paid=Decimal("0.00"),
                penalty_due=Decimal("0.00"),
                status=LoanScheduleStatus.PENDING,
            )
        )
    return items


def test_allocation_exact_single_installment():
    """Exact payment clears installment 1 to PAID."""
    loan = _create_mock_loan(Decimal("5000.00"))
    schedule = _create_mock_schedule(tenure=5)

    # Installment 1 has ₹1000 principal, ₹100 interest
    as_of = date(2026, 1, 15)
    result = allocate_repayment(
        loan=loan,
        schedule_items=schedule,
        payment_amount=Decimal("1100.00"),
        as_of_date=as_of,
    )

    assert result.total_payment == Decimal("1100.00")
    assert result.total_penalty == Decimal("0.00")
    assert result.total_interest == Decimal("100.00")
    assert result.total_principal == Decimal("1000.00")
    assert result.prepayment_principal == Decimal("0.00")
    assert result.is_loan_fully_paid is False

    # Check installment 1 status
    assert schedule[0].status == LoanScheduleStatus.PAID
    assert schedule[0].principal_paid == Decimal("1000.00")
    assert schedule[0].interest_paid == Decimal("100.00")

    # Installment 2 untouched
    assert schedule[1].status == LoanScheduleStatus.PENDING
    assert schedule[1].principal_paid == Decimal("0.00")


def test_allocation_partial_payment():
    """Partial payment leaves installment in PARTIAL status."""
    loan = _create_mock_loan(Decimal("5000.00"))
    schedule = _create_mock_schedule(tenure=5)

    # Paying ₹600 on installment 1 (due ₹1000 principal, ₹100 interest)
    as_of = date(2026, 1, 15)
    result = allocate_repayment(
        loan=loan,
        schedule_items=schedule,
        payment_amount=Decimal("600.00"),
        as_of_date=as_of,
    )

    assert result.total_interest == Decimal("100.00")
    assert result.total_principal == Decimal("500.00")
    assert schedule[0].status == LoanScheduleStatus.PARTIAL
    assert schedule[0].interest_paid == Decimal("100.00")
    assert schedule[0].principal_paid == Decimal("500.00")


def test_allocation_penalty_first():
    """Penalty is cleared before interest and principal on overdue installments."""
    loan = _create_mock_loan(Decimal("5000.00"))
    schedule = _create_mock_schedule(tenure=5)

    # Installment 1 has accrued late penalty of ₹50
    schedule[0].penalty_due = Decimal("50.00")
    schedule[0].status = LoanScheduleStatus.OVERDUE

    as_of = date(2026, 1, 20)
    # Payment of ₹120: should pay ₹50 penalty, ₹70 interest, ₹0 principal
    result = allocate_repayment(
        loan=loan,
        schedule_items=schedule,
        payment_amount=Decimal("120.00"),
        as_of_date=as_of,
    )

    assert result.total_penalty == Decimal("50.00")
    assert result.total_interest == Decimal("70.00")
    assert result.total_principal == Decimal("0.00")
    assert schedule[0].penalty_paid == Decimal("50.00")
    assert schedule[0].interest_paid == Decimal("70.00")
    assert schedule[0].principal_paid == Decimal("0.00")
    assert schedule[0].status == LoanScheduleStatus.PARTIAL


def test_allocation_overpayment_is_prepayment_reducing_tenure():
    """
    Overpayment beyond current due is treated as prepayment
    applied to next installments' principal (reducing tenure).
    """
    loan = _create_mock_loan(Decimal("5000.00"))
    schedule = _create_mock_schedule(tenure=5)

    # Current due is Installment 1 (₹100 int + ₹1000 princ = ₹1100 total)
    # Pay ₹1500 (₹400 overpayment)
    as_of = date(2026, 1, 15)
    result = allocate_repayment(
        loan=loan,
        schedule_items=schedule,
        payment_amount=Decimal("1500.00"),
        as_of_date=as_of,
    )

    assert result.total_penalty == Decimal("0.00")
    assert result.total_interest == Decimal("100.00")
    assert result.total_principal == Decimal("1400.00")
    assert result.prepayment_principal == Decimal("400.00")

    # Installment 1 fully paid
    assert schedule[0].status == LoanScheduleStatus.PAID
    assert schedule[0].principal_paid == Decimal("1000.00")

    # Installment 2 receives ₹400 towards principal
    assert schedule[1].status == LoanScheduleStatus.PARTIAL
    assert schedule[1].principal_paid == Decimal("400.00")
    assert schedule[1].interest_paid == Decimal("0.00")  # unearned future interest untouched


def test_allocation_multi_installment():
    """Payment covers multiple overdue installments in chronological order."""
    loan = _create_mock_loan(Decimal("5000.00"))
    schedule = _create_mock_schedule(tenure=5)

    # As of March 15, Installments 1, 2, and 3 are past due
    as_of = date(2026, 3, 15)
    # Each is 100 int + 1000 princ. Total for 1 and 2 is 2200.
    # Pay 2500: clears 1 and 2 completely, applies 100 int + 200 princ to 3.
    result = allocate_repayment(
        loan=loan,
        schedule_items=schedule,
        payment_amount=Decimal("2500.00"),
        as_of_date=as_of,
    )

    assert result.total_payment == Decimal("2500.00")
    assert result.total_interest == Decimal("300.00")  # 100 on #1, 100 on #2, 100 on #3
    assert result.total_principal == Decimal("2200.00")  # 1000 on #1, 1000 on #2, 200 on #3

    assert schedule[0].status == LoanScheduleStatus.PAID
    assert schedule[1].status == LoanScheduleStatus.PAID
    assert schedule[2].status == LoanScheduleStatus.PARTIAL
    assert schedule[2].interest_paid == Decimal("100.00")
    assert schedule[2].principal_paid == Decimal("200.00")


def test_allocation_full_payoff_closes_loan():
    """Paying all remaining principal and due interest/penalty marks loan as fully paid."""
    loan = _create_mock_loan(Decimal("3000.00"))
    schedule = _create_mock_schedule(tenure=3)

    # Total due = 3 * 1000 principal + 3 * 100 interest = 3300
    as_of = date(2026, 3, 15)
    result = allocate_repayment(
        loan=loan,
        schedule_items=schedule,
        payment_amount=Decimal("3300.00"),
        as_of_date=as_of,
    )

    assert result.is_loan_fully_paid is True
    assert all(s.status == LoanScheduleStatus.PAID for s in schedule)


def test_allocation_excess_payment_raises_error():
    """Paying more than total outstanding payoff amount is rejected."""
    loan = _create_mock_loan(Decimal("3000.00"))
    schedule = _create_mock_schedule(tenure=3)

    # Total payoff is 3300. Attempting to pay 4000.
    with pytest.raises(AppError) as exc_info:
        allocate_repayment(
            loan=loan,
            schedule_items=schedule,
            payment_amount=Decimal("4000.00"),
            as_of_date=date(2026, 1, 1),
        )
    assert exc_info.value.code == "EXCESS_REPAYMENT_AMOUNT"
