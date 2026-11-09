from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("app.core.errors")


class AppError(Exception):
    """
    Domain and application level base exception returning uniform error structure.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def build_error_response(
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    req_id = request_id or request_id_ctx.get() or "unknown"
    payload = {
        "code": code,
        "message": message,
        "details": details if details is not None else {},
        "request_id": req_id,
    }
    return JSONResponse(status_code=status_code, content=payload)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    app_exc = exc if isinstance(exc, AppError) else AppError("INTERNAL_ERROR", str(exc))
    logger.warning(
        f"Application error: {app_exc.code} - {app_exc.message}",
        extra={"code": app_exc.code, "details": app_exc.details, "status_code": app_exc.status_code},
    )
    req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
    return build_error_response(
        code=app_exc.code,
        message=app_exc.message,
        status_code=app_exc.status_code,
        details=app_exc.details,
        request_id=req_id,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    http_exc = (
        exc if isinstance(exc, StarletteHTTPException) else StarletteHTTPException(status_code=500, detail=str(exc))
    )
    code_map: dict[int, str] = {
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(http_exc.status_code, f"HTTP_{http_exc.status_code}")
    message = str(http_exc.detail) if http_exc.detail else "An HTTP error occurred."
    req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
    return build_error_response(
        code=code,
        message=message,
        status_code=http_exc.status_code,
        details={},
        request_id=req_id,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    errors_list = []
    if isinstance(exc, RequestValidationError):
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []))
            errors_list.append(
                {
                    "field": loc,
                    "message": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )

    req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
    return build_error_response(
        code="VALIDATION_ERROR",
        message="Request input validation failed.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors_list},
        request_id=req_id,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
    logger.exception(f"Unhandled server error: {exc}", extra={"request_id": req_id})
    return build_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={},
        request_id=req_id,
    )
