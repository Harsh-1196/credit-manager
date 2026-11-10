import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedUUIDModel


class SavingsDueStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class SavingsDue(TimestampedUUIDModel):
    __tablename__ = "savings_dues"
    __table_args__ = (UniqueConstraint("member_id", "period", name="uq_savings_dues_member_period"),)

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM
    amount_due: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    status: Mapped[SavingsDueStatus] = mapped_column(
        Enum(SavingsDueStatus),
        default=SavingsDueStatus.PENDING,
        nullable=False,
        index=True,
    )

    member = relationship("Member", lazy="selectin")
