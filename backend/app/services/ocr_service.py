"""OCR 服务：阿里云（印刷体）+ 腾讯云（手写体）双引擎识别。

Dev 模式（access_key 以 'placeholder' 开头）返回 mock 文字，无需真实 API Key。
两路 SDK 均为同步接口，用 asyncio.to_thread() 包装为异步。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

_log = logging.getLogger(__name__)


# ── 常量 ──────────────────────────────────────────────────────────────────────

_ALIYUN_ENDPOINT = "ocr-api.cn-hangzhou.aliyuncs.com"
_TENCENT_REGION = "ap-guangzhou"

_MOCK_PRINTED = (
    "27. The teacher asked the students to _____ their homework on time.\n"
    "A. hand in  B. hand out  C. hand over  D. hand up\n"
    "28. She _____ in Beijing for three years before she moved to Shanghai.\n"
    "A. lived  B. had lived  C. has lived  D. lives"
)
_MOCK_HANDWRITTEN = "27. B\n28. B"


# ── 返回结构 ──────────────────────────────────────────────────────────────────


@dataclass
class OcrResult:
    """两路 OCR 原始识别结果。"""
    printed_text: str    # 阿里云印刷体识别结果
    handwritten_text: str  # 腾讯云手写体识别结果


# ── Dev 模式检测 ──────────────────────────────────────────────────────────────


def _is_aliyun_dev_mode() -> bool:
    return settings.aliyun_ocr_access_key_id.startswith("placeholder")


def _is_tencent_ocr_dev_mode() -> bool:
    return settings.tencent_ocr_secret_id.startswith("placeholder")


# ── 阿里云 OCR（印刷体，同步包装）────────────────────────────────────────────


def _aliyun_recognize_sync(image_url: str) -> str:
    """调用阿里云 OCR 通用文字识别（同步）。"""
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707 import models as ocr_models
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=settings.aliyun_ocr_access_key_id,
        access_key_secret=settings.aliyun_ocr_access_key_secret,
        endpoint=_ALIYUN_ENDPOINT,
    )
    client = Client(config)
    request = ocr_models.RecognizeGeneralRequest(url=image_url)
    response = client.recognize_general(request)
    # response.body.data 为识别到的文字字符串
    return response.body.data or ""


async def _aliyun_recognize(image_url: str) -> str:
    """异步包装：阿里云印刷体 OCR。"""
    return await asyncio.to_thread(_aliyun_recognize_sync, image_url)


# ── 腾讯云 OCR（手写体，同步包装）────────────────────────────────────────────


def _tencent_handwriting_sync(image_url: str) -> str:
    """调用腾讯云手写识别 OCR（同步）。"""
    from tencentcloud.common import credential
    from tencentcloud.ocr.v20181119 import ocr_client, models

    cred = credential.Credential(
        settings.tencent_ocr_secret_id,
        settings.tencent_ocr_secret_key,
    )
    client = ocr_client.OcrClient(cred, _TENCENT_REGION)
    req = models.GeneralHandwritingOCRRequest()
    req.ImageUrl = image_url
    resp = client.GeneralHandwritingOCR(req)
    # TextDetections 是 list[TextDetection]，每项有 DetectedText
    if not resp.TextDetections:
        return ""
    return "\n".join(item.DetectedText for item in resp.TextDetections)


async def _tencent_handwriting(image_url: str) -> str:
    """异步包装：腾讯云手写体 OCR。"""
    return await asyncio.to_thread(_tencent_handwriting_sync, image_url)


# ── Provider 抽象 ─────────────────────────────────────────────────────────────


class OcrProvider(Protocol):
    """OCR 提供方接口。换厂商只需实现本协议并在 get_ocr_provider() 返回新实例。"""

    async def recognize(self, image_url: str) -> OcrResult:
        """对单张图片做 OCR，返回印刷体 + 手写体识别结果。"""
        ...


class DualEngineOcrProvider:
    """默认实现：阿里云印刷体 + 腾讯云手写体双引擎并行识别。

    Dev 模式（access_key 以 'placeholder' 开头）跳过真实 API 返回 mock 文字。
    任一路命中 placeholder 即对该路用 mock，另一路仍走真实 API。
    """

    async def recognize(self, image_url: str) -> OcrResult:
        if _is_aliyun_dev_mode() and _is_tencent_ocr_dev_mode():
            # 两路均为 placeholder → 完整 dev mock
            return OcrResult(
                printed_text=_MOCK_PRINTED,
                handwritten_text=_MOCK_HANDWRITTEN,
            )

        # 至少一路为真实 API — 用 _noop() 作占位，保证 gather 两槽类型一致 (str)
        async def _noop() -> str:
            return ""

        printed_coro = _noop() if _is_aliyun_dev_mode() else _aliyun_recognize(image_url)
        handwritten_coro = (
            _noop() if _is_tencent_ocr_dev_mode() else _tencent_handwriting(image_url)
        )

        printed_result, handwritten_result = await asyncio.gather(
            printed_coro, handwritten_coro, return_exceptions=True
        )

        if isinstance(printed_result, Exception):
            _log.error("Aliyun OCR failed: %s", printed_result, exc_info=printed_result)
            printed_result = ""
        if isinstance(handwritten_result, Exception):
            _log.error("Tencent OCR failed: %s", handwritten_result, exc_info=handwritten_result)
            handwritten_result = ""

        printed_text = _MOCK_PRINTED if _is_aliyun_dev_mode() else printed_result
        handwritten_text = (
            _MOCK_HANDWRITTEN if _is_tencent_ocr_dev_mode() else handwritten_result
        )

        return OcrResult(
            printed_text=printed_text,
            handwritten_text=handwritten_text,
        )


# ── 公开接口 ──────────────────────────────────────────────────────────────────

# M40: 默认切换为豆包 Vision provider；DualEngineOcrProvider 保留向下兼容。
def get_ocr_provider() -> OcrProvider:
    """返回当前 OCR provider。M40 起默认使用 DoubaoVisionProvider。"""
    from app.services.doubao_vision_service import DoubaoVisionProvider
    return DoubaoVisionProvider()


# 向下兼容：保留旧单例（已不被 run_ocr 使用，但避免直接引用 _provider 的代码报错）
_provider: OcrProvider = DualEngineOcrProvider()


async def run_ocr(image_url: str) -> OcrResult:
    """并行执行 OCR，返回 OcrResult（委托给当前 provider）。

    保持稳定的公开接口：调用方（user_paper_service / ocr.py 等）只依赖此函数，
    底层厂商切换对它们完全透明。
    """
    from app.services import upload_service
    # 桶对象私有 → 转预签名 GET,第三方 OCR 才拉得到图（外部/dev URL 原样放行）
    return await get_ocr_provider().recognize(upload_service.make_fetch_url(image_url))
