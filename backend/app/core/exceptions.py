import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.base import make_error

logger = logging.getLogger(__name__)


class AppError(Exception):
    """业务异常，统一返回 {code, message} 格式。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.code if exc.code in range(400, 600) else 400,
            content=make_error(exc.code, exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 把 422 的具体校验错误打到日志 + 返回给前端，方便调试
        errs = exc.errors()
        logger.warning("[422 validation] %s %s → %s", request.method, request.url.path, errs)
        # 简化错误信息：取第一个字段错误
        first = errs[0] if errs else {}
        loc = ".".join(str(x) for x in first.get("loc", [])[1:])  # 去掉 'body' 前缀
        msg = f"参数错误：{loc} - {first.get('msg', '校验失败')}"
        return JSONResponse(
            status_code=422,
            content=make_error(422, msg).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=make_error(500, "服务器内部错误").model_dump(),
        )
