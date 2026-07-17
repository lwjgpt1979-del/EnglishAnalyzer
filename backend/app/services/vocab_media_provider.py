"""词力通图/音频 provider（P1 / D-101）。

图片：image_provider='tencent' + 真实 TENCENT_AIART_SECRET_* → 腾讯混元生图极速版
(TextToImageLite)，生成的临时图 URL 下载后上传 COS 持久化，返回 COS 直链；否则 dev-mock。
音频：mock 占位（卡片实际发音走 TTS / tts_service，不依赖这里）。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import urllib.parse
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_cos_client = None

# 腾讯混元生图/图生图硬上限:同时只能 1 个任务(JobNumExceed)。全局信号量串行 + 限流重试,
# 让批量并发时"出图"这步排队(LLM/TTS 仍并发),避免撞上限失败。
_AIART_SEM = asyncio.Semaphore(1)


async def _aiart_call(fn, *args, label: str = "", retries: int = 6, backoff: float = 3.0):
    """在全局信号量内串行调用腾讯 AIArt(fn 同步,to_thread);遇任务上限/限流自动等待重试。"""
    async with _AIART_SEM:
        for attempt in range(retries + 1):
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as e:  # noqa: BLE001
                s = str(e)
                if ("RequestLimitExceeded" in s or "JobNumExceed" in s
                        or "TaskNumExceed" in s) and attempt < retries:
                    logger.warning("[腾讯生图] %s 任务上限,%.0fs 后重试(%d/%d)",
                                   label, backoff, attempt + 1, retries)
                    await asyncio.sleep(backoff)
                    continue
                raise


def is_image_dev_mode() -> bool:
    return (settings.image_provider != "tencent"
            or settings.tencent_aiart_secret_key.startswith("placeholder"))


def is_tts_dev_mode() -> bool:
    return settings.tts_provider == "mock" or settings.tts_api_key.startswith("tts-placeholder")


def _cos_dev() -> bool:
    return settings.cos_secret_key.startswith("placeholder")


def _get_cos_client():
    global _cos_client
    if _cos_client is None:
        from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import]
        _cos_client = CosS3Client(CosConfig(
            Region=settings.cos_region, SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key))
    return _cos_client


# ③M 负向约束(全项目配图铁律):禁一切文字/乱码、禁把词渲染成装饰字、禁无关人物 —— 词不达意的高发根因
_NEG_PROMPT = (
    "text, letters, words, numbers, caption, subtitle, watermark, signage, label, "
    "typography, writing on image, gibberish text, "
    "random unrelated person, extra people, crowd, deformed, blurry, low quality"
)


def _tencent_t2i(prompt: str) -> str | None:
    """腾讯混元生图极速版 TextToImageLite（同步，在 to_thread 中执行）：返回临时图 URL。"""
    from tencentcloud.common import credential
    from tencentcloud.aiart.v20221229 import aiart_client, models
    cred = credential.Credential(
        settings.tencent_aiart_secret_id, settings.tencent_aiart_secret_key)
    client = aiart_client.AiartClient(cred, settings.tencent_aiart_region)
    req = models.TextToImageLiteRequest()
    req.Prompt = prompt[:1024]
    try:
        req.NegativePrompt = _NEG_PROMPT   # SDK/接口若不支持则忽略(下方 setattr 容错)
    except Exception:  # noqa: BLE001
        pass
    req.Resolution = settings.tencent_aiart_resolution
    req.RspImgType = "url"
    req.LogoAdd = 0   # 不加水印
    resp = client.TextToImageLite(req)
    return getattr(resp, "ResultImage", None) or None


async def _persist_to_cos(img_url: str) -> str:
    """下载临时图 → 上传 COS（public-read）→ 返回直链；COS 未配则原样返回临时 URL。"""
    if _cos_dev():
        return img_url
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.get(img_url)
        r.raise_for_status()
        body = r.content
    key = f"vocab/img/{uuid.uuid4().hex}.png"

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=body,
            ContentType="image/png", ACL="public-read")

    await asyncio.to_thread(_put)
    return f"{settings.cos_base_url}/{key}"


async def t2i_to_cos(prompt: str, *, label: str = "") -> str | None:
    """单条完整提示词 → 混元生图极速版 → 下载转存 COS → 返回直链。

    dev-mock 返回 placehold 占位（按 label/prompt 哈希）；失败返回 None（调用方决定兜底）。
    """
    if is_image_dev_mode():
        safe = urllib.parse.quote((label or prompt or "word")[:20])
        h = hashlib.md5((prompt or "").encode()).hexdigest()[:4]
        return f"https://placehold.co/600x400?text={safe}-{h}"
    try:
        tmp = await _aiart_call(_tencent_t2i, prompt, label=(label or prompt[:20]))
        if not tmp:
            return None
        return await _persist_to_cos(tmp)
    except Exception as e:  # noqa: BLE001
        logger.error("[混元生图] %s 失败: %s", label or prompt[:20], e)
        return None


async def persist_image_bytes_to_cos(body: bytes, *, ext: str = "png") -> str | None:
    """上传的图片字节 → COS(public-read)→ 直链;COS 未配返回 None(无处托管)。"""
    if _cos_dev():
        logger.error("[图生图] COS 未配置,上传图无处托管")
        return None
    key = f"vocab/img/{uuid.uuid4().hex}.{ext}"

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=body,
            ContentType=f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}", ACL="public-read")

    await asyncio.to_thread(_put)
    return f"{settings.cos_base_url}/{key}"


async def fetch_image_to_cos(url: str) -> str | None:
    """下载外部图片 URL → 转存 COS(持久化,避免外链过期/CORS)。COS 未配则原样返回。"""
    try:
        return await _persist_to_cos(url)
    except Exception as e:  # noqa: BLE001
        logger.error("[图生图] 下载外链转存失败 %s: %s", url[:40], e)
        return None


def _tencent_i2i(prompt: str, input_url: str, strength: float) -> str | None:
    """腾讯 Img2Img(图像风格化/图生图):基于原图 + 提示词生成变体。strength=重绘幅度。"""
    from tencentcloud.common import credential
    from tencentcloud.aiart.v20221229 import aiart_client, models
    cred = credential.Credential(
        settings.tencent_aiart_secret_id, settings.tencent_aiart_secret_key)
    client = aiart_client.AiartClient(cred, settings.tencent_aiart_region)
    req = models.ImageToImageRequest()
    req.InputUrl = input_url
    if prompt:
        req.Prompt = prompt[:1024]
    req.Strength = strength
    req.RspImgType = "url"
    req.LogoAdd = 0
    resp = client.ImageToImage(req)
    return getattr(resp, "ResultImage", None) or None


async def i2i_to_cos(prompt: str, input_url: str, *, label: str = "",
                     strength: float = 0.6) -> str | None:
    """原图 + 提示词 → 腾讯图生图 → 转存 COS 直链。dev-mock 回退原图;失败返回 None。"""
    if is_image_dev_mode():
        return input_url
    try:
        tmp = await _aiart_call(_tencent_i2i, prompt, input_url, strength,
                                label=(label or prompt[:20]))
        if not tmp:
            return None
        return await _persist_to_cos(tmp)
    except Exception as e:  # noqa: BLE001
        logger.error("[图生图] %s 失败: %s", label or prompt[:20], e)
        return None


def generate_tts(text: str) -> str:
    """返回音频 URL。mock 时返回空串（不写假URL；卡片发音走 tts_service / 火山 TTS 兜底）。"""
    if is_tts_dev_mode():
        return ""
    raise NotImplementedError("真 TTS provider 未接入（卡片发音已走 tts_service）")


# ── 图生视频(词力通动图):provider=zhipu(CogVideoX 云)/ selfhost(自托管 GPU /i2v)────────
def is_video_dev_mode() -> bool:
    """两种 provider 各自的「未配置」判定:未配则回退静态图(不真调)。"""
    if settings.video_provider == "selfhost":
        return not settings.selfhost_i2v_url
    k = settings.zhipu_video_api_key
    return (not k) or k.startswith("zhipu-placeholder")


async def _persist_video_bytes_to_cos(body: bytes) -> str | None:
    """mp4 字节 → 上传 COS(public-read,.mp4)→ 返回直链;COS 未配则无处托管,返回 None。"""
    if _cos_dev():
        logger.error("[图生视频] COS 未配置,自托管返回的视频字节无处托管")
        return None
    key = f"vocab/video/{uuid.uuid4().hex}.mp4"

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=body,
            ContentType="video/mp4", ACL="public-read")

    await asyncio.to_thread(_put)
    return f"{settings.cos_base_url}/{key}"


async def _persist_video_to_cos(video_url: str) -> str:
    """下载生成的 mp4 → 上传 COS(public-read,.mp4)→ 返回直链;COS 未配则原样返回临时 URL。"""
    if _cos_dev():
        return video_url
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.get(video_url)
        r.raise_for_status()
        body = r.content
    return await _persist_video_bytes_to_cos(body) or video_url


async def _selfhost_i2v_to_cos(prompt: str, image_url: str, *, label: str = "") -> str | None:
    """自托管 GPU 上的 /i2v 服务:POST {image_url,prompt} 同步返回 mp4 字节 → 转存 COS。"""
    lab = label or prompt[:20]
    url = settings.selfhost_i2v_url
    headers = {}
    if settings.selfhost_i2v_token:
        headers["Authorization"] = f"Bearer {settings.selfhost_i2v_token}"
    try:
        async with httpx.AsyncClient(timeout=600) as client:   # 4090 上 LTX 约 30-90s,给足
            r = await client.post(url, headers=headers,
                                  json={"image_url": image_url, "prompt": prompt[:512]})
            r.raise_for_status()
            body = r.content
        if not body:
            logger.error("[图生视频·自托管] %s 返回空", lab)
            return None
        return await _persist_video_bytes_to_cos(body)
    except Exception as e:  # noqa: BLE001
        logger.error("[图生视频·自托管] %s 失败: %s", lab, e)
        return None


async def i2v_to_cos(prompt: str, image_url: str, *, label: str = "",
                     poll_interval: float = 5.0, max_wait: float = 260.0,
                     submit_retries: int = 3, submit_backoff: float = 12.0) -> str | None:
    """现有静态配图当首帧 + 一句动作描述 → 图生视频 → 转存 COS 返 mp4 直链。

    provider 分派:selfhost 走自托管 GPU;否则走智谱 CogVideoX 云。
    dev-mock(未配置)回退传入的静态图(不真调);失败返回 None(调用方决定兜底)。
    """
    if is_video_dev_mode():
        return image_url
    if settings.video_provider == "selfhost":
        return await _selfhost_i2v_to_cos(prompt, image_url, label=label)
    # ── 智谱 CogVideoX 云:异步 POST 提交拿 task id → GET 轮询到 SUCCESS 取视频 URL ──
    # 免费档常被全局限流(429/code 1305「访问量过大」)→ 提交端退避重试骑过瞬时拥塞。
    base = settings.zhipu_video_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.zhipu_video_api_key}"}
    lab = label or prompt[:20]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            task_id = None
            for attempt in range(submit_retries + 1):
                resp = await client.post(
                    f"{base}/videos/generations", headers=headers,
                    json={"model": settings.zhipu_video_model, "prompt": prompt[:512],
                          "image_url": image_url})
                if resp.status_code == 429:
                    code = str(((resp.json() or {}).get("error") or {}).get("code") or "")
                    # 1305=免费档全局限流(瞬时,可退避重试);其余如 1113=余额不足/无资源包→硬错误快速失败
                    if code != "1305":
                        logger.error("[图生视频] %s 提交失败(429 code=%s,非限流,勿重试): %s",
                                     lab, code, resp.text[:200])
                        return None
                    if attempt < submit_retries:
                        logger.warning("[图生视频] %s 提交被限流(1305 访问量过大),第 %d 次,%.0fs 后重试",
                                       lab, attempt + 1, submit_backoff)
                        await asyncio.sleep(submit_backoff)
                        continue
                    logger.error("[图生视频] %s 提交限流重试耗尽(免费档访问量过大)", lab)
                    return None
                resp.raise_for_status()
                task_id = (resp.json() or {}).get("id")
                break
            if not task_id:
                logger.error("[图生视频] %s 提交未返回任务 id", lab)
                return None
            waited = 0.0
            while waited < max_wait:
                await asyncio.sleep(poll_interval)
                waited += poll_interval
                q = await client.get(f"{base}/videos/generations/{task_id}", headers=headers)
                q.raise_for_status()
                j = q.json() or {}
                status = j.get("task_status") or "PROCESSING"
                if status == "SUCCESS":
                    vids = j.get("video_result") or []
                    url = vids[0].get("url") if vids else None
                    if not url:
                        return None
                    return await _persist_video_to_cos(url)
                if status == "FAIL":
                    logger.error("[图生视频] %s 生成失败(FAIL)", lab)
                    return None
            logger.warning("[图生视频] %s 轮询超时(%.0fs 未完成)", lab, max_wait)
            return None
    except Exception as e:  # noqa: BLE001
        logger.error("[图生视频] %s 失败: %s", lab, e)
        return None
