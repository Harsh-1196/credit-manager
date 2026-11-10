import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user, require_group_access, require_role
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.money import money_to_str, quantize_money
from app.db.models.auth import User, UserRole
from app.db.models.ledger import Account, AccountType, JournalEntry, JournalLine, JournalSourceType
from app.db.models.shg import Member
from app.db.session import get_db
from app.domain.ledger.accounts import get_or_create_member_sub_accounts
from app.domain.ledger.posting import reverse_journal_entry
from app.domain.savings.service import get_member_savings_balance
from app.schemas.ledger import (
    JournalEntryResponse,
    JournalEntryReverseRequest,
    JournalLineResponse,
    LedgerReportResponse,
    MemberPassbookResponse,
    PassbookEntryResponse,
    TrialBalanceItem,
)

router = APIRouter(tags=["ledger"])


@router.get("/groups/{id}/ledger", response_model=LedgerReportResponse)
async def get_group_ledger(
    id: uuid.UUID,
    group_scope: Annotated[tuple[User, uuid.UUID], Depends(require_group_access("id"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    account_id: uuid.UUID | None = Query(default=None),
) -> LedgerReportResponse:
    """
    Returns the group ledger entries, trial balance summary, and verification that sum(debits) == sum(credits).
    """
    current_user, shg_id = group_scope

    # 1. Fetch entries with lines and accounts
    entry_stmt = (
        select(JournalEntry)
        .options(
            selectinload(JournalEntry.lines).selectinload(JournalLine.account),
        )
        .where(JournalEntry.shg_id == shg_id)
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.created_at.asc())
    )

    if from_date:
        entry_stmt = entry_stmt.where(JournalEntry.entry_date >= from_date)
    if to_date:
        entry_stmt = entry_stmt.where(JournalEntry.entry_date <= to_date)

    res = await db.execute(entry_stmt)
    entries = res.scalars().all()

    # If filtered by account_id, filter entries that touch this account
    if account_id:
        entries = [e for e in entries if any(line.account_id == account_id for line in e.lines)]

    # 2. Compute trial balance across all accounts of this group
    acc_stmt = select(Account).where(Account.shg_id == shg_id, Account.is_active.is_(True)).order_by(Account.code.asc())
    acc_res = await db.execute(acc_stmt)
    accounts = acc_res.scalars().all()

    account_totals: dict[uuid.UUID, dict[str, Decimal]] = {
        acc.id: {"debit": Decimal("0.00"), "credit": Decimal("0.00")} for acc in accounts
    }

    total_group_debits = Decimal("0.00")
    total_group_credits = Decimal("0.00")

    entry_responses: list[JournalEntryResponse] = []
    for e in entries:
        line_responses: list[JournalLineResponse] = []
        for line in e.lines:
            d = quantize_money(line.debit)
            c = quantize_money(line.credit)
            total_group_debits += d
            total_group_credits += c

            if line.account_id in account_totals:
                account_totals[line.account_id]["debit"] += d
                account_totals[line.account_id]["credit"] += c

            acc_code = line.account.code if line.account else "UNKNOWN"
            acc_name = line.account.name if line.account else "Unknown Account"

            line_responses.append(
                JournalLineResponse(
                    id=line.id,
                    account_id=line.account_id,
                    account_code=acc_code,
                    account_name=acc_name,
                    debit=money_to_str(d),
                    credit=money_to_str(c),
                )
            )

        entry_responses.append(
            JournalEntryResponse(
                id=e.id,
                shg_id=e.shg_id,
                entry_date=e.entry_date,
                description=e.description,
                source_type=e.source_type,
                source_id=e.source_id,
                reverses_entry_id=e.reverses_entry_id,
                idempotency_key=e.idempotency_key,
                posted_by=e.posted_by,
                posted_at=e.posted_at,
                lines=line_responses,
            )
        )

    trial_balance_items: list[TrialBalanceItem] = []
    for acc in accounts:
        t = account_totals[acc.id]
        d = quantize_money(t["debit"])
        c = quantize_money(t["credit"])
        # Net balance convention: Assets/Expenses normal debit (debit - credit); Liabilities/Equity/Income normal credit (credit - debit)
        if acc.type in {AccountType.ASSET, AccountType.EXPENSE}:
            net = d - c
        else:
            net = c - d

        trial_balance_items.append(
            TrialBalanceItem(
                account_id=acc.id,
                account_code=acc.code,
                account_name=acc.name,
                account_type=acc.type.value,
                total_debit=money_to_str(d),
                total_credit=money_to_str(c),
                net_balance=money_to_str(net),
            )
        )

    return LedgerReportResponse(
        shg_id=shg_id,
        total_debits=money_to_str(total_group_debits),
        total_credits=money_to_str(total_group_credits),
        is_balanced=(total_group_debits == total_group_credits),
        trial_balance=trial_balance_items,
        entries=entry_responses,
    )


@router.get("/members/{id}/passbook", response_model=MemberPassbookResponse)
async def get_member_passbook(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> MemberPassbookResponse:
    """
    Returns the per-member savings passbook with running balance.
    Columns: Date, Particulars, Debit, Credit, Balance (SPEC 12.4, 12.5 Screen 5).
    """
    member_stmt = select(Member).where(Member.id == id, Member.deleted_at.is_(None))
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()

    if not member:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    has_access = await check_user_has_group_access(current_user, member.shg_id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Ensure member sub-accounts exist
    savings_acc, _ = await get_or_create_member_sub_accounts(db, member.shg_id, member)

    # Query all journal lines for this member's savings account in chronological order
    lines_stmt = (
        select(JournalLine)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .options(selectinload(JournalLine.entry))
        .where(JournalLine.account_id == savings_acc.id)
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.created_at.asc(), JournalLine.created_at.asc())
    )
    res = await db.execute(lines_stmt)
    all_lines = res.scalars().all()

    running_balance = Decimal("0.00")
    passbook_entries: list[PassbookEntryResponse] = []

    for line in all_lines:
        debit_amt = quantize_money(line.debit)
        credit_amt = quantize_money(line.credit)

        # For Member Savings (LIABILITY): Credit increases balance, Debit decreases balance
        running_balance = quantize_money(running_balance + credit_amt - debit_amt)

        entry_date = line.entry.entry_date
        # Check date filter
        if from_date and entry_date < from_date:
            continue
        if to_date and entry_date > to_date:
            continue

        is_reversal = line.entry.source_type == JournalSourceType.REVERSAL

        passbook_entries.append(
            PassbookEntryResponse(
                id=line.id,
                entry_id=line.entry.id,
                entry_date=entry_date,
                particulars=line.entry.description,
                debit=money_to_str(debit_amt) if debit_amt > Decimal("0.00") else "",
                credit=money_to_str(credit_amt) if credit_amt > Decimal("0.00") else "",
                balance=money_to_str(running_balance),
                is_reversal=is_reversal,
                reverses_entry_id=line.entry.reverses_entry_id,
            )
        )

    current_balance = await get_member_savings_balance(db, member.shg_id, member.id)

    return MemberPassbookResponse(
        member_id=member.id,
        member_name=member.full_name,
        shg_id=member.shg_id,
        total_savings_balance=money_to_str(current_balance),
        entries=passbook_entries,
    )


@router.post("/ledger/entries/{id}/reverse", response_model=JournalEntryResponse)
async def reverse_entry_endpoint(
    id: uuid.UUID,
    payload: JournalEntryReverseRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> JournalEntryResponse:
    """
    ADMIN only: reverses a journal entry with an audit reason.
    Posts an exact mirror entry (swapping debits and credits) and links reverses_entry_id.
    """
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        .where(JournalEntry.id == id)
    )
    res = await db.execute(stmt)
    entry = res.scalar_one_or_none()

    if not entry:
        raise AppError(
            code="NOT_FOUND",
            message="Journal entry not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    reversal_entry = await reverse_journal_entry(
        db=db,
        shg_id=entry.shg_id,
        entry_id=entry.id,
        posted_by=current_user.id,
        reason=payload.reason,
    )
    await db.commit()

    # Re-fetch reversal entry with eager lines
    ref_stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        .where(JournalEntry.id == reversal_entry.id)
    )
    ref_res = await db.execute(ref_stmt)
    full_reversal = ref_res.scalar_one()

    await record_audit_log(
        db=db,
        action="JOURNAL_ENTRY_REVERSED",
        entity_type="journal_entries",
        entity_id=entry.id,
        before={"entry_id": str(entry.id), "description": entry.description},
        after={"reversal_entry_id": str(full_reversal.id), "reason": payload.reason},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    line_resps = [
        JournalLineResponse(
            id=line.id,
            account_id=line.account_id,
            account_code=line.account.code if line.account else "UNKNOWN",
            account_name=line.account.name if line.account else "Unknown",
            debit=money_to_str(line.debit),
            credit=money_to_str(line.credit),
        )
        for line in full_reversal.lines
    ]

    return JournalEntryResponse(
        id=full_reversal.id,
        shg_id=full_reversal.shg_id,
        entry_date=full_reversal.entry_date,
        description=full_reversal.description,
        source_type=full_reversal.source_type,
        source_id=full_reversal.source_id,
        reverses_entry_id=full_reversal.reverses_entry_id,
        idempotency_key=full_reversal.idempotency_key,
        posted_by=full_reversal.posted_by,
        posted_at=full_reversal.posted_at,
        lines=line_resps,
    )
