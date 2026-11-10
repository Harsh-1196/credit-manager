import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.money import quantize_money
from app.db.models.ledger import Account, JournalEntry, JournalLine, JournalSourceType


@dataclass
class PostingLineDTO:
    account_id: uuid.UUID
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        self.debit = quantize_money(self.debit)
        self.credit = quantize_money(self.credit)


async def post_journal_entry(
    db: AsyncSession,
    shg_id: uuid.UUID,
    entry_date: date,
    description: str,
    source_type: JournalSourceType,
    lines: list[PostingLineDTO],
    posted_by: uuid.UUID,
    source_id: uuid.UUID | None = None,
    reverses_entry_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> JournalEntry:
    """
    Atomically validates and posts a balanced double-entry journal entry with lines.
    Enforces non-negotiable accounting rules:
    - sum(debit) == sum(credit) > 0
    - Exactly one of debit/credit is non-zero per line
    - All accounts belong to the group
    - An entry can only be reversed once
    """
    if not lines or len(lines) < 2:
        raise AppError(
            code="LEDGER_INVALID_LINES",
            message="Journal entry must contain at least two lines.",
            status_code=400,
        )

    # 1. Check idempotency key if provided
    if idempotency_key:
        stmt = select(JournalEntry).where(
            JournalEntry.shg_id == shg_id,
            JournalEntry.idempotency_key == idempotency_key,
        )
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

    # 2. Validate line balances and constraints
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    account_ids: set[uuid.UUID] = set()

    for idx, line in enumerate(lines):
        line.debit = quantize_money(line.debit)
        line.credit = quantize_money(line.credit)

        if line.debit < 0 or line.credit < 0:
            raise AppError(
                code="LEDGER_NEGATIVE_AMOUNT",
                message=f"Line {idx + 1} has negative amount.",
                status_code=400,
            )

        has_debit = line.debit > Decimal("0.00")
        has_credit = line.credit > Decimal("0.00")

        # Invariant: exactly one of debit or credit is non-zero
        if not (has_debit ^ has_credit):
            raise AppError(
                code="LEDGER_INVALID_LINE_SIDE",
                message=f"Line {idx + 1} must have exactly one non-zero side (debit XOR credit).",
                status_code=400,
                details={"line_index": idx, "debit": str(line.debit), "credit": str(line.credit)},
            )

        total_debit += line.debit
        total_credit += line.credit
        account_ids.add(line.account_id)

    total_debit = quantize_money(total_debit)
    total_credit = quantize_money(total_credit)

    # Invariant: sum(debit) == sum(credit)
    if total_debit != total_credit:
        raise AppError(
            code="LEDGER_UNBALANCED_ENTRY",
            message=f"Journal entry is unbalanced: total debit ({total_debit}) != total credit ({total_credit}).",
            status_code=400,
            details={"total_debit": str(total_debit), "total_credit": str(total_credit)},
        )

    if total_debit <= Decimal("0.00"):
        raise AppError(
            code="LEDGER_ZERO_AMOUNT",
            message="Journal entry total must be strictly greater than zero.",
            status_code=400,
        )

    # 3. Validate accounts belong to the same SHG
    stmt_acc = select(Account).where(
        Account.id.in_(list(account_ids)),
        Account.shg_id == shg_id,
        Account.is_active.is_(True),
    )
    res_acc = await db.execute(stmt_acc)
    valid_accounts = res_acc.scalars().all()
    if len(valid_accounts) != len(account_ids):
        raise AppError(
            code="LEDGER_INVALID_ACCOUNT",
            message="One or more accounts do not exist or belong to a different group.",
            status_code=400,
            details={"expected_accounts": len(account_ids), "found_accounts": len(valid_accounts)},
        )

    # 4. If this is a reversal, validate target entry
    if reverses_entry_id:
        target_stmt = select(JournalEntry).where(
            JournalEntry.id == reverses_entry_id,
            JournalEntry.shg_id == shg_id,
        )
        target_res = await db.execute(target_stmt)
        target_entry = target_res.scalar_one_or_none()

        if not target_entry:
            raise AppError(
                code="ENTRY_NOT_FOUND",
                message="Target journal entry to reverse was not found.",
                status_code=404,
            )

        if target_entry.source_type == JournalSourceType.REVERSAL:
            raise AppError(
                code="CANNOT_REVERSE_REVERSAL",
                message="Cannot reverse an entry that is already a reversal.",
                status_code=400,
            )

        # SPEC 4.5 invariant: A reversed entry can only be reversed once
        rev_check_stmt = select(JournalEntry).where(
            JournalEntry.reverses_entry_id == reverses_entry_id,
        )
        rev_check_res = await db.execute(rev_check_stmt)
        already_reversed = rev_check_res.scalar_one_or_none()
        if already_reversed:
            raise AppError(
                code="ENTRY_ALREADY_REVERSED",
                message="This journal entry has already been reversed.",
                status_code=400,
                details={"original_entry_id": str(reverses_entry_id), "existing_reversal_id": str(already_reversed.id)},
            )

    # 5. Create entry and lines atomically
    entry = JournalEntry(
        shg_id=shg_id,
        entry_date=entry_date,
        description=description,
        source_type=source_type,
        source_id=source_id,
        reverses_entry_id=reverses_entry_id,
        idempotency_key=idempotency_key,
        posted_by=posted_by,
        posted_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.flush()

    for line in lines:
        j_line = JournalLine(
            entry_id=entry.id,
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
        )
        db.add(j_line)

    await db.flush()

    # Eagerly load lines for caller convenience
    stmt_reload = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(JournalEntry.id == entry.id)
    )
    res_reload = await db.execute(stmt_reload)
    return res_reload.scalar_one()


async def reverse_journal_entry(
    db: AsyncSession,
    shg_id: uuid.UUID,
    entry_id: uuid.UUID,
    posted_by: uuid.UUID,
    reason: str,
    entry_date: date | None = None,
) -> JournalEntry:
    """
    Creates a mirror reversal entry with swapped debits and credits.
    Enforces that an entry can only be reversed once.
    """
    if not reason or not reason.strip():
        raise AppError(
            code="REASON_REQUIRED",
            message="A descriptive reason is required to reverse a journal entry.",
            status_code=400,
        )

    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(JournalEntry.id == entry_id, JournalEntry.shg_id == shg_id)
    )
    res = await db.execute(stmt)
    original = res.scalar_one_or_none()

    if not original:
        raise AppError(
            code="ENTRY_NOT_FOUND",
            message="Journal entry not found or inaccessible.",
            status_code=404,
        )

    # Swap debits and credits for each line
    mirror_lines = [
        PostingLineDTO(
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
        )
        for line in original.lines
    ]

    reversal_date = entry_date or date.today()
    description = f"Reversal of entry {original.id}: {reason.strip()}"

    return await post_journal_entry(
        db=db,
        shg_id=shg_id,
        entry_date=reversal_date,
        description=description,
        source_type=JournalSourceType.REVERSAL,
        lines=mirror_lines,
        posted_by=posted_by,
        source_id=original.id,
        reverses_entry_id=original.id,
    )
