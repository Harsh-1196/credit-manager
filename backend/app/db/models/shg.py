from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedUUIDModel

if TYPE_CHECKING:
    from app.db.models.auth import User


class SHGStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CLOSED = "CLOSED"


class InterestType(enum.StrEnum):
    FLAT = "FLAT"
    REDUCING = "REDUCING"


class MemberStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"


class OfficeBearerRole(enum.StrEnum):
    PRESIDENT = "PRESIDENT"
    SECRETARY = "SECRETARY"
    TREASURER = "TREASURER"
    MEMBER = "MEMBER"


class SHG(TimestampedUUIDModel):
    __tablename__ = "shgs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    village: Mapped[str] = mapped_column(String(255), nullable=False)
    ward: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str] = mapped_column(String(255), nullable=False)
    formation_date: Mapped[date] = mapped_column(Date, nullable=False)
    meeting_day: Mapped[str] = mapped_column(String(50), nullable=False)
    meeting_frequency: Mapped[str] = mapped_column(String(50), default="MONTHLY", nullable=False)
    bank_account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[SHGStatus] = mapped_column(
        Enum(SHGStatus, name="shg_status_enum", native_enum=False),
        default=SHGStatus.ACTIVE,
        nullable=False,
    )

    settings: Mapped[GroupSettings] = relationship(
        "GroupSettings", back_populates="shg", uselist=False, cascade="all, delete-orphan"
    )
    members: Mapped[list[Member]] = relationship("Member", back_populates="shg", cascade="all, delete-orphan")


class GroupSettings(TimestampedUUIDModel):
    __tablename__ = "group_settings"

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    monthly_saving_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("200.00"), nullable=False)
    late_fine_per_day: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("5.00"), nullable=False)
    fine_grace_days: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    default_interest_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("12.000"), nullable=False)
    interest_type: Mapped[InterestType] = mapped_column(
        Enum(InterestType, name="interest_type_enum", native_enum=False),
        default=InterestType.REDUCING,
        nullable=False,
    )
    max_loan_multiple: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("3.00"), nullable=False)
    min_tenure_months: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_tenure_months: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    processing_fee_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("1.000"), nullable=False)
    penalty_interest_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("2.000"), nullable=False)
    prepayment_policy: Mapped[str] = mapped_column(String(50), default="REDUCE_TENURE", nullable=False)

    shg: Mapped[SHG] = relationship("SHG", back_populates="settings")


class Member(TimestampedUUIDModel):
    __tablename__ = "members"

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    id_proof_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_proof_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    joined_on: Mapped[date] = mapped_column(Date, nullable=False)
    exited_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MemberStatus] = mapped_column(
        Enum(MemberStatus, name="member_status_enum", native_enum=False),
        default=MemberStatus.ACTIVE,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    shg: Mapped[SHG] = relationship("SHG", back_populates="members")
    user: Mapped[User | None] = relationship("User", foreign_keys=[user_id])
    roles: Mapped[list[MemberRole]] = relationship("MemberRole", back_populates="member", cascade="all, delete-orphan")


class MemberRole(TimestampedUUIDModel):
    __tablename__ = "member_roles"

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[OfficeBearerRole] = mapped_column(
        Enum(OfficeBearerRole, name="office_bearer_role_enum", native_enum=False),
        default=OfficeBearerRole.MEMBER,
        nullable=False,
    )
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    member: Mapped[Member] = relationship("Member", back_populates="roles")
