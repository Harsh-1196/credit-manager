import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.errors import AppError
from app.db.base import TimestampedUUIDModel


class AccountType(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class JournalSourceType(str, enum.Enum):
    SAVINGS = "SAVINGS"
    DISBURSAL = "DISBURSAL"
    REPAYMENT = "REPAYMENT"
    FINE = "FINE"
    FEE = "FEE"
    REVERSAL = "REVERSAL"
    ADJUSTMENT = "ADJUSTMENT"


class Account(TimestampedUUIDModel):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("shg_id", "code", name="uq_accounts_shg_id_code"),)

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False, index=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    lines: Mapped[list["JournalLine"]] = relationship("JournalLine", back_populates="account")


class JournalEntry(TimestampedUUIDModel):
    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("shg_id", "idempotency_key", name="uq_journal_entries_shg_idempotency_key"),)

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[JournalSourceType] = mapped_column(
        Enum(JournalSourceType),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,  # Ensures a reversed entry can only be reversed once (SPEC 4.5)
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="JournalLine.created_at",
    )


class JournalLine(TimestampedUUIDModel):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint(
            "((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))",
            name="chk_journal_line_debit_xor_credit",
        ),
        CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name="chk_journal_line_non_negative",
        ),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    debit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    credit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["Account"] = relationship("Account", back_populates="lines", lazy="selectin")


# --- Database-level Append-Only Invariants via SQLAlchemy Event Listeners ---
@event.listens_for(JournalEntry, "before_update")
def receive_before_update_journal_entry(mapper: object, connection: object, target: JournalEntry) -> None:
    raise AppError(
        code="LEDGER_IMMUTABLE",
        message="Journal entries are append-only. UPDATE operations are prohibited.",
        status_code=400,
    )


@event.listens_for(JournalEntry, "before_delete")
def receive_before_delete_journal_entry(mapper: object, connection: object, target: JournalEntry) -> None:
    raise AppError(
        code="LEDGER_IMMUTABLE",
        message="Journal entries are append-only. DELETE operations are prohibited.",
        status_code=400,
    )


@event.listens_for(JournalLine, "before_update")
def receive_before_update_journal_line(mapper: object, connection: object, target: JournalLine) -> None:
    raise AppError(
        code="LEDGER_IMMUTABLE",
        message="Journal lines are append-only. UPDATE operations are prohibited.",
        status_code=400,
    )


@event.listens_for(JournalLine, "before_delete")
def receive_before_delete_journal_line(mapper: object, connection: object, target: JournalLine) -> None:
    raise AppError(
        code="LEDGER_IMMUTABLE",
        message="Journal lines are append-only. DELETE operations are prohibited.",
        status_code=400,
    )
