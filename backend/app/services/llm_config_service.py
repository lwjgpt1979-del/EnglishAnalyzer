"""LLM 模型运行时配置(后台「模型配置」页可改,无需改 .env / 重启)。

存 system_configs.key='llm_model',value={"model": "deepseek-v4-pro"}。
- chat_completion 调用前用 active_model() 取**当前生效模型**(内存缓存,零额外 DB 往返)。
- 缓存在应用启动(lifespan)预热;保存配置时同步刷新。无 DB 配置时回落 settings.llm_model
  (默认 deepseek-v4-pro)。换厂商/换模型只动这页,业务零改动。

注:api_key / base_url 仍走 .env(密钥不入库);这里只管「模型名」这一可频繁切换项。
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.d9_system import SystemConfig

_KEY = "llm_model"

# 当前 endpoint 支持的模型(配置页下拉建议;仍允许自填其它 OpenAI 兼容模型名)
# 经 DeepSeek /models 接口确认(2026-06):仅 deepseek-v4-pro / deepseek-v4-flash。
# deepseek-chat 已不在可用列表(遗留别名,可能到期),不再预设。
PRESET_MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]

# 进程内缓存:active_model() 无需每次查库
_cached_model: str | None = None


def _default_model() -> str:
    return settings.llm_model or "deepseek-v4-pro"


def active_model() -> str:
    """当前生效模型(缓存优先;未预热则回落默认)。chat_completion 用它。"""
    return _cached_model or _default_model()


async def get_model(db: AsyncSession) -> str:
    """读生效模型并预热缓存:DB 覆盖值优先,否则默认。"""
    global _cached_model
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    model = None
    if cfg is not None and isinstance(cfg.value, dict):
        model = (cfg.value.get("model") or "").strip() or None
    _cached_model = model or _default_model()
    return _cached_model


async def set_model(db: AsyncSession, *, model: str, updated_by: uuid.UUID) -> str:
    """保存生效模型(整体覆盖)并刷新缓存。"""
    global _cached_model
    model = (model or "").strip()
    if not model:
        from app.core.exceptions import AppError
        raise AppError(code=400, message="模型名不能为空")
    value = {"model": model}
    cfg = (await db.execute(select(SystemConfig).where(SystemConfig.key == _KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KEY, value=value,
                            description="LLM 生效模型名", updated_by=updated_by))
    else:
        cfg.value = value
        cfg.updated_by = updated_by
    await db.flush()
    _cached_model = model
    return model
