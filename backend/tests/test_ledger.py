from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.ledger import JournalEntry, JournalLine, JournalSourceType
from app.db.models.shg import SHG
from app.domain.ledger.accounts import get_account_by_code
from app.domain.ledger.posting import PostingLineDTO, post_journal_entry, reverse_journal_entry


@pytest.mark.asyncio
async def test_post_balanced_journal_entry(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    assert cash_acc is not None
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert bank_acc is not None

    entry = await post_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_date=date(2025, 2, 1),
        description="Transfer cash to bank",
        source_type=JournalSourceType.ADJUSTMENT,
        posted_by=admin_user.id,
        lines=[
            PostingLineDTO(account_id=bank_acc.id, debit=Decimal("500.00"), credit=Decimal("0.00")),
            PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("500.00")),
        ],
    )
    assert entry.id is not None
    assert len(entry.lines) == 2

    # Verify lines in DB
    stmt = select(JournalLine).where(JournalLine.entry_id == entry.id)
    res = await db_session.execute(stmt)
    lines = res.scalars().all()
    assert len(lines) == 2
    assert sum(line.debit for line in lines) == sum(line.credit for line in lines) == Decimal("500.00")


@pytest.mark.asyncio
async def test_post_unbalanced_journal_entry_fails(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert cash_acc is not None and bank_acc is not None

    with pytest.raises(AppError) as exc_info:
        await post_journal_entry(
            db=db_session,
            shg_id=test_group.id,
            entry_date=date(2025, 2, 1),
            description="Unbalanced entry",
            source_type=JournalSourceType.ADJUSTMENT,
            posted_by=admin_user.id,
            lines=[
                PostingLineDTO(account_id=bank_acc.id, debit=Decimal("500.00"), credit=Decimal("0.00")),
                PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("400.00")),
            ],
        )
    assert exc_info.value.code == "LEDGER_UNBALANCED_ENTRY"


@pytest.mark.asyncio
async def test_post_entry_both_debit_and_credit_fails(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert cash_acc is not None and bank_acc is not None

    with pytest.raises(AppError) as exc_info:
        await post_journal_entry(
            db=db_session,
            shg_id=test_group.id,
            entry_date=date(2025, 2, 1),
            description="Both debit and credit on single line",
            source_type=JournalSourceType.ADJUSTMENT,
            posted_by=admin_user.id,
            lines=[
                PostingLineDTO(account_id=bank_acc.id, debit=Decimal("100.00"), credit=Decimal("50.00")),
                PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("50.00")),
            ],
        )
    assert exc_info.value.code == "LEDGER_INVALID_LINE_SIDE"


@pytest.mark.asyncio
async def test_reversal_restores_balances_and_prevents_double_reversal(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert cash_acc is not None and bank_acc is not None

    orig_entry = await post_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_date=date(2025, 2, 1),
        description="Original transfer",
        source_type=JournalSourceType.ADJUSTMENT,
        posted_by=admin_user.id,
        lines=[
            PostingLineDTO(account_id=bank_acc.id, debit=Decimal("250.00"), credit=Decimal("0.00")),
            PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("250.00")),
        ],
    )

    reversal_entry = await reverse_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_id=orig_entry.id,
        posted_by=admin_user.id,
        reason="Wrong account credited",
        entry_date=date(2025, 2, 2),
    )

    assert reversal_entry.reverses_entry_id == orig_entry.id
    assert reversal_entry.source_type == JournalSourceType.REVERSAL
    assert "Reversal of entry" in reversal_entry.description
    assert "Wrong account credited" in reversal_entry.description

    # Lines should be mirrored
    rev_lines = reversal_entry.lines
    assert len(rev_lines) == 2
    for line in rev_lines:
        if line.account_id == bank_acc.id:
            assert line.credit == Decimal("250.00")
            assert line.debit == Decimal("0.00")
        elif line.account_id == cash_acc.id:
            assert line.debit == Decimal("250.00")
            assert line.credit == Decimal("0.00")

    # Double reversal must fail
    with pytest.raises(AppError) as exc_info:
        await reverse_journal_entry(
            db=db_session,
            shg_id=test_group.id,
            entry_id=orig_entry.id,
            posted_by=admin_user.id,
            reason="Attempt second reversal",
            entry_date=date(2025, 2, 3),
        )
    assert exc_info.value.code == "ENTRY_ALREADY_REVERSED"

    # Reversing a reversal must fail
    with pytest.raises(AppError) as exc_rev:
        await reverse_journal_entry(
            db=db_session,
            shg_id=test_group.id,
            entry_id=reversal_entry.id,
            posted_by=admin_user.id,
            reason="Attempt to reverse a reversal",
            entry_date=date(2025, 2, 4),
        )
    assert exc_rev.value.code == "CANNOT_REVERSE_REVERSAL"


@pytest.mark.asyncio
async def test_ledger_append_only_update_prohibited(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert cash_acc is not None and bank_acc is not None

    entry = await post_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_date=date(2025, 2, 1),
        description="Immutable entry",
        source_type=JournalSourceType.ADJUSTMENT,
        posted_by=admin_user.id,
        lines=[
            PostingLineDTO(account_id=bank_acc.id, debit=Decimal("100.00"), credit=Decimal("0.00")),
            PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("100.00")),
        ],
    )

    with pytest.raises(AppError) as exc_up:
        entry.description = "Tampered description"
        await db_session.flush()
    assert exc_up.value.code == "LEDGER_IMMUTABLE"


@pytest.mark.asyncio
async def test_ledger_append_only_delete_prohibited(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert cash_acc is not None and bank_acc is not None

    entry = await post_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_date=date(2025, 2, 1),
        description="Immutable entry",
        source_type=JournalSourceType.ADJUSTMENT,
        posted_by=admin_user.id,
        lines=[
            PostingLineDTO(account_id=bank_acc.id, debit=Decimal("100.00"), credit=Decimal("0.00")),
            PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("100.00")),
        ],
    )

    with pytest.raises(AppError) as exc_del:
        await db_session.delete(entry)
        await db_session.flush()
    assert exc_del.value.code == "LEDGER_IMMUTABLE"


@pytest.mark.asyncio
async def test_hypothesis_ledger_balancing_property(
    db_session: AsyncSession,
    test_group: SHG,
    admin_user: User,
) -> None:
    cash_acc = await get_account_by_code(db_session, test_group.id, "1000")
    bank_acc = await get_account_by_code(db_session, test_group.id, "1010")
    assert cash_acc is not None and bank_acc is not None

    posted_entries: list[JournalEntry] = []

    amounts = [Decimal("100.00"), Decimal("250.50"), Decimal("10.00"), Decimal("999.99"), Decimal("45.00")]

    for i, amt in enumerate(amounts):
        entry = await post_journal_entry(
            db=db_session,
            shg_id=test_group.id,
            entry_date=date(2025, 2, 1 + i),
            description=f"Transaction {i}",
            source_type=JournalSourceType.ADJUSTMENT,
            posted_by=admin_user.id,
            lines=[
                PostingLineDTO(account_id=bank_acc.id, debit=amt, credit=Decimal("0.00")),
                PostingLineDTO(account_id=cash_acc.id, debit=Decimal("0.00"), credit=amt),
            ],
        )
        posted_entries.append(entry)

    # Reverse 2 of the entries
    await reverse_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_id=posted_entries[0].id,
        posted_by=admin_user.id,
        reason="Test reversal 1",
        entry_date=date(2025, 2, 10),
    )
    await reverse_journal_entry(
        db=db_session,
        shg_id=test_group.id,
        entry_id=posted_entries[2].id,
        posted_by=admin_user.id,
        reason="Test reversal 2",
        entry_date=date(2025, 2, 11),
    )

    # Verify ledger consistency
    stmt = (
        select(JournalLine)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(JournalEntry.shg_id == test_group.id)
    )
    res = await db_session.execute(stmt)
    all_lines = res.scalars().all()

    total_debit = sum(line.debit for line in all_lines)
    total_credit = sum(line.credit for line in all_lines)

    assert total_debit == total_credit
    assert total_debit > Decimal("0.00")
