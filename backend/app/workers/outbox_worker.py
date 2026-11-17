import asyncio
import logging
import sys
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.outbox import OutboxEventStatus
from app.db.session import AsyncSessionLocal
from app.domain.outbox.consumers import dashboard_read_model_consumer, overdue_and_par_consumer
from app.domain.outbox.service import (
    get_pending_outbox_events,
    mark_event_failed,
    mark_event_published,
)

logger = logging.getLogger("outbox_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def process_outbox_batch(
    db: AsyncSession,
    batch_size: int = 50,
) -> dict[str, int]:
    """
    Core outbox processing pipeline with at-least-once delivery, retry backoff,
    and dead-letter queueing.
    Processes events one by one in isolated sub-transactions so a single failure
    or mid-batch crash leaves already-processed events committed without duplication.
    """
    events = await get_pending_outbox_events(db, batch_size=batch_size)
    if not events:
        return {"processed": 0, "published": 0, "failed": 0, "dead_letter": 0}

    published_count = 0
    failed_count = 0
    dead_letter_count = 0

    for event in events:
        event_id = event.id
        try:
            async with db.begin_nested():
                event.status = OutboxEventStatus.PROCESSING
                await db.flush()

                # Execute consumers sequentially
                await dashboard_read_model_consumer(db, event)
                await overdue_and_par_consumer(db, event)

                await mark_event_published(db, event)

            await db.commit()
            published_count += 1
            logger.info("Successfully published outbox event %s (%s)", event_id, event.event_type)

        except Exception as exc:
            logger.exception("Failed to process outbox event %s: %s", event_id, exc)
            try:
                async with db.begin_nested():
                    new_status = await mark_event_failed(db, event_id, str(exc))
                await db.commit()

                if new_status == OutboxEventStatus.DEAD_LETTER:
                    dead_letter_count += 1
                else:
                    failed_count += 1
            except Exception as inner_exc:
                logger.error("Failed to mark event %s as failed: %s", event_id, inner_exc)
                await db.rollback()

    return {
        "processed": len(events),
        "published": published_count,
        "failed": failed_count,
        "dead_letter": dead_letter_count,
    }


async def poll_outbox_task(ctx: dict[str, Any] | None = None) -> dict[str, int]:
    """ARQ task executing a batch of outbox event polling and publishing."""
    async with AsyncSessionLocal() as session:
        return await process_outbox_batch(session)


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("Outbox worker starting up with Redis at %s", settings.REDIS_URL)


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("Outbox worker shutting down")


class WorkerSettings:
    """ARQ Worker configuration."""

    functions = [poll_outbox_task]
    cron_jobs = [cron(poll_outbox_task, run_at_startup=True, second=set(range(0, 60, 5)))]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown


async def main() -> None:
    """Standalone CLI entry point for testing or direct Docker daemon operation."""
    args = sys.argv[1:]
    once = "--once" in args

    logger.info("Starting outbox worker runner (once=%s)", once)
    while True:
        async with AsyncSessionLocal() as session:
            res = await process_outbox_batch(session)
            if res["processed"] > 0:
                logger.info("Batch result: %s", res)
        if once:
            break
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
