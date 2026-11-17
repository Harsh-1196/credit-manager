from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.models.auth import User, UserRole
from app.db.models.outbox import OutboxEvent, OutboxEventStatus
from app.db.models.reconciliation import ReconciliationRun
from app.db.session import get_db
from app.domain.reconciliation.service import run_reconciliation
from app.schemas.reconciliation import ReconciliationRunResponse, WorkerStatusResponse

router = APIRouter(tags=["reconciliation"])


@router.post("/reconciliation/run", response_model=ReconciliationRunResponse)
async def trigger_reconciliation(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReconciliationRunResponse:
    """Trigger a complete financial reconciliation run across all groups. Restricted to ADMIN."""
    run_record = await run_reconciliation(db, triggered_by=current_user.id)
    return ReconciliationRunResponse.model_validate(run_record)


@router.get("/reconciliation/latest", response_model=ReconciliationRunResponse | None)
async def get_latest_reconciliation(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReconciliationRunResponse | None:
    """Retrieve the most recent financial reconciliation run result. Restricted to ADMIN."""
    stmt = select(ReconciliationRun).order_by(ReconciliationRun.run_at.desc()).limit(1)
    res = await db.execute(stmt)
    latest = res.scalar_one_or_none()
    if not latest:
        return None
    return ReconciliationRunResponse.model_validate(latest)


@router.get("/reconciliation/runs", response_model=list[ReconciliationRunResponse])
async def list_reconciliation_runs(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ReconciliationRunResponse]:
    """List historical reconciliation execution runs. Restricted to ADMIN."""
    stmt = select(ReconciliationRun).order_by(ReconciliationRun.run_at.desc()).limit(limit)
    res = await db.execute(stmt)
    runs = list(res.scalars().all())
    return [ReconciliationRunResponse.model_validate(r) for r in runs]


@router.get("/system/worker-status", response_model=WorkerStatusResponse)
async def get_worker_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkerStatusResponse:
    """
    Returns worker health status, queue backlog counts, and processing lag in seconds.
    Used by frontend status indicators to monitor background processing lag.
    """
    # Counts by status
    pending_stmt = select(func.count(OutboxEvent.id)).where(OutboxEvent.status == OutboxEventStatus.PENDING)
    processing_stmt = select(func.count(OutboxEvent.id)).where(OutboxEvent.status == OutboxEventStatus.PROCESSING)
    failed_stmt = select(func.count(OutboxEvent.id)).where(OutboxEvent.status == OutboxEventStatus.FAILED)
    dead_letter_stmt = select(func.count(OutboxEvent.id)).where(OutboxEvent.status == OutboxEventStatus.DEAD_LETTER)

    pending_count = (await db.execute(pending_stmt)).scalar_one() or 0
    processing_count = (await db.execute(processing_stmt)).scalar_one() or 0
    failed_count = (await db.execute(failed_stmt)).scalar_one() or 0
    dead_letter_count = (await db.execute(dead_letter_stmt)).scalar_one() or 0

    # Oldest pending event for lag computation
    oldest_stmt = (
        select(OutboxEvent.created_at)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
        .order_by(OutboxEvent.created_at.asc())
        .limit(1)
    )
    oldest_created = (await db.execute(oldest_stmt)).scalar_one_or_none()

    lag_seconds = 0.0
    if oldest_created:
        now = datetime.now(UTC)
        if oldest_created.tzinfo is None:
            oldest_created = oldest_created.replace(tzinfo=UTC)
        lag_seconds = max(0.0, (now - oldest_created).total_seconds())

    # Latest processed event
    latest_stmt = (
        select(OutboxEvent.processed_at)
        .where(OutboxEvent.status == OutboxEventStatus.PUBLISHED)
        .order_by(OutboxEvent.processed_at.desc())
        .limit(1)
    )
    last_processed_at = (await db.execute(latest_stmt)).scalar_one_or_none()

    worker_status = "HEALTHY"
    if dead_letter_count > 0 or failed_count > 5 or lag_seconds > 60.0:
        worker_status = "DEGRADED"
    elif pending_count == 0 and processing_count == 0:
        worker_status = "IDLE"

    return WorkerStatusResponse(
        worker_status=worker_status,
        pending_events_count=pending_count,
        processing_events_count=processing_count,
        failed_events_count=failed_count,
        dead_letter_count=dead_letter_count,
        lag_seconds=round(lag_seconds, 2),
        last_event_processed_at=last_processed_at,
    )
