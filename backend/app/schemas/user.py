import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models.auth import UserRole


class UserGroupAccessItem(BaseModel):
    group_id: uuid.UUID
    group_name: str | None = None
    access_level: str


class UserSummaryResponse(BaseModel):
    id: uuid.UUID
    email: str
    phone: str | None = None
    role: UserRole
    is_active: bool


class UserDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    phone: str | None = None
    role: UserRole
    is_active: bool
    failed_login_count: int
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    group_access: list[UserGroupAccessItem] = []
    member_id: uuid.UUID | None = None
    member_shg_id: uuid.UUID | None = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    role: UserRole
    phone: str | None = None
    group_ids: list[uuid.UUID] = []


class UserUpdateRequest(BaseModel):
    phone: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    group_ids: list[uuid.UUID] | None = None
