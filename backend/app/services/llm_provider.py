"""LLM 提供方抽象：集中管理 api_key / base_url / model 与 dev-mock 检测。

所有需要调用大模型的 service 都经由这里，而不是各自构造 AsyncOpenAI client。
好处：换 LLM 厂商（DeepSeek → 通义 / Moonshot / OpenAI 等，凡 OpenAI 兼容协议）
只需改 .env 的 LLM_BASE_URL / LLM_MODEL / DEEPSEEK_API_KEY 三项，业务 service 零改动。

dev-mock：api_key 以 'sk-placeholder' 开头时，is_llm_dev_mode() 返回 True，
各 service 据此走本地确定性 mock，无需真实账号即可跑通整条链路与测试。
"""
from __future__ import annotations

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.core.config import settings


def is_llm_dev_mode() -> bool:
    """api_key 以 'sk-placeholder' 开头 → 进入 dev-mock，无需真实账号。"""
    return settings.deepseek_api_key.startswith("sk-placeholder")


def get_llm_client() -> AsyncOpenAI:
    """按配置构造 LLM client（OpenAI 兼容协议）。"""
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.llm_base_url,
    )


async def chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    response_format: dict | None = None,
    temperature: float | None = None,
) -> ChatCompletion:
    """统一的单轮 chat 调用：system + user 两条消息，返回原始 ChatCompletion。

    调用方负责解析 response.choices[0].message.content 与 response.usage，
    并自行用 try/except 包装本调用以抛出各自语义的 AppError。

    Args:
        system_prompt: 系统提示词。
        user_prompt: 用户提示词。
        max_tokens: 最大生成 token 数。
        response_format: 可选，如 {"type": "json_object"} 强制 JSON 输出。
    """
    from app.services import llm_config_service
    client = get_llm_client()
    kwargs: dict = {
        "model": llm_config_service.active_model(),   # 后台「模型配置」页可改;缓存优先
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if temperature is not None:
        kwargs["temperature"] = temperature
    return await client.chat.completions.create(**kwargs)
