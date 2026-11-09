import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.db.models.shg import MemberStatus, OfficeBearerRole


class MemberCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = None
    address: str | None = None
    id_proof_type: str | None = None
    id_proof_number: str | None = Field(default=None, description="Will be sanitized to store last 4 digits only")
    date_of_birth: date | None = None
    joined_on: date
    user_id: uuid.UUID | None = None
    role: OfficeBearerRole = OfficeBearerRole.MEMBER


class MemberUpdateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    address: str | None = None
    id_proof_type: str | None = None
    id_proof_number: str | None = None
    date_of_birth: date | None = None
    role: OfficeBearerRole | None = None


class MemberExitRequest(BaseModel):
    exited_on: date
    reason: str | None = None


class MemberResponse(BaseModel):
    id: uuid.UUID
    shg_id: uuid.UUID
    user_id: uuid.UUID | None = None
    full_name: str
    phone: str | None = None
    address: str | None = None
    id_proof_type: str | None = None
    id_proof_last4: str | None = None
    date_of_birth: date | None = None
    joined_on: date
    exited_on: date | None = None
    status: MemberStatus
    roles: list[str] = []
    created_at: datetime
    updated_at: datetime
