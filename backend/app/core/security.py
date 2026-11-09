import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AppError

ph = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token (15-minute default)."""
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if additional_claims:
        to_encode.update(additional_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError as err:
        raise AppError(
            code="TOKEN_EXPIRED",
            message="Access token has expired.",
            status_code=401,
            details={"reason": "token_expired"},
        ) from err
    except jwt.InvalidTokenError as err:
        raise AppError(
            code="INVALID_TOKEN",
            message="Invalid access token.",
            status_code=401,
            details={"reason": "invalid_token"},
        ) from err


def generate_refresh_token() -> str:
    """Generate a high-entropy random string for use as a refresh token."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a refresh token for safe database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_urlsafe(32)


def mask_phone(phone: str | None) -> str | None:
    """Mask phone number preserving only the last 4 digits: e.g. ******3210."""
    if not phone:
        return phone
    cleaned = phone.strip()
    if len(cleaned) <= 4:
        return cleaned
    return f"{'*' * (len(cleaned) - 4)}{cleaned[-4:]}"


def mask_address(address: str | None) -> str | None:
    """Mask address displaying only city/district or truncated preview."""
    if not address:
        return address
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) > 1:
        return f"***, {parts[-1]}"
    return "***"


def mask_pii_dict(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mask sensitive PII fields in before/after dictionaries for audit logs."""
    if not data:
        return data
    masked = dict(data)
    sensitive_keys = {"password_hash", "password", "token", "token_hash", "secret"}
    for k in list(masked.keys()):
        if k in sensitive_keys:
            masked[k] = "[REDACTED]"
        elif k == "phone" and isinstance(masked[k], str):
            masked[k] = mask_phone(masked[k])
        elif k == "address" and isinstance(masked[k], str):
            masked[k] = mask_address(masked[k])
    return masked
