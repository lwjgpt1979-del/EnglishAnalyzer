"""LLM 提供方抽象：集中管理 api_key / base_url / model 与 dev-mock 检测。

所有需要调用大模型的 service 都经由这里，而不是各自构造 AsyncOpenAI client。
好处：换 LLM 厂商（DeepSeek → 通义 / Moonshot / OpenAI 等，凡 OpenAI 兼容协议）
只需改 .env 的 LLM_BASE_URL / LLM_MODEL / DEEPSEEK_API_KEY 三项，业务 service 零改动。

dev-mock：api_key 以 'sk-placeholder' 开头时，is_llm_dev_mode() 返回 True，
各 service 据此走本地确定性 mock，无需真实账号即可跑通整条链路与测试。
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.core.config import settings

_log = logging.getLogger(__name__)


def is_llm_dev_mode() -> bool:
    """api_key 以 'sk-placeholder' 开头 → 进入 dev-mock，无需真实账号。"""
    return settings.deepseek_api_key.startswith("sk-placeholder")


def get_llm_client() -> AsyncOpenAI:
    """按配置构造 LLM client（OpenAI 兼容协议）。"""
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.llm_base_url,
    )


def fast_model() -> str:
    """非推理「快/省」档模型名:抽取/打分等规格明确、无需重推理的任务用之。"""
    return settings.llm_model_fast or settings.llm_model


async def list_models() -> list[str]:
    """厂商当前可用模型 id 列表(GET /models)。dev-mock 或查询失败→返回 [](调用方按"无法确定"处理)。"""
    if is_llm_dev_mode():
        return []
    try:
        resp = await get_llm_client().models.list()
        return [m.id for m in resp.data]
    except Exception as exc:  # noqa: BLE001
        _log.warning("list_models failed: %s", exc)
        return []


async def chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    response_format: dict | None = None,
    temperature: float | None = None,
    model: str | None = None,
    feature: str = "other",
    disable_thinking: bool = False,
) -> ChatCompletion:
    """统一的单轮 chat 调用：system + user 两条消息，返回原始 ChatCompletion。

    调用方负责解析 response.choices[0].message.content 与 response.usage，
    并自行用 try/except 包装本调用以抛出各自语义的 AppError。

    Args:
        system_prompt: 系统提示词。
        user_prompt: 用户提示词。
        max_tokens: 最大生成 token 数。
        response_format: 可选，如 {"type": "json_object"} 强制 JSON 输出。
        disable_thinking: 关闭推理(v4 系是推理模型;简单任务关思考可从 ~15s 降到 ~1s)。
    """
    from app.services import llm_config_service
    client = get_llm_client()
    kwargs: dict = {
        "model": model or llm_config_service.active_model(),   # 显式 model 优先;否则后台配置主模型
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
    if disable_thinking:   # 关推理:抽取/改写等规格明确、无需重推理的任务提速用
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    resp = await client.chat.completions.create(**kwargs)
    try:    # 记用量台账 + 累加预算(失败不影响主调用)
        from app.services import usage_log_service
        u = resp.usage
        await usage_log_service.note(
            model=kwargs["model"], feature=feature,
            prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(u, "completion_tokens", 0) or 0,
            finish_reason=resp.choices[0].finish_reason if resp.choices else None)
    except Exception as exc:  # noqa: BLE001
        _log.warning("usage note skipped: %s", exc)
    return resp


async def complete_json(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    model: str | None = None,
    temperature: float | None = None,
    max_attempts: int = 2,
    escalate_ceiling: int | None = None,
    validate: Callable[[dict], bool] | None = None,
    feature: str = "other",
    disable_thinking: bool = False,
) -> dict | None:
    """带 finish_reason 感知的 JSON 调用,取代各处"盲目重试":
    - finish_reason=length(预算耗尽):盲重试必再失败。给了 escalate_ceiling 才把 max_tokens
      翻倍升一档(≤ceiling)重试一次;否则直接放弃(返回 None,调用方走模板兜底)。
    - stop 但 JSON 解析失败 / validate 不过:视为瞬时抖动,同参数重试一次。
    - 调用异常(网络/5xx):重试一次。
    全失败返回 None。"""
    cur = max_tokens
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await chat_completion(
                system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=cur,
                response_format={"type": "json_object"}, temperature=temperature, model=model,
                feature=feature, disable_thinking=disable_thinking)
            choice = resp.choices[0]
            if choice.finish_reason == "length":
                if escalate_ceiling and cur < escalate_ceiling:
                    cur = min(cur * 2, escalate_ceiling)
                    _log.warning("complete_json 截断(length),升档 max_tokens→%d 重试", cur)
                    continue
                _log.warning("complete_json 截断(length)且已达上限,放弃→走兜底")
                return None
            data = json.loads(choice.message.content or "{}")
            if validate is None or validate(data):
                return data
            _log.warning("complete_json 校验未过(finish=%s,第%d次),重试", choice.finish_reason, attempt)
        except Exception as exc:  # noqa: BLE001
            _log.warning("complete_json 第%d次调用异常: %s", attempt, exc)
    return None
