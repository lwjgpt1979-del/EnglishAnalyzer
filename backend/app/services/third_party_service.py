"""第三方付费 API 资源总览:图像 / 声音 / LLM / 存储 的配置状态清单。

只读地从 settings 判断每个第三方能力「配了真 key 还是占位 dev-mock」,给 admin 一个统一总览。
用量/成本/余额另有专门端点(LLM:/admin/llm-usage、/admin/llm-balance;TTS:cos_usage)。
"""
from __future__ import annotations

from app.core.config import settings


def _real(v: str | None, *placeholders: str) -> bool:
    """key 非空且不以任一占位前缀开头 → 视为已配真 key。"""
    s = (v or "").strip()
    return bool(s) and not any(s.startswith(p) for p in placeholders)


def status_inventory() -> dict:
    """所有第三方付费能力的配置状态,按类别分组。每项:
      {name, provider, api, purpose, configured, mode(real/mock), billing, console}"""
    aiart_ok = _real(settings.tencent_aiart_secret_id, "placeholder")
    # 视频(词力通动图):两个可选 provider 都列出,各自显示配置状态,并标当前启用哪个。
    # 由 settings.video_provider 决定实际走哪个(selfhost=自托管 GPU / zhipu=智谱云)。
    _vp = settings.video_provider
    _active = lambda cur: "(当前启用)" if _vp == cur else ""  # noqa: E731
    video_items = [
        {"category": "视频", "name": f"自托管文生视频·Wan2.2{_active('selfhost')}",
         "provider": "自托管 GPU(Featurize 4090)",
         "api": settings.selfhost_i2v_url or "(未配 URL)",
         "purpose": "词力通动图(文生视频:文字→动画,主体一致)",
         "configured": bool(settings.selfhost_i2v_url),
         "billing": "GPU 按小时(无单次调用费)",
         "console": "租的 GPU 机 · deploy/i2v_server.py(POST /t2v)", "usage": None},
        {"category": "视频", "name": f"智谱 CogVideoX 图生视频{_active('zhipu')}",
         "provider": "智谱 AI(BigModel)", "api": settings.zhipu_video_model,
         "purpose": "词力通动图(云 API·图生视频)",
         "configured": _real(settings.zhipu_video_api_key, "zhipu-placeholder"),
         "billing": "flash 免费(限流)/ cogvideox-2 ¥0.5次 / -3 ¥1次",
         "console": "bigmodel.cn(财务/资源包)", "usage": None},
    ]
    items = [
        # —— LLM ——
        {"category": "LLM", "name": "DeepSeek 主模型", "provider": "DeepSeek",
         "api": settings.llm_model, "purpose": "长难句/语法/阅读解析、知识点归类、讲解生成、评分",
         "configured": _real(settings.deepseek_api_key, "sk-placeholder"),
         "billing": "按 token 后付费", "console": "platform.deepseek.com(余额可在本页查)",
         "usage": "llm"},
        {"category": "LLM", "name": "DeepSeek 快档", "provider": "DeepSeek",
         "api": settings.llm_model_fast, "purpose": "抽取/打分等规格明确任务(便宜档)",
         "configured": _real(settings.deepseek_api_key, "sk-placeholder"),
         "billing": "按 token 后付费", "console": "同上", "usage": "llm"},
        {"category": "LLM", "name": "豆包 Vision", "provider": "火山方舟(豆包)",
         "api": settings.doubao_vision_model, "purpose": "整卷上传·看图拆题(多模态 OCR)",
         "configured": _real(settings.doubao_api_key, "placeholder"),
         "billing": "按 token 后付费", "console": "console.volcengine.com/ark", "usage": None},
        # —— 图像 ——
        {"category": "图像", "name": "腾讯混元·文生图", "provider": "腾讯云 AIArt",
         "api": "TextToImageLite", "purpose": "词力通配图(静态图)",
         "configured": aiart_ok, "billing": "资源包 / 后付费",
         "console": "腾讯云 AI绘画 → 混元生图资源包", "usage": None},
        # —— 视频 ——
        *video_items,
        # —— 声音 ——
        {"category": "声音", "name": "火山 TTS 语音合成", "provider": "火山引擎",
         "api": "BigTTS", "purpose": "单词/例句/听力 语音合成",
         "configured": settings.tts_provider != "mock" and bool(settings.volc_tts_appid)
                       and bool(settings.volc_tts_access_token),
         "billing": "按次/字符 后付费", "console": "console.volcengine.com 语音技术", "usage": "tts"},
        {"category": "声音", "name": "腾讯智聆口语评测", "provider": "腾讯云 SOE",
         "api": "SOE WebSocket", "purpose": "跟读发音评测",
         "configured": _real(settings.tencent_soe_secret_key, "placeholder")
                       and _real(settings.tencent_soe_appid, "placeholder"),
         "billing": "按次 后付费", "console": "腾讯云 智聆口语评测", "usage": None},
        # —— 存储 / OCR ——
        {"category": "存储 / OCR", "name": "腾讯云 COS 对象存储", "provider": "腾讯云 COS",
         "api": settings.cos_bucket, "purpose": "图片/音频/GIF 持久化直链",
         "configured": _real(settings.cos_secret_id, "placeholder"),
         "billing": "存储 + 流量后付费", "console": "腾讯云 对象存储 COS", "usage": None},
        {"category": "存储 / OCR", "name": "腾讯云 OCR", "provider": "腾讯云 OCR",
         "api": "OCR", "purpose": "传统 OCR(现主用豆包 Vision,此为备用)",
         "configured": _real(settings.tencent_ocr_secret_id, "placeholder"),
         "billing": "按次 后付费", "console": "腾讯云 文字识别 OCR", "usage": None},
    ]
    for it in items:
        it["mode"] = "real" if it["configured"] else "mock"

    cats: dict[str, list] = {}
    for it in items:
        cats.setdefault(it["category"], []).append(it)
    total = len(items)
    configured = sum(1 for it in items if it["configured"])
    return {"categories": [{"category": c, "items": v} for c, v in cats.items()],
            "total": total, "configured": configured, "mock": total - configured}
