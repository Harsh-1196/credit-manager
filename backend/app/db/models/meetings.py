import enum
import uuid
from datetime import date

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedUUIDModel


class MeetingStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    HELD = "HELD"
    CANCELLED = "CANCELLED"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    EXCUSED = "EXCUSED"


class Meeting(TimestampedUUIDModel):
    __tablename__ = "meetings"

    shg_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus),
        default=MeetingStatus.SCHEDULED,
        nullable=False,
        index=True,
    )
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    attendance_records: Mapped[list["Attendance"]] = relationship(
        "Attendance",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Attendance(TimestampedUUIDModel):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("meeting_id", "member_id", name="uq_attendance_meeting_member"),)

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus),
        default=AttendanceStatus.PRESENT,
        nullable=False,
    )

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="attendance_records")
