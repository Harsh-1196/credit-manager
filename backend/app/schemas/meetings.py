import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.meetings import AttendanceStatus, MeetingStatus


class AttendanceRecord(BaseModel):
    member_id: uuid.UUID
    status: AttendanceStatus = AttendanceStatus.PRESENT


class AttendanceUpdateRequest(BaseModel):
    attendance: list[AttendanceRecord]


class MeetingCreateRequest(BaseModel):
    meeting_date: date
    agenda: str | None = Field(default=None, max_length=1000)


class MeetingUpdateRequest(BaseModel):
    status: MeetingStatus | None = None
    agenda: str | None = None
    minutes: str | None = None


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shg_id: uuid.UUID
    meeting_date: date
    status: MeetingStatus
    agenda: str | None = None
    minutes: str | None = None
    recorded_by: uuid.UUID | None = None
    attendance_count: int = 0


class MeetingDetailResponse(MeetingResponse):
    attendance: list[AttendanceRecord] = []


class MeetingBatchCollectionItem(BaseModel):
    member_id: uuid.UUID
    savings_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    fine_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)


class MeetingBatchCollectionsRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    collections: list[MeetingBatchCollectionItem]
    idempotency_key: str | None = None


class MeetingBatchCollectionsResponse(BaseModel):
    total_collected: str
    members_count: int
    journal_entry_id: uuid.UUID
