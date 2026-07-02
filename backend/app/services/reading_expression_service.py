"""阅读表达(简答/回答问题)AI 批改 service（P2a）。

给「短文 + 问题 + 参考答案 + 学生作答」判分:①内容要点是否命中(逐点标注);
②语言是否准确。独立批改,不走练习字符串判分流(_grade 对自由作答会误判)。
复用 LLM dev-mock:无 key 时确定性返回,离线可测。
"""
from __future__ import annotations

import json

from app.core.exceptions import AppError
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_SYSTEM_PROMPT = (
    "你是中小学英语「阅读表达/简答题」阅卷老师。请对照短文与参考答案,批改学生作答:"
    "①逐个内容要点判断是否命中(意思对即算命中,不苛求与参考答案字面一致);"
    "②评价语言准确性(语法/拼写/句子完整),并给出扣分。"
    "宽松合理、面向提分。只返回 JSON,键:"
    "points(list of {point,hit,comment})、content_score(int)、content_full(int)、"
    "language_comment(str)、language_deduction(int)、total(int)、full(int)、feedback(str)。"
)


def _empty_result(full_score: int) -> dict:
    return {"points": [], "content_score": 0, "content_full": full_score,
            "language_comment": "未作答", "language_deduction": 0,
            "total": 0, "full": full_score, "feedback": "未作答,请作答后再提交批改。"}


def _mock_result(*, reference_answer: str, student_answer: str, full_score: int) -> dict:
    """dev-mock:参考答案被作答包含 或 作答足够长 → 判要点命中(确定性,离线可测)。"""
    sa = student_answer.strip().lower()
    hit = bool(reference_answer.strip()) and (reference_answer.strip().lower() in sa or len(sa) >= 8)
    cs = full_score if hit else max(0, full_score - 2)
    return {
        "points": [{"point": (reference_answer or "要点")[:24], "hit": hit,
                    "comment": "dev-mock 判定"}],
        "content_score": cs, "content_full": full_score,
        "language_comment": "dev-mock:语言基本通顺", "language_deduction": 0,
        "total": cs, "full": full_score,
        "feedback": f"[dev-mock] 要点{'命中' if hit else '部分命中'};注意句子完整与时态。",
    }


async def grade_reading_expression(
    *, question: str, reference_answer: str, student_answer: str,
    passage: str | None = None, full_score: int = 4,
) -> dict:
    """批改一道阅读表达简答:返回逐要点命中 + 内容/语言得分 + 总分 + 反馈。"""
    sa = (student_answer or "").strip()
    if not sa:
        return _empty_result(full_score)
    if is_llm_dev_mode():
        return _mock_result(reference_answer=reference_answer, student_answer=sa,
                            full_score=full_score)
    prompt = (f"短文:\n{passage or '(无独立短文)'}\n\n问题:{question}\n\n"
              f"参考答案:{reference_answer}\n\n学生作答:{sa}\n\n满分:{full_score}")
    try:
        resp = await chat_completion(
            system_prompt=_SYSTEM_PROMPT, user_prompt=prompt, max_tokens=1024)
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用,请稍后重试（{exc}）") from exc
    try:
        return json.loads((resp.choices[0].message.content or "").strip())
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI阅读表达批改返回格式异常") from exc
