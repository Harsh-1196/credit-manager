import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import quantize_money
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.outbox import OutboxConsumerLog, OutboxEvent
from app.domain.outbox.service import get_or_create_dashboard_read_model

logger = logging.getLogger(__name__)


async def is_event_already_processed(
    db: AsyncSession,
    consumer_name: str,
    event_id: uuid.UUID,
) -> bool:
    """Verifies whether an outbox event was already processed by this specific consumer."""
    stmt = select(OutboxConsumerLog).where(
        OutboxConsumerLog.consumer_name == consumer_name,
        OutboxConsumerLog.event_id == event_id,
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none() is not None


async def log_consumer_success(
    db: AsyncSession,
    consumer_name: str,
    event: OutboxEvent,
) -> None:
    """Records deduplication log row atomically with consumer side effects."""
    log_entry = OutboxConsumerLog(
        consumer_name=consumer_name,
        event_id=event.id,
        shg_id=event.shg_id,
    )
    db.add(log_entry)
    await db.flush()


async def dashboard_read_model_consumer(
    db: AsyncSession,
    event: OutboxEvent,
) -> None:
    """
    Consumer 1: Updates the denormalized dashboard read model table.
    Strictly idempotent: replaying an event executes zero duplicate operations.
    """
    consumer_name = "dashboard_read_model"
    if await is_event_already_processed(db, consumer_name, event.id):
        logger.info("Event %s already processed by consumer %s; skipping duplicate.", event.id, consumer_name)
        return

    if not event.shg_id:
        await log_consumer_success(db, consumer_name, event)
        return

    read_model = await get_or_create_dashboard_read_model(db, event.shg_id)
    payload = event.payload

    if event.event_type == "LOAN_DISBURSED":
        principal = Decimal(str(payload.get("principal", "0.00")))
        processing_fee = Decimal(str(payload.get("processing_fee", "0.00")))
        net_cash_out = quantize_money(principal - processing_fee)

        read_model.total_loans_disbursed = quantize_money(read_model.total_loans_disbursed + principal)
        read_model.total_principal_outstanding = quantize_money(read_model.total_principal_outstanding + principal)
        read_model.group_cash_balance = quantize_money(read_model.group_cash_balance - net_cash_out)
        read_model.active_loans_count += 1

    elif event.event_type == "LOAN_REPAID":
        total_payment = Decimal(str(payload.get("amount", "0.00")))
        principal_paid = Decimal(str(payload.get("principal_paid", "0.00")))
        interest_paid = Decimal(str(payload.get("interest_paid", "0.00")))
        penalty_paid = Decimal(str(payload.get("penalty_paid", "0.00")))
        is_fully_paid = bool(payload.get("is_fully_paid", False))

        read_model.total_principal_outstanding = quantize_money(
            max(Decimal("0.00"), read_model.total_principal_outstanding - principal_paid)
        )
        read_model.total_interest_collected = quantize_money(read_model.total_interest_collected + interest_paid)
        read_model.total_penalties_collected = quantize_money(read_model.total_penalties_collected + penalty_paid)
        read_model.group_cash_balance = quantize_money(read_model.group_cash_balance + total_payment)

        if is_fully_paid:
            read_model.active_loans_count = max(0, read_model.active_loans_count - 1)

    elif event.event_type == "SAVINGS_COLLECTED":
        amount = Decimal(str(payload.get("amount", "0.00")))
        fine_amount = Decimal(str(payload.get("fine_amount", "0.00")))
        total_cash_in = quantize_money(amount + fine_amount)

        read_model.total_savings = quantize_money(read_model.total_savings + amount)
        read_model.total_penalties_collected = quantize_money(read_model.total_penalties_collected + fine_amount)
        read_model.group_cash_balance = quantize_money(read_model.group_cash_balance + total_cash_in)

    elif event.event_type == "SAVINGS_WITHDRAWN":
        amount = Decimal(str(payload.get("amount", "0.00")))
        read_model.total_savings = quantize_money(max(Decimal("0.00"), read_model.total_savings - amount))
        read_model.group_cash_balance = quantize_money(read_model.group_cash_balance - amount)

    elif event.event_type == "ENTRY_REVERSED":
        # Handle reversal deltas if provided in payload
        rev_savings = Decimal(str(payload.get("reversed_savings", "0.00")))
        rev_principal = Decimal(str(payload.get("reversed_principal", "0.00")))
        rev_interest = Decimal(str(payload.get("reversed_interest", "0.00")))
        rev_penalty = Decimal(str(payload.get("reversed_penalty", "0.00")))
        rev_cash = Decimal(str(payload.get("reversed_cash", "0.00")))

        if rev_savings:
            read_model.total_savings = quantize_money(read_model.total_savings - rev_savings)
        if rev_principal:
            read_model.total_principal_outstanding = quantize_money(
                read_model.total_principal_outstanding + rev_principal
            )
        if rev_interest:
            read_model.total_interest_collected = quantize_money(
                max(Decimal("0.00"), read_model.total_interest_collected - rev_interest)
            )
        if rev_penalty:
            read_model.total_penalties_collected = quantize_money(
                max(Decimal("0.00"), read_model.total_penalties_collected - rev_penalty)
            )
        if rev_cash:
            read_model.group_cash_balance = quantize_money(read_model.group_cash_balance - rev_cash)

    read_model.last_event_id = event.id
    read_model.last_event_type = event.event_type
    await db.flush()

    await log_consumer_success(db, consumer_name, event)


async def overdue_and_par_consumer(
    db: AsyncSession,
    event: OutboxEvent,
) -> None:
    """
    Consumer 2: Refreshes overdue loan counts and PAR 30/60/90 figures.
    Strictly idempotent: replaying an event executes zero duplicate operations.
    """
    consumer_name = "overdue_and_par"
    if await is_event_already_processed(db, consumer_name, event.id):
        logger.info("Event %s already processed by consumer %s; skipping duplicate.", event.id, consumer_name)
        return

    if not event.shg_id:
        await log_consumer_success(db, consumer_name, event)
        return

    shg_id = event.shg_id
    read_model = await get_or_create_dashboard_read_model(db, shg_id)

    # Count active and overdue loans
    active_stmt = select(func.count(Loan.id)).where(
        Loan.shg_id == shg_id,
        Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
    )
    overdue_stmt = select(func.count(Loan.id)).where(
        Loan.shg_id == shg_id,
        Loan.status == LoanStatus.OVERDUE,
    )
    active_count = (await db.execute(active_stmt)).scalar_one() or 0
    overdue_count = (await db.execute(overdue_stmt)).scalar_one() or 0

    read_model.active_loans_count = active_count
    read_model.overdue_loans_count = overdue_count

    # Calculate PAR 30 / 60 / 90
    today = date.today()
    schedules_stmt = (
        select(LoanSchedule, Loan)
        .join(Loan, LoanSchedule.loan_id == Loan.id)
        .where(
            Loan.shg_id == shg_id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
            LoanSchedule.status.in_([LoanScheduleStatus.PENDING, LoanScheduleStatus.PARTIAL, LoanScheduleStatus.OVERDUE]),
            LoanSchedule.due_date < today,
        )
    )
    sched_res = await db.execute(schedules_stmt)
    rows = sched_res.all()

    # Track loans in PAR tiers by outstanding principal on loans that have installments overdue >= X days
    loans_with_overdue_days: dict[uuid.UUID, int] = {}
    loan_principals: dict[uuid.UUID, Decimal] = {}

    for sched, loan in rows:
        overdue_days = (today - sched.due_date).days
        curr_max = loans_with_overdue_days.get(loan.id, 0)
        if overdue_days > curr_max:
            loans_with_overdue_days[loan.id] = overdue_days

        if loan.id not in loan_principals:
            # Remaining principal on loan = loan.principal - sum(principal_paid)
            scheds_loan_stmt = select(func.sum(LoanSchedule.principal_paid)).where(LoanSchedule.loan_id == loan.id)
            total_principal_paid = (await db.execute(scheds_loan_stmt)).scalar_one() or Decimal("0.00")
            loan_principals[loan.id] = quantize_money(max(Decimal("0.00"), loan.principal - total_principal_paid))

    par_30 = Decimal("0.00")
    par_60 = Decimal("0.00")
    par_90 = Decimal("0.00")

    for loan_id, days in loans_with_overdue_days.items():
        rem_principal = loan_principals.get(loan_id, Decimal("0.00"))
        if days >= 30:
            par_30 += rem_principal
        if days >= 60:
            par_60 += rem_principal
        if days >= 90:
            par_90 += rem_principal

    read_model.par_30_amount = quantize_money(par_30)
    read_model.par_60_amount = quantize_money(par_60)
    read_model.par_90_amount = quantize_money(par_90)
    await db.flush()

    await log_consumer_success(db, consumer_name, event)
