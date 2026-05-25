from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas.base import make_error


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

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=make_error(500, "服务器内部错误").model_dump(),
        )
