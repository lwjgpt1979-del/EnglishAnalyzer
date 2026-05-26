"""OCR 服务：阿里云（印刷体）+ 腾讯云（手写体）双引擎识别。

Dev 模式（access_key 以 'placeholder' 开头）返回 mock 文字，无需真实 API Key。
两路 SDK 均为同步接口，用 asyncio.to_thread() 包装为异步。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import settings


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


# ── 公开接口 ──────────────────────────────────────────────────────────────────


async def run_ocr(image_url: str) -> OcrResult:
    """并行执行两路 OCR，返回 OcrResult。

    Dev 模式：跳过真实 API，返回 mock 文字（用于本地测试）。
    Prod 模式：两路并行 asyncio.gather()，节省等待时间。
    """
    if _is_aliyun_dev_mode() and _is_tencent_ocr_dev_mode():
        # 两路均为 placeholder → 完整 dev mock
        return OcrResult(
            printed_text=_MOCK_PRINTED,
            handwritten_text=_MOCK_HANDWRITTEN,
        )

    # 至少一路为真实 API
    printed_coro = (
        asyncio.sleep(0) if _is_aliyun_dev_mode()
        else _aliyun_recognize(image_url)
    )
    handwritten_coro = (
        asyncio.sleep(0) if _is_tencent_ocr_dev_mode()
        else _tencent_handwriting(image_url)
    )

    printed_result, handwritten_result = await asyncio.gather(
        printed_coro, handwritten_coro, return_exceptions=True
    )

    printed_text = (
        _MOCK_PRINTED if _is_aliyun_dev_mode()
        else (printed_result if isinstance(printed_result, str) else "")
    )
    handwritten_text = (
        _MOCK_HANDWRITTEN if _is_tencent_ocr_dev_mode()
        else (handwritten_result if isinstance(handwritten_result, str) else "")
    )

    return OcrResult(
        printed_text=printed_text,
        handwritten_text=handwritten_text,
    )
