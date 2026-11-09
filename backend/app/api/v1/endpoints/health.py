from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.session import get_db

router = APIRouter()
logger = get_logger("app.api.health")


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """
    Liveness probe: verifies that the web service is running and serving requests.
    """
    return {"status": "ok"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """
    Readiness probe: verifies that the web service is ready to accept traffic
    by checking database connectivity.
    """
    try:
        result = await db.execute(text("SELECT 1"))
        val = result.scalar()
        if val != 1:
            raise ValueError(f"Unexpected query result: {val}")
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        raise AppError(
            code="SERVICE_UNAVAILABLE",
            message="Database connection is not ready or unreachable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"error": str(exc)},
        ) from exc
