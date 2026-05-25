import time
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None
    timestamp: int


def make_ok(data: object = None, message: str = "ok") -> BaseResponse:
    return BaseResponse(
        code=200,
        message=message,
        data=data,
        timestamp=int(time.time()),
    )


def make_error(code: int, message: str) -> BaseResponse:
    return BaseResponse(
        code=code,
        message=message,
        data=None,
        timestamp=int(time.time()),
    )
