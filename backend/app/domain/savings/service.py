import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.money import quantize_money
from app.db.models.ledger import Account, AccountType, JournalSourceType
from app.db.models.savings import SavingsDue, SavingsDueStatus
from app.db.models.shg import GroupSettings, Member, MemberStatus
from app.domain.ledger.accounts import get_account_by_code, get_or_create_member_sub_accounts
from app.domain.ledger.posting import PostingLineDTO, post_journal_entry


async def get_member_savings_balance(
    db: AsyncSession,
    shg_id: uuid.UUID,
    member_id: uuid.UUID,
) -> Decimal:
    """
    Computes a member's current savings balance directly from the double-entry ledger lines.
    Member savings is a LIABILITY: balance = SUM(credit) - SUM(debit).
    """
    stmt = (
        select(
            func.coalesce(func.sum(Account.lines.property.mapper.class_.credit), 0)
            - func.coalesce(func.sum(Account.lines.property.mapper.class_.debit), 0)
        )
        .select_from(Account)
        .join(Account.lines)
        .where(
            Account.shg_id == shg_id,
            Account.member_id == member_id,
            Account.type == AccountType.LIABILITY,
            Account.code.startswith("2000-"),
        )
    )
    res = await db.execute(stmt)
    raw_bal = res.scalar() or Decimal("0.00")
    return quantize_money(raw_bal)


async def generate_savings_dues_for_period(
    db: AsyncSession,
    shg_id: uuid.UUID,
    period: str,  # YYYY-MM
) -> list[SavingsDue]:
    """
    Generates a savings_dues record for each active member in the SHG for the specified period.
    Idempotent: skips members who already have a due for this period.
    """
    # 1. Fetch group settings for monthly saving amount
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == shg_id)
    settings_res = await db.execute(settings_stmt)
    settings = settings_res.scalar_one_or_none()

    monthly_amount = settings.monthly_saving_amount if settings else Decimal("200.00")

    # 2. Fetch all active members
    members_stmt = select(Member).where(
        Member.shg_id == shg_id,
        Member.status == MemberStatus.ACTIVE,
        Member.deleted_at.is_(None),
    )
    members_res = await db.execute(members_stmt)
    active_members = members_res.scalars().all()

    # 3. Fetch existing dues for this period
    existing_stmt = select(SavingsDue.member_id).where(
        SavingsDue.shg_id == shg_id,
        SavingsDue.period == period,
    )
    existing_res = await db.execute(existing_stmt)
    existing_member_ids = set(existing_res.scalars().all())

    created_dues: list[SavingsDue] = []
    for m in active_members:
        if m.id not in existing_member_ids:
            due = SavingsDue(
                shg_id=shg_id,
                member_id=m.id,
                period=period,
                amount_due=monthly_amount,
                amount_paid=Decimal("0.00"),
                status=SavingsDueStatus.PENDING,
            )
            db.add(due)
            created_dues.append(due)

    await db.flush()
    return created_dues


def calculate_late_fine(
    period: str,
    as_of_date: date,
    late_fine_per_day: Decimal,
    fine_grace_days: int = 5,
    max_fine_cap: Decimal = Decimal("200.00"),
) -> Decimal:
    """
    Late fine = late_fine_per_day * max(0, days_late - fine_grace_days), capped by max_fine_cap.
    Period YYYY-MM assumes due on 1st of that month.
    """
    try:
        year, month = map(int, period.split("-"))
        due_date = date(year, month, 1)
    except Exception:
        due_date = as_of_date

    days_passed = (as_of_date - due_date).days
    overdue_days = max(0, days_passed - fine_grace_days)
    if overdue_days <= 0:
        return Decimal("0.00")

    fine = quantize_money(overdue_days * late_fine_per_day)
    return min(fine, max_fine_cap)


async def collect_member_savings(
    db: AsyncSession,
    shg_id: uuid.UUID,
    member_id: uuid.UUID,
    amount: Decimal,
    period: str,
    posted_by: uuid.UUID,
    fine_amount: Decimal = Decimal("0.00"),
    entry_date: date | None = None,
    idempotency_key: str | None = None,
) -> tuple[SavingsDue, Decimal]:
    """
    Records collection of savings (+ optional fine) for a member.
    Posts double-entry:
    - Debit Cash (1000) for total collected (amount + fine)
    - Credit Member Savings (2000-{member}) for amount
    - Credit Fine & Penalty Income (4010) for fine_amount (if fine > 0)
    Updates savings_dues status.
    """
    amount = quantize_money(amount)
    fine_amount = quantize_money(fine_amount)
    coll_date = entry_date or date.today()

    if amount <= Decimal("0.00"):
        raise AppError(
            code="INVALID_AMOUNT",
            message="Savings collection amount must be strictly positive.",
            status_code=400,
        )

    # 1. Fetch member
    member_stmt = select(Member).where(
        Member.id == member_id,
        Member.shg_id == shg_id,
        Member.deleted_at.is_(None),
    )
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()
    if not member:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found or inaccessible.",
            status_code=404,
        )

    # 2. Get accounts: Cash in Hand (1000), Member Savings (2000-sub), Fine Income (4010)
    cash_account = await get_account_by_code(db, shg_id, "1000")
    member_savings_acc, _ = await get_or_create_member_sub_accounts(db, shg_id, member)

    total_cash_in = amount + fine_amount

    posting_lines = [
        PostingLineDTO(account_id=cash_account.id, debit=total_cash_in, credit=Decimal("0.00")),
        PostingLineDTO(account_id=member_savings_acc.id, debit=Decimal("0.00"), credit=amount),
    ]

    if fine_amount > Decimal("0.00"):
        fine_account = await get_account_by_code(db, shg_id, "4010")
        posting_lines.append(PostingLineDTO(account_id=fine_account.id, debit=Decimal("0.00"), credit=fine_amount))

    # 3. Post double-entry journal entry
    desc = f"Monthly savings collection ({period}) for {member.full_name}"
    if fine_amount > Decimal("0.00"):
        desc += f" (including fine of ₹{fine_amount})"

    await post_journal_entry(
        db=db,
        shg_id=shg_id,
        entry_date=coll_date,
        description=desc,
        source_type=JournalSourceType.SAVINGS,
        lines=posting_lines,
        posted_by=posted_by,
        source_id=member.id,
        idempotency_key=idempotency_key,
    )

    # 4. Update savings_dues record
    due_stmt = select(SavingsDue).where(
        SavingsDue.member_id == member_id,
        SavingsDue.period == period,
    )
    due_res = await db.execute(due_stmt)
    due = due_res.scalar_one_or_none()

    if not due:
        due = SavingsDue(
            shg_id=shg_id,
            member_id=member_id,
            period=period,
            amount_due=amount,
            amount_paid=amount,
            status=SavingsDueStatus.PAID,
        )
        db.add(due)
    else:
        due.amount_paid = quantize_money(due.amount_paid + amount)
        if due.amount_paid >= due.amount_due:
            due.status = SavingsDueStatus.PAID
        else:
            due.status = SavingsDueStatus.PARTIAL

    await db.flush()

    # 5. Return updated due and new total savings balance
    new_balance = await get_member_savings_balance(db, shg_id, member_id)
    return due, new_balance


async def withdraw_member_savings(
    db: AsyncSession,
    shg_id: uuid.UUID,
    member_id: uuid.UUID,
    amount: Decimal,
    posted_by: uuid.UUID,
    reason: str,
    entry_date: date | None = None,
    idempotency_key: str | None = None,
) -> Decimal:
    """
    Processes a savings withdrawal (e.g. upon member exit).
    Verifies that member has sufficient savings balance.
    Posts double-entry:
    - Debit Member Savings (2000-{member})
    - Credit Cash in Hand (1000)
    """
    amount = quantize_money(amount)
    w_date = entry_date or date.today()

    if amount <= Decimal("0.00"):
        raise AppError(
            code="INVALID_AMOUNT",
            message="Withdrawal amount must be strictly positive.",
            status_code=400,
        )

    # 1. Fetch member
    member_stmt = select(Member).where(
        Member.id == member_id,
        Member.shg_id == shg_id,
        Member.deleted_at.is_(None),
    )
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()
    if not member:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found or inaccessible.",
            status_code=404,
        )

    # 2. Check sufficient savings balance
    current_balance = await get_member_savings_balance(db, shg_id, member_id)
    if amount > current_balance:
        raise AppError(
            code="INSUFFICIENT_SAVINGS_BALANCE",
            message=f"Withdrawal amount ₹{amount} exceeds member's available savings balance ₹{current_balance}.",
            status_code=400,
            details={"requested_amount": str(amount), "current_balance": str(current_balance)},
        )

    # 3. Accounts: Cash in Hand (1000) & Member Savings (2000-sub)
    cash_account = await get_account_by_code(db, shg_id, "1000")
    member_savings_acc, _ = await get_or_create_member_sub_accounts(db, shg_id, member)

    posting_lines = [
        PostingLineDTO(account_id=member_savings_acc.id, debit=amount, credit=Decimal("0.00")),
        PostingLineDTO(account_id=cash_account.id, debit=Decimal("0.00"), credit=amount),
    ]

    desc = f"Savings withdrawal for {member.full_name}: {reason}"
    await post_journal_entry(
        db=db,
        shg_id=shg_id,
        entry_date=w_date,
        description=desc,
        source_type=JournalSourceType.SAVINGS,
        lines=posting_lines,
        posted_by=posted_by,
        source_id=member.id,
        idempotency_key=idempotency_key,
    )

    new_balance = await get_member_savings_balance(db, shg_id, member_id)
    return new_balance
