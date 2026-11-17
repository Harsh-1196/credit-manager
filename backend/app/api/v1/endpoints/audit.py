import csv
import io
import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.audit.verifier import verify_audit_chain
from app.db.models.auth import User, UserRole
from app.db.models.platform import AuditLog
from app.db.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogRowResponse(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None = None
    actor_role: str | None = None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    prev_hash: str | None = None
    row_hash: str

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRowResponse]
    total: int
    limit: int
    offset: int


class AuditVerificationResponse(BaseModel):
    valid: bool
    count: int
    broken_at_index: int | None = None
    broken_at_id: str | None = None
    error: str | None = None
    message: str


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.AUDITOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
    actor_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditLogListResponse:
    """Filterable audit trail log entries. Restricted to ADMIN and AUDITOR roles."""
    stmt = select(AuditLog)
    count_stmt = select(func.count(AuditLog.id))

    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
        count_stmt = count_stmt.where(AuditLog.actor_id == actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
        count_stmt = count_stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    if from_date:
        stmt = stmt.where(func.date(AuditLog.occurred_at) >= from_date)
        count_stmt = count_stmt.where(func.date(AuditLog.occurred_at) >= from_date)
    if to_date:
        stmt = stmt.where(func.date(AuditLog.occurred_at) <= to_date)
        count_stmt = count_stmt.where(func.date(AuditLog.occurred_at) <= to_date)

    total = (await db.execute(count_stmt)).scalar_one() or 0
    stmt = stmt.order_by(desc(AuditLog.occurred_at)).limit(limit).offset(offset)
    rows = list((await db.execute(stmt)).scalars().all())

    return AuditLogListResponse(
        items=[AuditLogRowResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/verify", response_model=AuditVerificationResponse)
async def verify_audit_trail(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.AUDITOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditVerificationResponse:
    """
    Verifies the cryptographic SHA-256 hash chain across all audit logs.
    Restricted to ADMIN and AUDITOR roles.
    """
    res = await verify_audit_chain(db)
    return AuditVerificationResponse(**res)


@router.get("/export")
async def export_audit_logs_csv(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.AUDITOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
    actor_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> Response:
    """Exports filtered audit trail records to a CSV file. Restricted to ADMIN and AUDITOR."""
    stmt = select(AuditLog)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if from_date:
        stmt = stmt.where(func.date(AuditLog.occurred_at) >= from_date)
    if to_date:
        stmt = stmt.where(func.date(AuditLog.occurred_at) <= to_date)

    stmt = stmt.order_by(desc(AuditLog.occurred_at)).limit(5000)
    rows = list((await db.execute(stmt)).scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID",
        "Timestamp (UTC)",
        "Actor ID",
        "Actor Role",
        "Action",
        "Entity Type",
        "Entity ID",
        "Before",
        "After",
        "IP Address",
        "Row Hash",
        "Prev Hash",
    ])

    for r in rows:
        writer.writerow([
            str(r.id),
            r.occurred_at.isoformat(),
            str(r.actor_id) if r.actor_id else "",
            r.actor_role or "",
            r.action,
            r.entity_type,
            str(r.entity_id),
            json.dumps(r.before or {}),
            json.dumps(r.after or {}),
            r.ip or "",
            r.row_hash,
            r.prev_hash or "",
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'},
    )
