from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.core.errors import AppError
from app.core.money import quantize_money
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus


@dataclass
class InstallmentAllocationDetail:
    installment_no: int
    due_date: date
    penalty_allocated: Decimal
    interest_allocated: Decimal
    principal_allocated: Decimal
    total_allocated: Decimal
    status_before: LoanScheduleStatus
    status_after: LoanScheduleStatus


@dataclass
class _InstTracker:
    penalty: Decimal
    interest: Decimal
    principal: Decimal
    status_before: LoanScheduleStatus


@dataclass
class RepaymentAllocationResult:
    total_payment: Decimal
    total_penalty: Decimal
    total_interest: Decimal
    total_principal: Decimal
    prepayment_principal: Decimal
    installments_allocated: list[InstallmentAllocationDetail] = field(default_factory=list)
    is_loan_fully_paid: bool = False
    unallocated_amount: Decimal = Decimal("0.00")


def allocate_repayment(
    loan: Loan,
    schedule_items: list[LoanSchedule],
    payment_amount: Decimal,
    as_of_date: date,
    prepayment_policy: str = "REDUCE_TENURE",
) -> RepaymentAllocationResult:
    """
    Allocates a repayment per SPEC section 6.4:
    Order of allocation:
    1. Late penalty on due/overdue installments (oldest first)
    2. Interest due on due/overdue installments (oldest first)
    3. Principal due on due/overdue installments (oldest first)
    4. Overpayment is treated as prepayment applied to next installments' principal
       (reducing tenure by default).
    Partial payments leave installments as PARTIAL.
    """
    payment_amount = quantize_money(payment_amount)
    if payment_amount <= Decimal("0.00"):
        raise AppError(
            code="INVALID_REPAYMENT_AMOUNT",
            message="Repayment amount must be strictly positive.",
            status_code=400,
        )

    # Calculate total payoff amount across the entire loan
    total_rem_principal = sum(i.principal_due - i.principal_paid for i in schedule_items)
    total_rem_interest = sum(i.interest_due - i.interest_paid for i in schedule_items)
    total_rem_penalty = sum(i.penalty_due - i.penalty_paid for i in schedule_items)
    total_payoff = quantize_money(total_rem_principal + total_rem_interest + total_rem_penalty)

    if payment_amount > total_payoff:
        raise AppError(
            code="EXCESS_REPAYMENT_AMOUNT",
            message=f"Repayment amount ₹{payment_amount} exceeds total loan payoff amount of ₹{total_payoff}.",
            status_code=400,
            details={
                "payment_amount": str(payment_amount),
                "total_payoff": str(total_payoff),
                "outstanding_principal": str(total_rem_principal),
                "outstanding_interest": str(total_rem_interest),
                "outstanding_penalty": str(total_rem_penalty),
            },
        )

    remaining = payment_amount
    total_penalty = Decimal("0.00")
    total_interest = Decimal("0.00")
    total_principal = Decimal("0.00")
    prepayment_principal = Decimal("0.00")

    # Sort schedule by installment_no ascending
    sorted_schedule = sorted(schedule_items, key=lambda s: s.installment_no)

    # Tracking per installment changes
    inst_allocations: dict[int, _InstTracker] = {
        s.installment_no: _InstTracker(
            penalty=Decimal("0.00"),
            interest=Decimal("0.00"),
            principal=Decimal("0.00"),
            status_before=s.status,
        )
        for s in sorted_schedule
    }

    # Step 1: Allocate towards penalties (oldest installment first)
    for inst in sorted_schedule:
        if inst.status == LoanScheduleStatus.PAID:
            continue
        unpaid_penalty = quantize_money(inst.penalty_due - inst.penalty_paid)
        if unpaid_penalty > Decimal("0.00") and remaining > Decimal("0.00"):
            alloc = min(remaining, unpaid_penalty)
            inst.penalty_paid = quantize_money(inst.penalty_paid + alloc)
            remaining = quantize_money(remaining - alloc)
            total_penalty = quantize_money(total_penalty + alloc)
            inst_allocations[inst.installment_no].penalty += alloc

    # Identify installments that are currently due or already past due
    due_installments = [
        s for s in sorted_schedule
        if s.status != LoanScheduleStatus.PAID and s.due_date <= as_of_date
    ]
    # If no past-due installments exist, the earliest unpaid installment is considered the current due installment
    if not due_installments:
        earliest_unpaid = next((s for s in sorted_schedule if s.status != LoanScheduleStatus.PAID), None)
        if earliest_unpaid:
            due_installments = [earliest_unpaid]

    # Step 2: Allocate towards interest due on current/due installments (oldest first)
    for inst in due_installments:
        unpaid_interest = quantize_money(inst.interest_due - inst.interest_paid)
        if unpaid_interest > Decimal("0.00") and remaining > Decimal("0.00"):
            alloc = min(remaining, unpaid_interest)
            inst.interest_paid = quantize_money(inst.interest_paid + alloc)
            remaining = quantize_money(remaining - alloc)
            total_interest = quantize_money(total_interest + alloc)
            inst_allocations[inst.installment_no].interest += alloc

    # Step 3: Allocate towards principal due on current/due installments (oldest first)
    for inst in due_installments:
        unpaid_principal = quantize_money(inst.principal_due - inst.principal_paid)
        if unpaid_principal > Decimal("0.00") and remaining > Decimal("0.00"):
            alloc = min(remaining, unpaid_principal)
            inst.principal_paid = quantize_money(inst.principal_paid + alloc)
            remaining = quantize_money(remaining - alloc)
            total_principal = quantize_money(total_principal + alloc)
            inst_allocations[inst.installment_no].principal += alloc

    # Step 4: Overpayment beyond current due is treated as prepayment
    # applied to the next installments' principal (reducing tenure)
    if remaining > Decimal("0.00"):
        future_installments = [
            s for s in sorted_schedule
            if s not in due_installments and s.status != LoanScheduleStatus.PAID
        ]
        for inst in future_installments:
            unpaid_principal = quantize_money(inst.principal_due - inst.principal_paid)
            if unpaid_principal > Decimal("0.00") and remaining > Decimal("0.00"):
                alloc = min(remaining, unpaid_principal)
                inst.principal_paid = quantize_money(inst.principal_paid + alloc)
                remaining = quantize_money(remaining - alloc)
                total_principal = quantize_money(total_principal + alloc)
                prepayment_principal = quantize_money(prepayment_principal + alloc)
                inst_allocations[inst.installment_no].principal += alloc

    # Step 4b: If excess remains after paying all future principal,
    # allocate to future installments' interest (oldest first)
    if remaining > Decimal("0.00"):
        future_installments = [
            s for s in sorted_schedule
            if s not in due_installments and s.status != LoanScheduleStatus.PAID
        ]
        for inst in future_installments:
            unpaid_interest = quantize_money(inst.interest_due - inst.interest_paid)
            if unpaid_interest > Decimal("0.00") and remaining > Decimal("0.00"):
                alloc = min(remaining, unpaid_interest)
                inst.interest_paid = quantize_money(inst.interest_paid + alloc)
                remaining = quantize_money(remaining - alloc)
                total_interest = quantize_money(total_interest + alloc)
                inst_allocations[inst.installment_no].interest += alloc

    # Step 5: Update statuses of all schedule items
    details: list[InstallmentAllocationDetail] = []
    for inst in sorted_schedule:
        unpaid_p = quantize_money(inst.principal_due - inst.principal_paid)
        unpaid_i = quantize_money(inst.interest_due - inst.interest_paid)
        unpaid_pen = quantize_money(inst.penalty_due - inst.penalty_paid)

        # Status determination:
        # An installment is PAID if its principal, interest, and penalty are fully settled.
        if unpaid_p <= Decimal("0.00") and unpaid_i <= Decimal("0.00") and unpaid_pen <= Decimal("0.00"):
            inst.status = LoanScheduleStatus.PAID
        elif (
            inst.principal_paid > Decimal("0.00")
            or inst.interest_paid > Decimal("0.00")
            or inst.penalty_paid > Decimal("0.00")
        ):
            inst.status = LoanScheduleStatus.PARTIAL
        elif inst.due_date < as_of_date:
            inst.status = LoanScheduleStatus.OVERDUE
        else:
            inst.status = LoanScheduleStatus.PENDING

        alloc_data = inst_allocations[inst.installment_no]
        tot_alloc = alloc_data.penalty + alloc_data.interest + alloc_data.principal
        if tot_alloc > Decimal("0.00") or alloc_data.status_before != inst.status:
            details.append(
                InstallmentAllocationDetail(
                    installment_no=inst.installment_no,
                    due_date=inst.due_date,
                    penalty_allocated=alloc_data.penalty,
                    interest_allocated=alloc_data.interest,
                    principal_allocated=alloc_data.principal,
                    total_allocated=tot_alloc,
                    status_before=alloc_data.status_before,
                    status_after=inst.status,
                )
            )

    # Check if whole loan is completely paid off
    all_principal_settled = all(
        i.principal_paid >= i.principal_due for i in sorted_schedule
    )
    all_due_interest_settled = all(
        i.interest_paid >= i.interest_due for i in sorted_schedule
    )
    all_penalties_settled = all(
        i.penalty_paid >= i.penalty_due for i in sorted_schedule
    )
    is_fully_paid = (
        all_principal_settled and all_due_interest_settled and all_penalties_settled
    )

    return RepaymentAllocationResult(
        total_payment=payment_amount,
        total_penalty=total_penalty,
        total_interest=total_interest,
        total_principal=total_principal,
        prepayment_principal=prepayment_principal,
        installments_allocated=details,
        is_loan_fully_paid=is_fully_paid,
        unallocated_amount=remaining,
    )
