from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.db.models.shg import InterestType
from app.domain.loans.schedule import (
    calculate_flat_schedule,
    calculate_loan_schedule,
    calculate_reducing_schedule,
)


def test_reducing_balance_known_answer_spec_6_3():
    """
    SPEC 6.3 known-answer:
    Principal 50,000 at 12% for 12 months gives EMI 4,442.44.
    Verify last installment absorbs rounding residue so total principal sums to 50,000.00
    and final outstanding balance is strictly 0.00.
    """
    principal = Decimal("50000.00")
    rate = Decimal("12.00")
    tenure = 12
    start_date = date(2026, 4, 1)

    result = calculate_reducing_schedule(
        principal=principal,
        annual_rate=rate,
        tenure_months=tenure,
        first_due_date=start_date,
    )
    items = result.installments

    assert len(items) == 12

    # Verify standard EMI for first 11 installments
    for item in items[:-1]:
        assert item.total_due == Decimal("4442.44")

    # Installment 12 absorbs 1 paisa residue
    assert items[-1].principal_due == Decimal("4398.45")
    assert items[-1].interest_due == Decimal("43.98")
    assert items[-1].total_due == Decimal("4442.43")
    assert items[-1].outstanding_balance == Decimal("0.00")

    # Sum of principal parts must exactly equal original principal
    total_principal = sum(i.principal_due for i in items)
    assert total_principal == principal

    # Sum of totals == total principal + total interest
    total_interest = sum(i.interest_due for i in items)
    assert sum(i.total_due for i in items) == total_principal + total_interest


def test_flat_rate_known_answer_spec_6_3():
    """
    SPEC 6.3 known-answer:
    10,000 flat at 12% for 10 months gives interest 1,000.00 and installment 1,100.00.
    """
    principal = Decimal("10000.00")
    rate = Decimal("12.00")
    tenure = 10
    start_date = date(2026, 1, 15)

    result = calculate_flat_schedule(
        principal=principal,
        annual_rate=rate,
        tenure_months=tenure,
        first_due_date=start_date,
    )
    items = result.installments

    assert len(items) == 10

    total_principal = sum(i.principal_due for i in items)
    total_interest = sum(i.interest_due for i in items)

    assert total_principal == Decimal("10000.00")
    assert total_interest == Decimal("1000.00")

    for item in items:
        assert item.principal_due == Decimal("1000.00")
        assert item.interest_due == Decimal("100.00")
        assert item.total_due == Decimal("1100.00")

    assert items[-1].outstanding_balance == Decimal("0.00")


def test_zero_interest_rate_schedule():
    """A 0% loan should have 0 interest on all installments and divide principal cleanly."""
    principal = Decimal("10000.00")
    tenure = 3
    result = calculate_reducing_schedule(
        principal=principal,
        annual_rate=Decimal("0.00"),
        tenure_months=tenure,
        first_due_date=date(2026, 5, 1),
    )
    items = result.installments
    assert len(items) == 3
    for item in items:
        assert item.interest_due == Decimal("0.00")
    assert sum(i.principal_due for i in items) == principal
    assert items[-1].outstanding_balance == Decimal("0.00")


def test_single_month_tenure():
    """1-month tenure loan."""
    principal = Decimal("5000.00")
    rate = Decimal("12.00")
    result = calculate_reducing_schedule(
        principal=principal,
        annual_rate=rate,
        tenure_months=1,
        first_due_date=date(2026, 6, 1),
    )
    items = result.installments
    assert len(items) == 1
    # 5000 * 0.01 = 50.00 interest
    assert items[0].principal_due == Decimal("5000.00")
    assert items[0].interest_due == Decimal("50.00")
    assert items[0].total_due == Decimal("5050.00")
    assert items[0].outstanding_balance == Decimal("0.00")


def test_odd_tenures_and_residue():
    """Odd tenure (e.g. 7 months) where principal division leaves residue."""
    principal = Decimal("10000.00")
    rate = Decimal("15.00")
    for interest_type in [InterestType.REDUCING, InterestType.FLAT]:
        result = calculate_loan_schedule(
            principal=principal,
            annual_rate=rate,
            tenure_months=7,
            interest_type=interest_type,
            first_due_date=date(2026, 1, 1),
        )
        items = result.installments
        assert len(items) == 7
        assert sum(i.principal_due for i in items) == principal
        assert items[-1].outstanding_balance == Decimal("0.00")
        for item in items:
            assert item.total_due == item.principal_due + item.interest_due


def test_large_principal():
    """Large principal (e.g. 5,00,000) over 36 months."""
    principal = Decimal("500000.00")
    rate = Decimal("10.50")
    result = calculate_reducing_schedule(
        principal=principal,
        annual_rate=rate,
        tenure_months=36,
        first_due_date=date(2026, 1, 1),
    )
    items = result.installments
    assert len(items) == 36
    assert sum(i.principal_due for i in items) == principal
    assert items[-1].outstanding_balance == Decimal("0.00")


@settings(max_examples=50)
@given(
    principal_int=st.integers(min_value=100, max_value=1_000_000),
    rate_int=st.integers(min_value=0, max_value=3600),
    tenure=st.integers(min_value=1, max_value=60),
    interest_type=st.sampled_from([InterestType.REDUCING, InterestType.FLAT]),
)
def test_hypothesis_loan_schedule_properties(principal_int, rate_int, tenure, interest_type):
    """
    Property test:
    - Principal parts always sum to the principal exactly.
    - Each installment satisfies total_due == principal_due + interest_due.
    - Final outstanding balance is exactly 0.00.
    """
    principal = Decimal(principal_int)
    annual_rate = Decimal(rate_int) / Decimal("100")

    result = calculate_loan_schedule(
        principal=principal,
        annual_rate=annual_rate,
        tenure_months=tenure,
        interest_type=interest_type,
        first_due_date=date(2026, 1, 1),
    )
    items = result.installments

    assert len(items) == tenure
    total_principal = sum(i.principal_due for i in items)
    assert total_principal == principal

    for item in items:
        assert item.total_due == item.principal_due + item.interest_due
        assert item.principal_due >= Decimal("0.00")
        assert item.interest_due >= Decimal("0.00")
        assert item.outstanding_balance >= Decimal("0.00")

    assert items[-1].outstanding_balance == Decimal("0.00")
