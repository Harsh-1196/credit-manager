import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.security import mask_pii_dict
from app.db.models.platform import AuditLog


def format_audit_dt(dt: datetime) -> str:
    """Consistently format datetime to UTC ISO string across SQLite and Postgres."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def json_serializer(obj: Any) -> Any:
    """Helper serializer for canonical json encoding."""
    if isinstance(obj, datetime):
        return format_audit_dt(obj)
    if isinstance(obj, (uuid.UUID, Decimal)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def canonical_json(data: dict[str, Any]) -> str:
    """Serialize dictionary to deterministic, canonical JSON."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        default=json_serializer,
        ensure_ascii=False,
    )


def compute_row_hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    """Compute tamper-evident SHA-256 hash chaining with prev_hash."""
    canonical = canonical_json(payload)
    chain_input = f"{prev_hash or ''}{canonical}".encode()
    return hashlib.sha256(chain_input).hexdigest()


async def get_latest_audit_hash(db: AsyncSession) -> str | None:
    """Retrieve the row_hash of the most recent audit log entry."""
    stmt = select(AuditLog.row_hash).order_by(desc(AuditLog.occurred_at), desc(AuditLog.created_at)).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def record_audit_log(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request: Request | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    occurred_at: datetime | None = None,
) -> AuditLog:
    """
    Records an append-only audit log row with hash-chaining and masked PII.
    """
    if occurred_at is None:
        occurred_at = datetime.now(UTC)

    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None

    if request:
        ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
        if not actor_id and hasattr(request.state, "user"):
            actor_id = getattr(request.state.user, "id", None)
            actor_role = getattr(request.state.user, "role", None)

    masked_before = mask_pii_dict(before)
    masked_after = mask_pii_dict(after)
    str_entity_id = str(entity_id)

    prev_hash = await get_latest_audit_hash(db)

    payload = {
        "action": action,
        "actor_id": str(actor_id) if actor_id else None,
        "actor_role": str(actor_role) if actor_role else None,
        "after": masked_after,
        "before": masked_before,
        "entity_id": str_entity_id,
        "entity_type": entity_type,
        "ip": ip,
        "occurred_at": format_audit_dt(occurred_at),
        "request_id": request_id,
        "user_agent": user_agent,
    }

    row_hash = compute_row_hash(prev_hash, payload)

    audit_entry = AuditLog(
        occurred_at=occurred_at,
        actor_id=actor_id,
        actor_role=str(actor_role) if actor_role else None,
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
        action=action,
        entity_type=entity_type,
        entity_id=str_entity_id,
        before=masked_before,
        after=masked_after,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )

    db.add(audit_entry)
    await db.flush()
    return audit_entry
