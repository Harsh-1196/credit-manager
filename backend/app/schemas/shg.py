import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.db.models.shg import InterestType, SHGStatus


class GroupSettingsResponse(BaseModel):
    id: uuid.UUID
    shg_id: uuid.UUID
    monthly_saving_amount: str
    late_fine_per_day: str
    fine_grace_days: int
    default_interest_rate: str
    interest_type: InterestType
    max_loan_multiple: str
    min_tenure_months: int
    max_tenure_months: int
    processing_fee_percent: str
    penalty_interest_rate: str
    created_at: datetime
    updated_at: datetime


class GroupSettingsUpdateRequest(BaseModel):
    monthly_saving_amount: str | None = None
    late_fine_per_day: str | None = None
    fine_grace_days: int | None = None
    default_interest_rate: str | None = None
    interest_type: InterestType | None = None
    max_loan_multiple: str | None = None
    min_tenure_months: int | None = None
    max_tenure_months: int | None = None
    processing_fee_percent: str | None = None
    penalty_interest_rate: str | None = None


class SHGCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    village: str = Field(min_length=2, max_length=255)
    ward: str | None = None
    district: str = Field(min_length=2, max_length=255)
    formation_date: date
    meeting_day: str = Field(min_length=1, max_length=50)
    meeting_frequency: str = Field(default="MONTHLY")
    bank_account_label: str | None = None
    settings: GroupSettingsUpdateRequest | None = None


class SHGUpdateRequest(BaseModel):
    name: str | None = None
    village: str | None = None
    ward: str | None = None
    district: str | None = None
    meeting_day: str | None = None
    meeting_frequency: str | None = None
    bank_account_label: str | None = None
    status: SHGStatus | None = None


class SHGResponse(BaseModel):
    id: uuid.UUID
    name: str
    village: str
    ward: str | None = None
    district: str
    formation_date: date
    meeting_day: str
    meeting_frequency: str
    bank_account_label: str | None = None
    status: SHGStatus
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    settings: GroupSettingsResponse | None = None
