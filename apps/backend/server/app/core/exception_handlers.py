import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.response import ApiError

logger = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _http_error_message(exception: StarletteHTTPException) -> str:
    if exception.status_code == 404 and exception.detail == "Not Found":
        return "请求的资源不存在"
    if isinstance(exception.detail, str):
        return exception.detail
    return "请求处理失败"


async def http_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, StarletteHTTPException):
        raise TypeError("异常处理器收到了非 HTTP 异常")
    payload = ApiError(
        code=exception.status_code,
        timestamp=_utc_timestamp(),
        path=request.url.path,
        method=request.method,
        message=_http_error_message(exception),
    )
    return JSONResponse(
        status_code=exception.status_code,
        content=payload.model_dump(mode="json"),
        headers=exception.headers,
    )


async def validation_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, RequestValidationError):
        raise TypeError("参数校验处理器收到了非校验异常")
    payload = ApiError(
        code=422,
        timestamp=_utc_timestamp(),
        path=request.url.path,
        method=request.method,
        message="请求参数验证失败",
    )
    return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))


async def unhandled_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    logger.error("未处理的服务器异常", exc_info=exception)
    payload = ApiError(
        code=500,
        timestamp=_utc_timestamp(),
        path=request.url.path,
        method=request.method,
        message="服务器内部错误",
    )
    return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))


def register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
