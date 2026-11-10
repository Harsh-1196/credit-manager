import uuid
from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models.auth import User, UserRole
from app.db.models.ledger import Account, AccountType, JournalEntry, JournalLine, JournalSourceType
from app.db.models.shg import SHG, SHGStatus


def create_sync_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


# Strategy for generating an action:
# 1 = savings deposit
# 2 = savings withdrawal
# 3 = fine collection
# 4 = reversal of a previous entry
action_strategy = st.lists(
    st.tuples(
        st.sampled_from(["SAVINGS", "WITHDRAWAL", "FINE", "REVERSAL"]),
        st.decimals(min_value=Decimal("10.00"), max_value=Decimal("5000.00"), places=2),
    ),
    min_size=3,
    max_size=20,
)


@settings(max_examples=25, deadline=None)
@given(actions=action_strategy)
def test_hypothesis_trial_balance_always_zero(actions: list[tuple[str, Decimal]]) -> None:
    """
    Hypothesis property test:
    After random sequences of savings, withdrawals, fines and reversals,
    every entry balances and the trial balance sums to zero: sum(debit) == sum(credit).
    """
    session_maker = create_sync_test_db()
    with session_maker() as db:
        shg = SHG(
            name="Hypothesis SHG",
            village="Village",
            district="District",
            formation_date=date(2025, 1, 1),
            meeting_day="Monday",
            meeting_frequency="MONTHLY",
            status=SHGStatus.ACTIVE,
        )
        db.add(shg)
        db.flush()

        admin = User(
            email=f"admin_{uuid.uuid4().hex[:6]}@shg.org",
            phone="9876543210",
            password_hash="dummy",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.flush()

        # Create basic accounts
        cash_acc = Account(shg_id=shg.id, code="1000", name="Cash in Hand", type=AccountType.ASSET)
        bank_acc = Account(shg_id=shg.id, code="1010", name="Bank Account", type=AccountType.ASSET)
        savings_acc = Account(shg_id=shg.id, code="2000-001", name="Member Savings", type=AccountType.LIABILITY)
        fine_acc = Account(shg_id=shg.id, code="4010", name="Fines and Penalties", type=AccountType.INCOME)
        db.add_all([cash_acc, bank_acc, savings_acc, fine_acc])
        db.flush()

        posted_entries: list[JournalEntry] = []
        reversed_ids: set[uuid.UUID] = set()
        member_balance = Decimal("0.00")

        for idx, (action_type, amount) in enumerate(actions):
            if action_type == "SAVINGS":
                # Debit Cash (Asset +), Credit Member Savings (Liability +)
                entry = JournalEntry(
                    shg_id=shg.id,
                    entry_date=date(2025, 2, 1),
                    description=f"Savings deposit #{idx}",
                    source_type=JournalSourceType.SAVINGS,
                    posted_by=admin.id,
                )
                db.add(entry)
                db.flush()
                l1 = JournalLine(entry_id=entry.id, account_id=cash_acc.id, debit=amount, credit=Decimal("0.00"))
                l2 = JournalLine(entry_id=entry.id, account_id=savings_acc.id, debit=Decimal("0.00"), credit=amount)
                db.add_all([l1, l2])
                db.flush()
                member_balance += amount
                posted_entries.append(entry)

            elif action_type == "WITHDRAWAL":
                # Allowed only if member has sufficient savings
                if member_balance >= amount:
                    # Debit Member Savings (Liability -), Credit Cash (Asset -)
                    entry = JournalEntry(
                        shg_id=shg.id,
                        entry_date=date(2025, 2, 1),
                        description=f"Savings withdrawal #{idx}",
                        source_type=JournalSourceType.SAVINGS,
                        posted_by=admin.id,
                    )
                    db.add(entry)
                    db.flush()
                    l1 = JournalLine(entry_id=entry.id, account_id=savings_acc.id, debit=amount, credit=Decimal("0.00"))
                    l2 = JournalLine(entry_id=entry.id, account_id=cash_acc.id, debit=Decimal("0.00"), credit=amount)
                    db.add_all([l1, l2])
                    db.flush()
                    member_balance -= amount
                    posted_entries.append(entry)

            elif action_type == "FINE":
                # Debit Cash (Asset +), Credit Fine Income (Income +)
                entry = JournalEntry(
                    shg_id=shg.id,
                    entry_date=date(2025, 2, 1),
                    description=f"Fine collection #{idx}",
                    source_type=JournalSourceType.FINE,
                    posted_by=admin.id,
                )
                db.add(entry)
                db.flush()
                l1 = JournalLine(entry_id=entry.id, account_id=cash_acc.id, debit=amount, credit=Decimal("0.00"))
                l2 = JournalLine(entry_id=entry.id, account_id=fine_acc.id, debit=Decimal("0.00"), credit=amount)
                db.add_all([l1, l2])
                db.flush()
                posted_entries.append(entry)

            elif action_type == "REVERSAL":
                eligible = [
                    e
                    for e in posted_entries
                    if e.source_type != JournalSourceType.REVERSAL and e.id not in reversed_ids
                ]
                if eligible:
                    target = eligible[0]
                    t_lines = db.execute(select(JournalLine).where(JournalLine.entry_id == target.id)).scalars().all()
                    rev_entry = JournalEntry(
                        shg_id=shg.id,
                        entry_date=date(2025, 2, 2),
                        description=f"Reversal of #{target.id}",
                        source_type=JournalSourceType.REVERSAL,
                        reverses_entry_id=target.id,
                        posted_by=admin.id,
                    )
                    db.add(rev_entry)
                    db.flush()
                    for target_line in t_lines:
                        db.add(
                            JournalLine(
                                entry_id=rev_entry.id,
                                account_id=target_line.account_id,
                                debit=target_line.credit,
                                credit=target_line.debit,
                            )
                        )
                    db.flush()
                    reversed_ids.add(target.id)
                    posted_entries.append(rev_entry)

        # 1. Every entry balances individually: sum(debit) == sum(credit)
        all_entries = db.execute(select(JournalEntry).where(JournalEntry.shg_id == shg.id)).scalars().all()
        for e in all_entries:
            lines = db.execute(select(JournalLine).where(JournalLine.entry_id == e.id)).scalars().all()
            assert sum(line.debit for line in lines) == sum(line.credit for line in lines)

        # 2. Entire ledger trial balance sums to zero: total debits == total credits
        all_lines = (
            db.execute(
                select(JournalLine)
                .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
                .where(JournalEntry.shg_id == shg.id)
            )
            .scalars()
            .all()
        )
        total_ledger_debits = sum(line.debit for line in all_lines)
        total_ledger_credits = sum(line.credit for line in all_lines)

        assert total_ledger_debits == total_ledger_credits
