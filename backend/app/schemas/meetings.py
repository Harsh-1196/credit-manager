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


# --- Phase 4: Collection Sheet Schemas ---

class CollectionSheetMemberRow(BaseModel):
    member_id: uuid.UUID
    member_name: str
    attendance_status: AttendanceStatus = AttendanceStatus.PRESENT
    savings_due: str
    emi_due: str
    principal_due: str
    interest_due: str
    arrears: str
    penalty_due: str
    fines_due: str
    total_due: str
    active_loan_id: uuid.UUID | None = None
    active_loan_number: str | None = None


class CollectionSheetTotals(BaseModel):
    total_savings_due: str
    total_emi_due: str
    total_arrears: str
    total_fines_due: str
    total_due: str
    member_count: int


class CollectionSheetResponse(BaseModel):
    meeting_id: uuid.UUID
    shg_id: uuid.UUID
    shg_name: str
    meeting_date: date
    status: MeetingStatus
    period: str
    members: list[CollectionSheetMemberRow]
    totals: CollectionSheetTotals


# --- Phase 4: Batch Collections Schemas ---

class MeetingBatchCollectionItem(BaseModel):
    member_id: uuid.UUID
    attendance_status: AttendanceStatus = AttendanceStatus.PRESENT
    savings_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    loan_repayment_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    fine_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)


class MeetingBatchCollectionsRequest(BaseModel):
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    collections: list[MeetingBatchCollectionItem]
    idempotency_key: str | None = None


class MeetingBatchCollectionsResponse(BaseModel):
    total_collected: str
    total_savings: str
    total_loan_repayment: str
    total_fines: str
    members_count: int
    journal_entries_count: int
    journal_entry_ids: list[uuid.UUID]
    meeting_status: MeetingStatus


# --- Phase 4: Member Attendance History Schemas ---

class MemberAttendanceRecord(BaseModel):
    meeting_id: uuid.UUID
    meeting_date: date
    agenda: str | None = None
    status: AttendanceStatus
    recorded_at: str | None = None


class MemberAttendanceSummary(BaseModel):
    total_meetings: int
    present_count: int
    absent_count: int
    excused_count: int
    attendance_rate: str


class MemberAttendanceResponse(BaseModel):
    member_id: uuid.UUID
    member_name: str
    summary: MemberAttendanceSummary
    records: list[MemberAttendanceRecord]
