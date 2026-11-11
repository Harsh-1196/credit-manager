import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.money import quantize_money
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus


@dataclass
class LoanSummaryFigures:
    loan_id: uuid.UUID
    loan_number: str
    status: LoanStatus
    principal: Decimal
    total_principal_paid: Decimal
    outstanding_principal: Decimal
    total_interest_due: Decimal
    total_interest_paid: Decimal
    outstanding_interest: Decimal
    total_penalty_due: Decimal
    total_penalty_paid: Decimal
    outstanding_penalty: Decimal
    total_outstanding_balance: Decimal
    next_due_date: date | None
    next_due_amount: Decimal
    days_overdue: int


@dataclass
class PortfolioMetrics:
    shg_id: uuid.UUID | None
    as_of_date: date
    total_loans_count: int
    active_loans_count: int
    overdue_loans_count: int
    closed_loans_count: int
    written_off_loans_count: int
    total_disbursed_principal: Decimal
    total_principal_repaid: Decimal
    total_outstanding_principal: Decimal
    total_overdue_principal: Decimal
    total_interest_outstanding: Decimal
    total_penalty_outstanding: Decimal
    par_30_principal: Decimal
    par_30_count: int
    par_30_ratio: Decimal  # percentage 0.00%
    par_60_principal: Decimal
    par_60_count: int
    par_60_ratio: Decimal
    par_90_principal: Decimal
    par_90_count: int
    par_90_ratio: Decimal


async def calculate_loan_summary_figures(
    db: AsyncSession,
    loan: Loan,
    as_of_date: date | None = None,
) -> LoanSummaryFigures:
    """Computes exact live balances and next installment due details for a specific loan."""
    as_of = as_of_date or date.today()

    # Ensure schedule is loaded
    if "schedule" not in loan.__dict__:
        stmt = select(LoanSchedule).where(LoanSchedule.loan_id == loan.id).order_by(LoanSchedule.installment_no)
        res = await db.execute(stmt)
        schedule = list(res.scalars().all())
    else:
        schedule = sorted(loan.schedule, key=lambda s: s.installment_no)

    tot_p_paid = sum((s.principal_paid for s in schedule), Decimal("0.00"))
    tot_i_due = sum((s.interest_due for s in schedule), Decimal("0.00"))
    tot_i_paid = sum((s.interest_paid for s in schedule), Decimal("0.00"))
    tot_pen_due = sum((s.penalty_due for s in schedule), Decimal("0.00"))
    tot_pen_paid = sum((s.penalty_paid for s in schedule), Decimal("0.00"))

    out_principal = quantize_money(max(Decimal("0.00"), loan.principal - tot_p_paid))
    out_interest = quantize_money(max(Decimal("0.00"), tot_i_due - tot_i_paid))
    out_penalty = quantize_money(max(Decimal("0.00"), tot_pen_due - tot_pen_paid))
    total_balance = quantize_money(out_principal + out_interest + out_penalty)

    # Next unpaid installment
    next_unpaid = next((s for s in schedule if s.status != LoanScheduleStatus.PAID), None)
    next_date = next_unpaid.due_date if next_unpaid else None
    if next_unpaid:
        p_rem = next_unpaid.principal_due - next_unpaid.principal_paid
        i_rem = next_unpaid.interest_due - next_unpaid.interest_paid
        pen_rem = next_unpaid.penalty_due - next_unpaid.penalty_paid
        next_amount = quantize_money(p_rem + i_rem + pen_rem)
    else:
        next_amount = Decimal("0.00")

    # Max days overdue across unpaid installments
    max_overdue_days = 0
    for s in schedule:
        if s.status != LoanScheduleStatus.PAID and s.due_date < as_of:
            diff = (as_of - s.due_date).days
            if diff > max_overdue_days:
                max_overdue_days = diff

    return LoanSummaryFigures(
        loan_id=loan.id,
        loan_number=loan.loan_number,
        status=loan.status,
        principal=loan.principal,
        total_principal_paid=quantize_money(tot_p_paid),
        outstanding_principal=out_principal,
        total_interest_due=quantize_money(tot_i_due),
        total_interest_paid=quantize_money(tot_i_paid),
        outstanding_interest=out_interest,
        total_penalty_due=quantize_money(tot_pen_due),
        total_penalty_paid=quantize_money(tot_pen_paid),
        outstanding_penalty=out_penalty,
        total_outstanding_balance=total_balance,
        next_due_date=next_date,
        next_due_amount=next_amount,
        days_overdue=max_overdue_days,
    )


async def calculate_portfolio_metrics(
    db: AsyncSession,
    shg_id: uuid.UUID | None = None,
    allowed_shg_ids: list[uuid.UUID] | None = None,
    as_of_date: date | None = None,
) -> PortfolioMetrics:
    """
    Computes portfolio quality metrics including PAR 30/60/90 per microfinance standards.
    PAR N = (Outstanding Principal of loans with installments overdue > N days) / (Total Outstanding Principal)
    """
    as_of = as_of_date or date.today()

    query = (
        select(Loan)
        .options(selectinload(Loan.schedule))
        .where(Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE, LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF]))
    )
    if shg_id:
        query = query.where(Loan.shg_id == shg_id)
    elif allowed_shg_ids is not None:
        query = query.where(Loan.shg_id.in_(allowed_shg_ids))

    res = await db.execute(query)
    loans = list(res.scalars().all())

    total_loans = len(loans)
    active_count = sum(1 for ln in loans if ln.status == LoanStatus.ACTIVE)
    overdue_count = sum(1 for ln in loans if ln.status == LoanStatus.OVERDUE)
    closed_count = sum(1 for ln in loans if ln.status == LoanStatus.CLOSED)
    written_off_count = sum(1 for ln in loans if ln.status == LoanStatus.WRITTEN_OFF)

    total_disbursed = sum((ln.principal for ln in loans), Decimal("0.00"))
    total_repaid = Decimal("0.00")
    total_out_principal = Decimal("0.00")
    total_overdue_principal = Decimal("0.00")
    total_int_out = Decimal("0.00")
    total_pen_out = Decimal("0.00")

    par_30_principal = Decimal("0.00")
    par_30_count = 0
    par_60_principal = Decimal("0.00")
    par_60_count = 0
    par_90_principal = Decimal("0.00")
    par_90_count = 0

    for loan in loans:
        p_paid = sum((s.principal_paid for s in loan.schedule), Decimal("0.00"))
        i_due = sum((s.interest_due for s in loan.schedule), Decimal("0.00"))
        i_paid = sum((s.interest_paid for s in loan.schedule), Decimal("0.00"))
        pen_due = sum((s.penalty_due for s in loan.schedule), Decimal("0.00"))
        pen_paid = sum((s.penalty_paid for s in loan.schedule), Decimal("0.00"))

        out_p = quantize_money(max(Decimal("0.00"), loan.principal - p_paid))
        total_repaid += p_paid

        # Only ACTIVE and OVERDUE loans count toward active portfolio at risk
        if loan.status in [LoanStatus.ACTIVE, LoanStatus.OVERDUE]:
            total_out_principal += out_p
            total_int_out += quantize_money(max(Decimal("0.00"), i_due - i_paid))
            total_pen_out += quantize_money(max(Decimal("0.00"), pen_due - pen_paid))

            # Check overdue installments
            max_days_for_loan = 0
            has_overdue_inst = False
            for s in loan.schedule:
                if s.status != LoanScheduleStatus.PAID and s.due_date < as_of:
                    has_overdue_inst = True
                    diff = (as_of - s.due_date).days
                    if diff > max_days_for_loan:
                        max_days_for_loan = diff

            if has_overdue_inst:
                total_overdue_principal += out_p

            if max_days_for_loan > 30:
                par_30_principal += out_p
                par_30_count += 1
            if max_days_for_loan > 60:
                par_60_principal += out_p
                par_60_count += 1
            if max_days_for_loan > 90:
                par_90_principal += out_p
                par_90_count += 1

    total_disbursed = quantize_money(total_disbursed)
    total_repaid = quantize_money(total_repaid)
    total_out_principal = quantize_money(total_out_principal)
    total_overdue_principal = quantize_money(total_overdue_principal)
    total_int_out = quantize_money(total_int_out)
    total_pen_out = quantize_money(total_pen_out)
    par_30_principal = quantize_money(par_30_principal)
    par_60_principal = quantize_money(par_60_principal)
    par_90_principal = quantize_money(par_90_principal)

    def calc_ratio(par_amt: Decimal) -> Decimal:
        if total_out_principal > Decimal("0.00"):
            return quantize_money((par_amt / total_out_principal) * Decimal("100.00"))
        return Decimal("0.00")

    return PortfolioMetrics(
        shg_id=shg_id,
        as_of_date=as_of,
        total_loans_count=total_loans,
        active_loans_count=active_count,
        overdue_loans_count=overdue_count,
        closed_loans_count=closed_count,
        written_off_loans_count=written_off_count,
        total_disbursed_principal=total_disbursed,
        total_principal_repaid=total_repaid,
        total_outstanding_principal=total_out_principal,
        total_overdue_principal=total_overdue_principal,
        total_interest_outstanding=total_int_out,
        total_penalty_outstanding=total_pen_out,
        par_30_principal=par_30_principal,
        par_30_count=par_30_count,
        par_30_ratio=calc_ratio(par_30_principal),
        par_60_principal=par_60_principal,
        par_60_count=par_60_count,
        par_60_ratio=calc_ratio(par_60_principal),
        par_90_principal=par_90_principal,
        par_90_count=par_90_count,
        par_90_ratio=calc_ratio(par_90_principal),
    )
