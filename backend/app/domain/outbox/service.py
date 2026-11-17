import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox import DashboardReadModel, OutboxEvent, OutboxEventStatus


async def create_outbox_event(
    db: AsyncSession,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | uuid.UUID,
    shg_id: uuid.UUID | None,
    payload: dict[str, Any],
) -> OutboxEvent:
    """
    Registers an event in the transactional outbox table within the caller's active database transaction.
    Guarantees atomicity: the outbox event is persisted if and only if the business transaction commits.
    """
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        shg_id=shg_id,
        payload=payload,
        status=OutboxEventStatus.PENDING,
        retry_count=0,
        max_retries=5,
        next_retry_at=datetime.now(UTC),
    )
    db.add(event)
    await db.flush()
    return event


async def get_pending_outbox_events(
    db: AsyncSession,
    batch_size: int = 50,
) -> list[OutboxEvent]:
    """
    Polls up to batch_size pending or retriable outbox events.
    Uses SELECT ... FOR UPDATE SKIP LOCKED on PostgreSQL to prevent worker race conditions.
    """
    now = datetime.now(UTC)
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_([OutboxEventStatus.PENDING, OutboxEventStatus.FAILED]),
            OutboxEvent.next_retry_at <= now,
        )
        .order_by(OutboxEvent.created_at.asc())
        .limit(batch_size)
    )

    # Use FOR UPDATE SKIP LOCKED on PostgreSQL; safe no-op on SQLite
    bind = db.bind
    if bind and getattr(bind.dialect, "name", "") == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    res = await db.execute(stmt)
    return list(res.scalars().all())


async def mark_event_published(
    db: AsyncSession,
    event: OutboxEvent,
) -> None:
    """Marks an outbox event as successfully processed by all consumers."""
    event.status = OutboxEventStatus.PUBLISHED
    event.processed_at = datetime.now(UTC)
    event.last_error = None
    await db.flush()


async def mark_event_failed(
    db: AsyncSession,
    event_id: uuid.UUID,
    error_message: str,
) -> OutboxEventStatus:
    """
    Increments retry count with exponential backoff.
    Moves event to DEAD_LETTER status if max retries exceeded.
    """
    stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
    ev = (await db.execute(stmt)).scalar_one()

    ev.retry_count += 1
    ev.last_error = error_message

    if ev.retry_count >= ev.max_retries:
        ev.status = OutboxEventStatus.DEAD_LETTER
    else:
        ev.status = OutboxEventStatus.FAILED
        # Exponential backoff: 2s, 4s, 8s, 16s...
        backoff_seconds = 2**ev.retry_count
        ev.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)

    await db.flush()
    return ev.status


async def get_or_create_dashboard_read_model(
    db: AsyncSession,
    shg_id: uuid.UUID,
) -> DashboardReadModel:
    """Retrieves or initializes the denormalized read model for an SHG."""
    stmt = select(DashboardReadModel).where(DashboardReadModel.shg_id == shg_id)
    res = await db.execute(stmt)
    model = res.scalar_one_or_none()
    if not model:
        model = DashboardReadModel(shg_id=shg_id)
        db.add(model)
        await db.flush()
    return model
