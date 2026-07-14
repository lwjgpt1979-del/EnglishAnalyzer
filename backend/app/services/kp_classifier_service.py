"""知识点归类服务（M40）。

接收拆题结果（list[ParsedPaperQuestion]），调用 DeepSeek 文本模型
批量归类每题所属知识点，返回 {题号: kp_key} 映射。

Dev 模式复用 is_llm_dev_mode()，返回固定 mock 映射，无需真实 API。
"""
from __future__ import annotations

import json
import logging

from app.core.exceptions import AppError
from app.services.llm_provider import chat_completion, is_llm_dev_mode, fast_model
from app.services.paper_split_service import ParsedPaperQuestion

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是一个专业的英语教学知识点分类助手。"
    "你会收到一组英语题目，请为每题归类其考查的核心英语知识点（中文），"
    "严格按 JSON 对象输出，不要任何额外文字。"
)

_USER_PROMPT_TEMPLATE = """以下是一组英语题目，请为每题归类其核心知识点。

{questions_text}

请返回纯 JSON 对象（题号 → 知识点名称），例如：
{{"27": "一般现在时", "28": "过去完成时", "29": "定语从句"}}

要求：
- 知识点用中文，尽量精确（如"过去完成时"优于"时态"）
- 一题只选最核心的一个知识点
- 只返回 JSON，不要任何 markdown 或额外文字"""

# dev mock：与 _MOCK_PRINTED 里的两道题对应
_DEV_MOCK_RESULT = {
    "27": "动词短语辨析",
    "28": "过去完成时",
}


async def classify_kps(
    questions: list[ParsedPaperQuestion],
) -> dict[str, str]:
    """批量归类知识点，返回 {题号: kp_key}。

    Dev 模式返回固定 mock；题目列表为空直接返回 {}。
    """
    if not questions:
        return {}

    if is_llm_dev_mode():
        # dev mock：为每题返回固定知识点（题号→知识点）
        result: dict[str, str] = {}
        for i, q in enumerate(questions):
            qno = q.question_no or str(i + 1)
            result[qno] = _DEV_MOCK_RESULT.get(qno, "英语综合")
        return result

    # 按小题内容 md5 缓存归类:独立题按题干、阅读/完形题按 短文+题干(带上下文);
    # 命中缓存的题不再送 LLM(跨上传/跨学生复用,重叠题不重复归类)。
    q_md5: dict[str, str] = {}     # qno → content_md5
    for i, q in enumerate(questions):
        qno = q.question_no or str(i + 1)
        q_md5[qno] = _content_md5(q)
    cached = await _classify_cache_get(list({m for m in q_md5.values() if m}))
    result = {}
    misses = []
    for i, q in enumerate(questions):
        qno = q.question_no or str(i + 1)
        m = q_md5[qno]
        if m and m in cached:
            result[qno] = cached[m]
        else:
            misses.append((qno, q))
    if not misses:                 # 全命中缓存 → 不调 LLM
        return result

    # 只对未命中的题构造描述文字（只传题干，不传图片，节省 token）
    lines = []
    for qno, q in misses:
        stem = (q.stem or "").strip()[:200]  # 截断超长题干
        lines.append(f"题{qno}：{stem}")
    questions_text = "\n".join(lines)

    prompt = _USER_PROMPT_TEMPLATE.format(questions_text=questions_text)

    try:
        response = await chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            model=fast_model(),          # 归类=题干→知识点映射抽取,快档即可
            disable_thinking=True,       # 关思考:开思考会烧光 token 致 JSON 截断→归类失败拖垮整卷
            max_tokens=2048,             # 整卷多题,给足预算防截断
            feature="kp_classify",
        )
    except Exception as exc:
        _log.error("KP classify failed: %s", exc)
        raise AppError(code=502, message=f"知识点归类服务暂时不可用（{exc}）") from exc

    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[-2] if raw.count("```") >= 2 else raw
        raw = raw.lstrip("json").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="知识点归类返回格式异常") from exc

    if not isinstance(data, dict):
        raise AppError(code=500, message="知识点归类返回格式异常")

    new = {str(k): str(v) for k, v in data.items() if v}
    # 合并新归类 + 回写缓存(同题下次不再归类)
    for qno, q in misses:
        kp = new.get(qno)
        if kp:
            result[qno] = kp
            m = q_md5.get(qno)
            if m:
                await _classify_cache_put(m, kp)
    return result


def _content_md5(q) -> str | None:
    """小题内容指纹:阅读/完形(有 passage)带上短文上下文,独立题只按题干。归一化后 md5。"""
    import hashlib
    ctx = (getattr(q, "passage", None) or "")[:400] + "|" + (q.stem or "")
    norm = "".join(c.lower() for c in ctx if c.isalnum())
    return hashlib.md5(norm.encode()).hexdigest() if norm else None


async def _classify_cache_get(md5s: list[str]) -> dict[str, str]:
    if not md5s:
        return {}
    from app.core.database import async_session_factory
    from app.models.d13_v2_user_papers import KpClassifyCache
    from sqlalchemy import select
    try:
        async with async_session_factory() as db:
            rows = (await db.execute(select(KpClassifyCache.content_md5, KpClassifyCache.kp_key)
                                     .where(KpClassifyCache.content_md5.in_(md5s)))).all()
            return {m: k for m, k in rows}
    except Exception:  # noqa: BLE001
        return {}


async def _classify_cache_put(md5: str, kp_key: str) -> None:
    from app.core.database import async_session_factory
    from app.models.d13_v2_user_papers import KpClassifyCache
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    try:
        async with async_session_factory() as db:
            await db.execute(pg_insert(KpClassifyCache)
                             .values(content_md5=md5, kp_key=kp_key[:120])
                             .on_conflict_do_nothing(index_elements=["content_md5"]))
            await db.commit()
    except Exception:  # noqa: BLE001
        pass
