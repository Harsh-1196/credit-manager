import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.platform import IdempotencyRecord


def compute_request_hash(data: Any) -> str:
    """Compute SHA-256 hash of canonical JSON request representation."""
    if data is None:
        raw = "{}"
    elif isinstance(data, (bytes, bytearray)):
        raw = data.decode("utf-8", errors="replace")
    elif isinstance(data, str):
        try:
            # Re-serialize to canonical sorted JSON if string is valid JSON
            parsed = json.loads(data)
            raw = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        except Exception:
            raw = data
    else:
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def check_idempotency(
    db: AsyncSession,
    key: str,
    scope: str,
    request_hash: str,
) -> IdempotencyRecord | None:
    """
    Checks if an idempotency key has been used within scope.
    - If same key & same hash: returns stored record.
    - If same key & different hash: raises 409 Conflict.
    - If not found: returns None.
    """
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.key == key,
        IdempotencyRecord.scope == scope,
    )
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        return None

    if record.request_hash != request_hash:
        raise AppError(
            code="IDEMPOTENCY_CONFLICT",
            message="Idempotency key was previously used with a different request payload.",
            status_code=status.HTTP_409_CONFLICT,
            details={"key": key, "scope": scope},
        )

    return record


async def save_idempotency_record(
    db: AsyncSession,
    key: str,
    scope: str,
    request_hash: str,
    response_status: int,
    response_body: str,
    ttl_hours: int = 24,
) -> IdempotencyRecord:
    """Persist the response of an idempotent request."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=ttl_hours)

    record = IdempotencyRecord(
        key=key,
        scope=scope,
        request_hash=request_hash,
        response_status=response_status,
        response_body=response_body,
        expires_at=expires_at,
    )
    db.add(record)
    await db.flush()
    return record
