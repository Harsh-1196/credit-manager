from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import AppError
from app.core.money import quantize_money
from app.db.models.shg import InterestType


@dataclass(frozen=True)
class ScheduleInstallmentDTO:
    installment_no: int
    due_date: date
    principal_due: Decimal
    interest_due: Decimal
    total_due: Decimal
    outstanding_balance: Decimal


@dataclass(frozen=True)
class LoanScheduleResultDTO:
    principal: Decimal
    total_interest: Decimal
    total_amount: Decimal
    monthly_installment: Decimal
    installments: list[ScheduleInstallmentDTO]


def add_months(start_date: date, months: int) -> date:
    """
    Adds a given number of months to a date, pinning to the last valid day
    of the target month if needed (e.g. 2025-01-31 + 1 month -> 2025-02-28).
    """
    new_month = start_date.month + months
    new_year = start_date.year + (new_month - 1) // 12
    new_month = (new_month - 1) % 12 + 1

    # Find the maximum valid day in target month
    if new_month in (1, 3, 5, 7, 8, 10, 12):
        max_day = 31
    elif new_month in (4, 6, 9, 11):
        max_day = 30
    else:
        # February
        is_leap = (new_year % 4 == 0 and new_year % 100 != 0) or (new_year % 400 == 0)
        max_day = 29 if is_leap else 28

    return date(new_year, new_month, min(start_date.day, max_day))


def calculate_flat_schedule(
    principal: Decimal,
    annual_rate: Decimal,
    tenure_months: int,
    first_due_date: date,
) -> LoanScheduleResultDTO:
    """
    Computes flat interest repayment schedule:
    - total_interest = principal * (annual_rate / 100) * (tenure_months / 12)
    - principal_part = round(principal / tenure_months, 2)
    - interest_part  = round(total_interest / tenure_months, 2)
    - Last installment absorbs any fractional residue so sum(principal_due) == principal
      and sum(interest_due) == total_interest exactly.
    """
    total_interest = quantize_money(
        principal * (annual_rate / Decimal(100)) * (Decimal(tenure_months) / Decimal(12))
    )

    total_p_cents = int((principal * Decimal(100)).to_integral_value())
    base_p_cents = total_p_cents // tenure_months
    rem_p_cents = total_p_cents % tenure_months

    total_i_cents = int((total_interest * Decimal(100)).to_integral_value())
    base_i_cents = total_i_cents // tenure_months
    rem_i_cents = total_i_cents % tenure_months

    installments: list[ScheduleInstallmentDTO] = []
    current_outstanding = principal

    for i in range(1, tenure_months + 1):
        due_date = add_months(first_due_date, i - 1)

        p_cents = base_p_cents + (1 if i <= rem_p_cents else 0)
        i_cents = base_i_cents + (1 if i <= rem_i_cents else 0)

        p_due = Decimal(p_cents) / Decimal(100)
        i_due = Decimal(i_cents) / Decimal(100)

        current_outstanding -= p_due

        installments.append(
            ScheduleInstallmentDTO(
                installment_no=i,
                due_date=due_date,
                principal_due=p_due,
                interest_due=i_due,
                total_due=p_due + i_due,
                outstanding_balance=max(Decimal("0.00"), current_outstanding),
            )
        )

    monthly_installment = (
        installments[0].total_due if installments else Decimal("0.00")
    )
    return LoanScheduleResultDTO(
        principal=principal,
        total_interest=total_interest,
        total_amount=principal + total_interest,
        monthly_installment=monthly_installment,
        installments=installments,
    )


def calculate_reducing_schedule(
    principal: Decimal,
    annual_rate: Decimal,
    tenure_months: int,
    first_due_date: date,
) -> LoanScheduleResultDTO:
    """
    Computes reducing balance (EMI) repayment schedule:
    - r = (annual_rate / 12) / 100
    - EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
      if r == 0: EMI = round(P / n, 2)
    - Each month:
        interest_i  = round(outstanding * r, 2)
        principal_i = EMI - interest_i
    - Last month:
        principal_n = outstanding (absorbs remaining principal residue)
        interest_n  = round(outstanding * r, 2)
        total_n     = principal_n + interest_n
    """
    r = (annual_rate / Decimal(12)) / Decimal(100)

    if r == Decimal("0.00"):
        emi = (principal / Decimal(tenure_months)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        one_plus_r_n = (Decimal(1) + r) ** tenure_months
        emi_exact = principal * r * one_plus_r_n / (one_plus_r_n - Decimal(1))
        emi = emi_exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    installments: list[ScheduleInstallmentDTO] = []
    current_outstanding = principal
    total_interest = Decimal("0.00")

    for i in range(1, tenure_months + 1):
        due_date = add_months(first_due_date, i - 1)
        interest_due = (current_outstanding * r).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if i == tenure_months:
            # Last installment absorbs remaining principal residue
            principal_due = current_outstanding
        else:
            principal_due = emi - interest_due

        current_outstanding -= principal_due
        total_interest += interest_due

        installments.append(
            ScheduleInstallmentDTO(
                installment_no=i,
                due_date=due_date,
                principal_due=principal_due,
                interest_due=interest_due,
                total_due=principal_due + interest_due,
                outstanding_balance=max(Decimal("0.00"), current_outstanding),
            )
        )

    return LoanScheduleResultDTO(
        principal=principal,
        total_interest=total_interest,
        total_amount=principal + total_interest,
        monthly_installment=emi,
        installments=installments,
    )


def calculate_loan_schedule(
    principal: Decimal,
    annual_rate: Decimal,
    interest_type: InterestType | str,
    tenure_months: int,
    first_due_date: date,
) -> LoanScheduleResultDTO:
    """
    Public entry point for calculating loan schedules.
    Validates non-negotiable rules and dispatches to flat or reducing calculations.
    """
    principal = quantize_money(principal)
    annual_rate = Decimal(str(annual_rate))

    if principal <= Decimal("0.00"):
        raise AppError(
            code="INVALID_LOAN_PARAMETERS",
            message="Loan principal must be strictly positive.",
            status_code=400,
        )

    if tenure_months < 1:
        raise AppError(
            code="INVALID_LOAN_PARAMETERS",
            message="Loan tenure must be at least 1 month.",
            status_code=400,
        )

    if annual_rate < Decimal("0.00"):
        raise AppError(
            code="INVALID_LOAN_PARAMETERS",
            message="Interest rate cannot be negative.",
            status_code=400,
        )

    i_type = (
        interest_type.value
        if isinstance(interest_type, InterestType)
        else str(interest_type).upper()
    )

    if i_type == InterestType.FLAT.value:
        return calculate_flat_schedule(
            principal=principal,
            annual_rate=annual_rate,
            tenure_months=tenure_months,
            first_due_date=first_due_date,
        )
    elif i_type == InterestType.REDUCING.value:
        return calculate_reducing_schedule(
            principal=principal,
            annual_rate=annual_rate,
            tenure_months=tenure_months,
            first_due_date=first_due_date,
        )
    else:
        raise AppError(
            code="INVALID_INTEREST_TYPE",
            message=f"Unsupported interest calculation type: {interest_type}",
            status_code=400,
        )
