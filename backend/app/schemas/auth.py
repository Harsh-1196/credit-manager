from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserSummaryResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummaryResponse


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class MessageResponse(BaseModel):
    message: str
    detail: dict[str, str] = {}
