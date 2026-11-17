import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import get_logger, request_id_ctx
from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL

logger = get_logger("app.core.middleware")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check for incoming X-Request-ID or generate new UUID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Set context variable and request state
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id
        request.state.audit_logged = False

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_s = time.perf_counter() - start_time
            duration_ms = round(duration_s * 1000, 2)

            response.headers["X-Request-ID"] = request_id

            if not request.url.path.endswith("/metrics"):
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=request.method,
                    endpoint=request.url.path,
                    status_code=str(response.status_code),
                ).observe(duration_s)
                HTTP_REQUESTS_TOTAL.labels(
                    method=request.method,
                    endpoint=request.url.path,
                    status_code=str(response.status_code),
                ).inc()

            logger.info(
                f"{request.method} {request.url.path} {response.status_code} ({duration_ms}ms)",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                f"{request.method} {request.url.path} failed with exception: {exc} ({duration_ms}ms)",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
            raise exc
        finally:
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enforces security headers: HSTS, X-Content-Type-Options, X-Frame-Options,
    Referrer-Policy, Permissions-Policy, Content-Security-Policy.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none';"
        )

        if settings.COOKIE_SECURE or settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """
    Hardening: Limits incoming request payload sizes to 2 MB to prevent DoS attacks.
    Rejects oversize requests with HTTP 413 Payload Too Large.
    """

    MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 Megabytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.MAX_BODY_BYTES:
                    return Response(
                        content='{"code":"PAYLOAD_TOO_LARGE","message":"Request payload exceeds maximum allowed size (2 MB).","details":{}}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass

        return await call_next(request)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Audit middleware placeholder providing audit tracking context.
    All mutating endpoints explicitly write hash-chained audit log rows with before/after snapshots.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        return await call_next(request)
