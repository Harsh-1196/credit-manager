import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.money import quantize_money
from app.db.models.auth import User, UserRole
from app.db.models.ledger import Account, JournalEntry, JournalLine, JournalSourceType
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.shg import GroupSettings
from app.domain.ledger.accounts import (
    get_account_by_code,
    get_or_create_member_sub_accounts,
)
from app.domain.ledger.posting import PostingLineDTO, post_journal_entry
from app.domain.loans.allocation import (
    RepaymentAllocationResult,
    allocate_repayment,
)
from app.domain.loans.schedule import calculate_loan_schedule
from app.domain.loans.state_machine import LoanStateMachine


async def get_account_cash_balance(db: AsyncSession, account_id: uuid.UUID) -> Decimal:
    """Calculates balance of an Asset account: SUM(debit) - SUM(credit)."""
    stmt = select(
        func.coalesce(func.sum(JournalLine.debit), Decimal("0.00"))
        - func.coalesce(func.sum(JournalLine.credit), Decimal("0.00"))
    ).where(JournalLine.account_id == account_id)
    res = await db.execute(stmt)
    bal = res.scalar() or Decimal("0.00")
    return quantize_money(bal)


async def get_disburse_preview(
    db: AsyncSession,
    loan_id: uuid.UUID,
    shg_id: uuid.UUID,
) -> dict:
    """Provides a preview of journal lines and cash sufficiency for loan disbursal."""
    loan_stmt = (
        select(Loan)
        .options(selectinload(Loan.member))
        .where(Loan.id == loan_id, Loan.shg_id == shg_id)
    )
    loan_res = await db.execute(loan_stmt)
    loan = loan_res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=404)

    cash_acc = await get_account_by_code(db, shg_id, "1000")
    cash_balance = await get_account_cash_balance(db, cash_acc.id)
    net_disbursed = quantize_money(loan.principal - loan.processing_fee)

    member_loans_acc, _ = await get_or_create_member_sub_accounts(db, shg_id, loan.member)
    has_sufficient = cash_balance >= net_disbursed

    journal_lines = [
        {
            "account_code": member_loans_acc.code,
            "account_name": member_loans_acc.name,
            "debit": str(loan.principal),
            "credit": "0.00",
        },
        {
            "account_code": cash_acc.code,
            "account_name": cash_acc.name,
            "debit": "0.00",
            "credit": str(net_disbursed),
        },
    ]
    if loan.processing_fee > Decimal("0.00"):
        proc_acc = await get_account_by_code(db, shg_id, "4020")
        journal_lines.append(
            {
                "account_code": proc_acc.code,
                "account_name": proc_acc.name,
                "debit": "0.00",
                "credit": str(loan.processing_fee),
            }
        )

    return {
        "loan_id": str(loan.id),
        "loan_number": loan.loan_number,
        "member_name": loan.member.full_name,
        "principal": str(loan.principal),
        "processing_fee": str(loan.processing_fee),
        "net_disbursed": str(net_disbursed),
        "group_cash_balance": str(cash_balance),
        "has_sufficient_cash": has_sufficient,
        "journal_lines": journal_lines,
    }


async def disburse_loan(
    db: AsyncSession,
    loan_id: uuid.UUID,
    shg_id: uuid.UUID,
    current_user: User,
    first_due_date: date | None = None,
    expected_version: int | None = None,
    idempotency_key: str | None = None,
) -> Loan:
    """
    Disburses an approved loan per SPEC sections 6.1 and 14:
    - Row-level lock on the loan and cash account (with_for_update)
    - Verifies group cash sufficiency
    - Posts double-entry journal entry:
        Debit: Member Loans Receivable (1100-{member})
        Credit: Cash in Hand (1000) [net disbursed]
        Credit: Processing Fee Income (4020) [if fee > 0]
    - Generates loan_schedule rows
    - Transitions APPROVED -> DISBURSED -> ACTIVE
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
        raise AppError(code="UNAUTHORIZED", message="Only GROUP_LEADER or ADMIN can disburse loans.", status_code=403)

    # 1. Row-level lock on loan
    stmt = (
        select(Loan)
        .options(selectinload(Loan.member), selectinload(Loan.schedule))
        .where(Loan.id == loan_id, Loan.shg_id == shg_id)
        .with_for_update()
    )
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=404)

    if loan.status != LoanStatus.APPROVED:
        if idempotency_key:
            stmt_idem = select(JournalEntry).where(
                JournalEntry.shg_id == shg_id,
                JournalEntry.idempotency_key == idempotency_key,
            )
            res_idem = await db.execute(stmt_idem)
            if res_idem.scalar_one_or_none() and loan.status in [LoanStatus.DISBURSED, LoanStatus.ACTIVE]:
                return loan
        raise AppError(
            code="LOAN_NOT_APPROVED",
            message=f"Only APPROVED loans can be disbursed. Current status is {loan.status.value}.",
            status_code=400,
        )

    # 2. Row-level lock on cash account
    cash_acc = await get_account_by_code(db, shg_id, "1000")
    # Execute with_for_update on the cash account
    cash_lock_stmt = select(Account).where(Account.id == cash_acc.id).with_for_update()
    await db.execute(cash_lock_stmt)

    # 3. Check group cash sufficiency
    cash_balance = await get_account_cash_balance(db, cash_acc.id)
    net_disbursed = quantize_money(loan.principal - loan.processing_fee)
    if cash_balance < net_disbursed:
        raise AppError(
            code="INSUFFICIENT_GROUP_CASH",
            message=f"Group cash balance ₹{cash_balance} is insufficient to disburse net amount ₹{net_disbursed}.",
            status_code=400,
            details={"cash_balance": str(cash_balance), "net_disbursed": str(net_disbursed)},
        )

    # 4. Generate schedule installments
    start_date = first_due_date or (date.today() + relativedelta(months=1))
    calc_result = calculate_loan_schedule(
        principal=loan.principal,
        annual_rate=loan.interest_rate,
        tenure_months=loan.tenure_months,
        interest_type=loan.interest_type,
        first_due_date=start_date,
    )

    # Clear existing schedule if any was pre-seeded
    loan.schedule.clear()
    for item in calc_result.installments:
        sched_entry = LoanSchedule(
            loan_id=loan.id,
            installment_no=item.installment_no,
            due_date=item.due_date,
            principal_due=item.principal_due,
            interest_due=item.interest_due,
            total_due=item.total_due,
            principal_paid=Decimal("0.00"),
            interest_paid=Decimal("0.00"),
            penalty_paid=Decimal("0.00"),
            penalty_due=Decimal("0.00"),
            status=LoanScheduleStatus.PENDING,
        )
        loan.schedule.append(sched_entry)

    # 5. Post double-entry journal entry
    member_loans_acc, _ = await get_or_create_member_sub_accounts(db, shg_id, loan.member)
    lines = [
        PostingLineDTO(account_id=member_loans_acc.id, debit=loan.principal, credit=Decimal("0.00")),
        PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=net_disbursed),
    ]
    if loan.processing_fee > Decimal("0.00"):
        fee_acc = await get_account_by_code(db, shg_id, "4020")
        lines.append(PostingLineDTO(account_id=fee_acc.id, debit=Decimal("0.00"), credit=loan.processing_fee))

    entry_desc = f"Loan disbursal ({loan.loan_number}) for {loan.member.full_name}"
    if loan.processing_fee > Decimal("0.00"):
        entry_desc += f" (processing fee ₹{loan.processing_fee})"

    await post_journal_entry(
        db=db,
        shg_id=shg_id,
        entry_date=date.today(),
        description=entry_desc,
        source_type=JournalSourceType.DISBURSAL,
        lines=lines,
        posted_by=current_user.id,
        source_id=loan.id,
        idempotency_key=idempotency_key,
    )

    # 6. Transitions: APPROVED -> DISBURSED -> ACTIVE
    now = datetime.now(UTC)
    loan.disbursed_at = now
    loan.disbursed_by = current_user.id
    loan.first_due_date = start_date

    # Transition to DISBURSED
    await LoanStateMachine.transition(
        db=db,
        loan=loan,
        to_status=LoanStatus.DISBURSED,
        actor=current_user,
        reason="Loan disbursed and ledger entry posted",
        expected_version=expected_version,
    )

    # Transition DISBURSED -> ACTIVE
    await LoanStateMachine.transition(
        db=db,
        loan=loan,
        to_status=LoanStatus.ACTIVE,
        actor=current_user,
        reason="Repayment schedule active",
    )

    await db.flush()
    return loan


async def get_repayment_preview(
    db: AsyncSession,
    loan_id: uuid.UUID,
    shg_id: uuid.UUID,
    amount: Decimal,
    payment_date: date | None = None,
) -> dict:
    """Pre-calculates live repayment breakdown without modifying the database."""
    stmt = (
        select(Loan)
        .options(selectinload(Loan.schedule), selectinload(Loan.member))
        .where(Loan.id == loan_id, Loan.shg_id == shg_id)
    )
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=404)

    # Fetch group settings for prepayment policy
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == shg_id)
    settings_res = await db.execute(settings_stmt)
    settings = settings_res.scalar_one_or_none()
    policy = settings.prepayment_policy if settings else "REDUCE_TENURE"

    as_of = payment_date or date.today()

    # Clone schedule for dry-run
    sched_copies = [
        LoanSchedule(
            installment_no=s.installment_no,
            due_date=s.due_date,
            principal_due=s.principal_due,
            interest_due=s.interest_due,
            total_due=s.total_due,
            principal_paid=s.principal_paid,
            interest_paid=s.interest_paid,
            penalty_paid=s.penalty_paid,
            penalty_due=s.penalty_due,
            status=s.status,
        )
        for s in loan.schedule
    ]

    alloc_res = allocate_repayment(
        loan=loan,
        schedule_items=sched_copies,
        payment_amount=amount,
        as_of_date=as_of,
        prepayment_policy=policy,
    )

    # Calculate remaining principal after allocation
    new_tot_p_paid = sum(s.principal_paid for s in sched_copies)
    rem_principal_after = quantize_money(max(Decimal("0.00"), loan.principal - new_tot_p_paid))

    return {
        "loan_id": str(loan.id),
        "loan_number": loan.loan_number,
        "payment_amount": str(alloc_res.total_payment),
        "penalty_allocated": str(alloc_res.total_penalty),
        "interest_allocated": str(alloc_res.total_interest),
        "principal_allocated": str(alloc_res.total_principal),
        "prepayment_principal": str(alloc_res.prepayment_principal),
        "is_loan_fully_paid": alloc_res.is_loan_fully_paid,
        "remaining_principal_after": str(rem_principal_after),
        "installments_affected": [
            {
                "installment_no": item.installment_no,
                "due_date": item.due_date.isoformat(),
                "penalty_allocated": str(item.penalty_allocated),
                "interest_allocated": str(item.interest_allocated),
                "principal_allocated": str(item.principal_allocated),
                "total_allocated": str(item.total_allocated),
                "status_before": item.status_before.value,
                "status_after": item.status_after.value,
            }
            for item in alloc_res.installments_allocated
        ],
    }


async def repay_loan(
    db: AsyncSession,
    loan_id: uuid.UUID,
    shg_id: uuid.UUID,
    current_user: User,
    amount: Decimal,
    payment_date: date | None = None,
    expected_version: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[Loan, RepaymentAllocationResult]:
    """
    Records a loan repayment per SPEC sections 6.4, 6.5, and 14:
    - Row-level lock on the loan and its schedule (with_for_update)
    - Allocates payment (penalty -> interest -> principal -> prepayment)
    - Posts balanced multi-line double-entry journal entry:
        Debit: Cash (1000)
        Credit: Member Loans Receivable (1100-{member})
        Credit: Interest Income (4000) [if interest > 0]
        Credit: Fine and Penalty Income (4010) [if penalty > 0]
    - Updates loan status (ACTIVE / OVERDUE -> CLOSED if fully paid)
    - Returns updated loan and allocation result
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
        raise AppError(code="UNAUTHORIZED", message="Only GROUP_LEADER or ADMIN can record loan repayments.", status_code=403)

    # 1. Row-level lock on loan
    stmt = (
        select(Loan)
        .options(selectinload(Loan.member), selectinload(Loan.schedule))
        .where(Loan.id == loan_id, Loan.shg_id == shg_id)
        .with_for_update()
    )
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=404)

    if idempotency_key:
        stmt_idem = select(JournalEntry).where(
            JournalEntry.shg_id == shg_id,
            JournalEntry.idempotency_key == idempotency_key,
        )
        res_idem = await db.execute(stmt_idem)
        if res_idem.scalar_one_or_none():
            dummy_alloc = RepaymentAllocationResult(
                total_payment=amount,
                total_penalty=Decimal("0.00"),
                total_interest=Decimal("0.00"),
                total_principal=Decimal("0.00"),
                prepayment_principal=Decimal("0.00"),
                is_loan_fully_paid=(loan.status == LoanStatus.CLOSED),
            )
            return loan, dummy_alloc

    if loan.status not in [LoanStatus.ACTIVE, LoanStatus.OVERDUE]:
        raise AppError(
            code="LOAN_NOT_REPAYABLE",
            message=f"Cannot record repayment for loan in status '{loan.status.value}'. Must be ACTIVE or OVERDUE.",
            status_code=400,
        )

    # 2. Lock schedule items
    sched_stmt = (
        select(LoanSchedule)
        .where(LoanSchedule.loan_id == loan.id)
        .order_by(LoanSchedule.installment_no)
        .with_for_update()
    )
    sched_res = await db.execute(sched_stmt)
    schedule_items = list(sched_res.scalars().all())

    # 3. Prepayment policy from settings
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == shg_id)
    settings_res = await db.execute(settings_stmt)
    settings = settings_res.scalar_one_or_none()
    policy = settings.prepayment_policy if settings else "REDUCE_TENURE"

    as_of = payment_date or date.today()

    # 4. Allocate repayment across schedule
    alloc_result = allocate_repayment(
        loan=loan,
        schedule_items=schedule_items,
        payment_amount=amount,
        as_of_date=as_of,
        prepayment_policy=policy,
    )

    # 5. Post multi-line balanced double-entry journal entry
    cash_acc = await get_account_by_code(db, shg_id, "1000")
    member_loans_acc, _ = await get_or_create_member_sub_accounts(db, shg_id, loan.member)

    posting_lines = [
        PostingLineDTO(account_id=cash_acc.id, debit=alloc_result.total_payment, credit=Decimal("0.00")),
    ]
    if alloc_result.total_principal > Decimal("0.00"):
        posting_lines.append(
            PostingLineDTO(
                account_id=member_loans_acc.id,
                debit=Decimal("0.00"),
                credit=alloc_result.total_principal,
            )
        )
    if alloc_result.total_interest > Decimal("0.00"):
        interest_acc = await get_account_by_code(db, shg_id, "4000")
        posting_lines.append(
            PostingLineDTO(
                account_id=interest_acc.id,
                debit=Decimal("0.00"),
                credit=alloc_result.total_interest,
            )
        )
    if alloc_result.total_penalty > Decimal("0.00"):
        penalty_acc = await get_account_by_code(db, shg_id, "4010")
        posting_lines.append(
            PostingLineDTO(
                account_id=penalty_acc.id,
                debit=Decimal("0.00"),
                credit=alloc_result.total_penalty,
            )
        )

    desc = f"Loan repayment ({loan.loan_number}) from {loan.member.full_name}: ₹{alloc_result.total_payment}"
    parts = []
    if alloc_result.total_principal > Decimal("0.00"):
        parts.append(f"principal ₹{alloc_result.total_principal}")
    if alloc_result.total_interest > Decimal("0.00"):
        parts.append(f"interest ₹{alloc_result.total_interest}")
    if alloc_result.total_penalty > Decimal("0.00"):
        parts.append(f"penalty ₹{alloc_result.total_penalty}")
    if parts:
        desc += f" ({', '.join(parts)})"

    await post_journal_entry(
        db=db,
        shg_id=shg_id,
        entry_date=as_of,
        description=desc,
        source_type=JournalSourceType.REPAYMENT,
        lines=posting_lines,
        posted_by=current_user.id,
        source_id=loan.id,
        idempotency_key=idempotency_key,
    )

    # 6. Status transitions
    if alloc_result.is_loan_fully_paid:
        await LoanStateMachine.transition(
            db=db,
            loan=loan,
            to_status=LoanStatus.CLOSED,
            actor=current_user,
            reason="All outstanding principal, interest, and penalties paid in full.",
            expected_version=expected_version,
        )
    elif loan.status == LoanStatus.OVERDUE:
        # Check if overdue condition cured
        has_overdue = any(s.status == LoanScheduleStatus.OVERDUE for s in schedule_items)
        if not has_overdue:
            await LoanStateMachine.transition(
                db=db,
                loan=loan,
                to_status=LoanStatus.ACTIVE,
                actor=current_user,
                reason="Overdue installments cleared by repayment.",
                expected_version=expected_version,
            )

    await db.flush()
    return loan, alloc_result


async def write_off_loan(
    db: AsyncSession,
    loan_id: uuid.UUID,
    shg_id: uuid.UUID,
    current_user: User,
    reason: str,
    expected_version: int | None = None,
) -> Loan:
    """
    Writes off an overdue loan per SPEC section 6.1:
    - Only ADMIN can write off
    - Loan must be in OVERDUE status
    - Reason is required
    - Posts double-entry:
        Debit: Loan Write-offs (5010)
        Credit: Member Loans Receivable (1100-{member})
    - Moves status to WRITTEN_OFF
    """
    if current_user.role != UserRole.ADMIN:
        raise AppError(code="FORBIDDEN_ROLE", message="Only an ADMIN can write off a loan.", status_code=403)

    if not reason or not reason.strip():
        raise AppError(code="REASON_REQUIRED", message="A formal reason is required to write off a loan.", status_code=400)

    stmt = (
        select(Loan)
        .options(selectinload(Loan.member), selectinload(Loan.schedule))
        .where(Loan.id == loan_id, Loan.shg_id == shg_id)
        .with_for_update()
    )
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=404)

    if loan.status != LoanStatus.OVERDUE:
        raise AppError(
            code="LOAN_NOT_OVERDUE",
            message=f"Only OVERDUE loans can be written off. Current status is '{loan.status.value}'.",
            status_code=400,
        )

    # Compute remaining principal
    total_principal_paid = sum(s.principal_paid for s in loan.schedule)
    unpaid_principal = quantize_money(max(Decimal("0.00"), loan.principal - total_principal_paid))

    if unpaid_principal <= Decimal("0.00"):
        raise AppError(
            code="NO_OUTSTANDING_PRINCIPAL",
            message="Loan has no outstanding principal to write off.",
            status_code=400,
        )

    # Post journal entry: Debit Write-offs (5010), Credit Loans Receivable (1100-{member})
    write_off_acc = await get_account_by_code(db, shg_id, "5010")
    member_loans_acc, _ = await get_or_create_member_sub_accounts(db, shg_id, loan.member)

    lines = [
        PostingLineDTO(account_id=write_off_acc.id, debit=unpaid_principal, credit=Decimal("0.00")),
        PostingLineDTO(account_id=member_loans_acc.id, debit=Decimal("0.00"), credit=unpaid_principal),
    ]

    await post_journal_entry(
        db=db,
        shg_id=shg_id,
        entry_date=date.today(),
        description=f"Loan write-off ({loan.loan_number}) for {loan.member.full_name}: {reason.strip()}",
        source_type=JournalSourceType.WRITE_OFF,
        lines=lines,
        posted_by=current_user.id,
        source_id=loan.id,
    )

    # Transition to WRITTEN_OFF
    now = datetime.now(UTC)
    loan.written_off_by = current_user.id
    loan.written_off_at = now
    loan.write_off_reason = reason.strip()

    await LoanStateMachine.transition(
        db=db,
        loan=loan,
        to_status=LoanStatus.WRITTEN_OFF,
        actor=current_user,
        reason=reason.strip(),
        expected_version=expected_version,
    )

    await db.flush()
    return loan
