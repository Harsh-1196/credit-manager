from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import get_logger, setup_logging
from app.core.metrics import get_metrics_content
from app.core.middleware import (
    AuditMiddleware,
    MaxBodySizeMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.telemetry import setup_telemetry
from app.db.session import engine

# Initialize logging and OpenTelemetry immediately
setup_logging()
setup_telemetry()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Application starting up...", extra={"environment": settings.ENVIRONMENT})
    yield
    logger.info("Application shutting down...")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Custom Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(RequestContextMiddleware)

# CORS
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Exception handlers for uniform error format
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Direct root-level /health and /ready routes for load balancers & container healthchecks
app.include_router(health_router, tags=["system"])


@app.get("/metrics", tags=["system"], include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint for scraping."""
    content, content_type = get_metrics_content()
    return Response(content=content, media_type=content_type)
