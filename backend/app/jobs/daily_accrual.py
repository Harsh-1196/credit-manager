import argparse
import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.money import quantize_money
from app.db.models.auth import User, UserRole
from app.db.models.loans import Loan, LoanScheduleStatus, LoanStatus
from app.db.models.shg import GroupSettings
from app.db.session import AsyncSessionLocal
from app.domain.loans.state_machine import LoanStateMachine

logger = logging.getLogger("app.jobs.daily_accrual")


async def run_daily_accrual_job(
    db: AsyncSession,
    as_of_date: date | None = None,
    shg_id: uuid.UUID | None = None,
    actor_user: User | None = None,
) -> dict:
    """
    Daily loan maintenance job per SPEC sections 6.1 and 6.5:
    - Identifies installments overdue beyond fine_grace_days
    - Computes and records daily penalty accrual at penalty_interest_rate
    - Moves loan ACTIVE -> OVERDUE if any installment is overdue
    - Moves loan OVERDUE -> ACTIVE when cured
    - Closes loans when outstanding principal, interest, and penalties are zero
    - Never recomputes penalty for closed periods or already-calculated dates (strictly idempotent)
    """
    as_of = as_of_date or date.today()

    # System actor fallback
    if not actor_user:
        admin_stmt = select(User).where(User.role == UserRole.ADMIN).limit(1)
        admin_res = await db.execute(admin_stmt)
        actor_user = admin_res.scalar_one_or_none()
        if not actor_user:
            # Fallback mock admin object for system jobs
            actor_user = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                email="system@shg.internal",
                role=UserRole.ADMIN,
            )

    # 1. Fetch relevant loans (ACTIVE or OVERDUE)
    loans_query = (
        select(Loan)
        .options(selectinload(Loan.schedule), selectinload(Loan.member))
        .where(Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]))
    )
    if shg_id:
        loans_query = loans_query.where(Loan.shg_id == shg_id)

    loans_res = await db.execute(loans_query)
    loans: list[Loan] = list(loans_res.scalars().all())

    penalties_accrued: Decimal = Decimal("0.00")
    installments_marked_overdue: int = 0
    loans_moved_to_overdue: int = 0
    loans_cured_to_active: int = 0
    loans_closed: int = 0

    # Cache group settings
    settings_cache: dict[uuid.UUID, GroupSettings] = {}

    for loan in loans:
        if loan.shg_id not in settings_cache:
            stg_stmt = select(GroupSettings).where(GroupSettings.shg_id == loan.shg_id)
            stg_res = await db.execute(stg_stmt)
            settings_cache[loan.shg_id] = stg_res.scalar_one_or_none() or GroupSettings(shg_id=loan.shg_id)

        settings = settings_cache[loan.shg_id]
        grace_days = settings.fine_grace_days
        penalty_rate = settings.penalty_interest_rate  # e.g. 2.000% p.a.

        has_overdue_installment = False

        for inst in loan.schedule:
            # Skip already closed periods
            if inst.status == LoanScheduleStatus.PAID:
                continue

            unpaid_p = quantize_money(inst.principal_due - inst.principal_paid)
            unpaid_i = quantize_money(inst.interest_due - inst.interest_paid)

            grace_cutoff = inst.due_date + timedelta(days=grace_days)
            if as_of > grace_cutoff:
                # Installment is overdue
                if inst.status != LoanScheduleStatus.OVERDUE:
                    inst.status = LoanScheduleStatus.OVERDUE
                    installments_marked_overdue += 1

                has_overdue_installment = True

                # Calculate daily penalty accrual
                overdue_balance = unpaid_p + unpaid_i
                if overdue_balance > Decimal("0.00") and penalty_rate > Decimal("0.00"):
                    last_accrual = inst.last_penalty_accrual_date or grace_cutoff
                    if as_of > last_accrual:
                        days = (as_of - last_accrual).days
                        # Daily penalty rate based on annual penalty rate (365 days)
                        daily_rate = (penalty_rate / Decimal("100.00")) / Decimal("365.00")
                        accrued = quantize_money(overdue_balance * daily_rate * Decimal(days))

                        if accrued > Decimal("0.00"):
                            inst.penalty_due = quantize_money(inst.penalty_due + accrued)
                            penalties_accrued += accrued

                        inst.last_penalty_accrual_date = as_of

        # Evaluate loan-level lifecycle transitions
        total_outstanding = (
            sum((s.principal_due - s.principal_paid for s in loan.schedule), Decimal("0.00"))
            + sum((s.interest_due - s.interest_paid for s in loan.schedule), Decimal("0.00"))
            + sum((s.penalty_due - s.penalty_paid for s in loan.schedule), Decimal("0.00"))
        )

        if total_outstanding <= Decimal("0.00"):
            # Move to CLOSED
            await LoanStateMachine.transition(
                db=db,
                loan=loan,
                to_status=LoanStatus.CLOSED,
                actor=actor_user,
                reason="Loan fully settled with zero balance.",
            )
            loan.closed_at = datetime.now(UTC)
            loans_closed += 1
        elif has_overdue_installment and loan.status == LoanStatus.ACTIVE:
            # Move to OVERDUE
            await LoanStateMachine.transition(
                db=db,
                loan=loan,
                to_status=LoanStatus.OVERDUE,
                actor=actor_user,
                reason=f"Installments past due beyond {grace_days} grace days as of {as_of.isoformat()}.",
            )
            loans_moved_to_overdue += 1
        elif not has_overdue_installment and loan.status == LoanStatus.OVERDUE:
            # Move back to ACTIVE (cured)
            await LoanStateMachine.transition(
                db=db,
                loan=loan,
                to_status=LoanStatus.ACTIVE,
                actor=actor_user,
                reason=f"Overdue installments cured as of {as_of.isoformat()}.",
            )
            loans_cured_to_active += 1

    await db.commit()
    return {
        "as_of_date": as_of.isoformat(),
        "total_loans_evaluated": len(loans),
        "installments_marked_overdue": installments_marked_overdue,
        "penalties_accrued": str(quantize_money(penalties_accrued)),
        "loans_moved_to_overdue": loans_moved_to_overdue,
        "loans_cured_to_active": loans_cured_to_active,
        "loans_closed": loans_closed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily loan maintenance and penalty accrual job")
    parser.add_argument("--as-of-date", type=str, default=None, help="Evaluation date (YYYY-MM-DD)")
    parser.add_argument("--shg-id", type=str, default=None, help="Filter by SHG UUID")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else date.today()
    target_shg = uuid.UUID(args.shg_id) if args.shg_id else None

    async def _runner() -> None:
        async with AsyncSessionLocal() as session:
            res = await run_daily_accrual_job(session, as_of_date=as_of, shg_id=target_shg)
            print(f"Daily Accrual Job completed successfully: {res}")

    asyncio.run(_runner())


if __name__ == "__main__":
    main()
