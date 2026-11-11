import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedUUIDModel
from app.db.models.shg import InterestType, Member


class LoanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISBURSED = "DISBURSED"
    ACTIVE = "ACTIVE"
    OVERDUE = "OVERDUE"
    CLOSED = "CLOSED"
    WRITTEN_OFF = "WRITTEN_OFF"


class LoanScheduleStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class Loan(TimestampedUUIDModel):
    __tablename__ = "loans"
    __table_args__ = (
        UniqueConstraint("shg_id", "loan_number", name="uq_loans_shg_id_loan_number"),
        CheckConstraint("principal > 0", name="chk_loan_principal_positive"),
        CheckConstraint("tenure_months >= 1", name="chk_loan_tenure_positive"),
        CheckConstraint("interest_rate >= 0", name="chk_loan_interest_non_negative"),
    )

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    loan_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    principal: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 3),
        nullable=False,
    )
    interest_type: Mapped[InterestType] = mapped_column(
        Enum(InterestType, name="loan_interest_type_enum", native_enum=False),
        default=InterestType.REDUCING,
        nullable=False,
    )
    tenure_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    processing_fee: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus, name="loan_status_enum", native_enum=False),
        default=LoanStatus.DRAFT,
        nullable=False,
        index=True,
    )
    applied_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    disbursed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disbursed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    first_due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    written_off_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    written_off_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    write_off_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    # Relationships
    member: Mapped["Member"] = relationship("Member", lazy="selectin")
    schedule: Mapped[list["LoanSchedule"]] = relationship(
        "LoanSchedule",
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="LoanSchedule.installment_no",
        lazy="selectin",
    )
    history: Mapped[list["LoanStatusHistory"]] = relationship(
        "LoanStatusHistory",
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="LoanStatusHistory.created_at",
        lazy="selectin",
    )


class LoanSchedule(TimestampedUUIDModel):
    __tablename__ = "loan_schedule"
    __table_args__ = (
        UniqueConstraint("loan_id", "installment_no", name="uq_loan_schedule_loan_inst"),
    )

    loan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installment_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    principal_due: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    interest_due: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    total_due: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    principal_paid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    interest_paid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    penalty_paid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    penalty_due: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    last_penalty_accrual_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[LoanScheduleStatus] = mapped_column(
        Enum(LoanScheduleStatus, name="loan_schedule_status_enum", native_enum=False),
        default=LoanScheduleStatus.PENDING,
        nullable=False,
        index=True,
    )

    loan: Mapped["Loan"] = relationship("Loan", back_populates="schedule")


class LoanStatusHistory(TimestampedUUIDModel):
    __tablename__ = "loan_status_history"

    loan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus, name="loan_status_enum", native_enum=False),
        nullable=False,
    )
    to_status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus, name="loan_status_enum", native_enum=False),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    loan: Mapped["Loan"] = relationship("Loan", back_populates="history")
