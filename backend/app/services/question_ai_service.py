"""V2 仿真题 AI 生成 service（D-079 / M3a）。

调 DeepSeek 为某个知识点生成 N 道题（单选/填空/判断 3 类混合）。
dev mode 返回固定结构供前端/集成测试无 key 时跑通。
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.questions import AIGeneratedQuestion

_SYSTEM_PROMPT = (
    "你是中国中小学英语命题老师，按知识点出仿真题。题型在单选/填空/判断三类中分配。"
    "严格按 JSON 数组输出，不要任何 markdown 代码块或额外文字。"
)

_USER_PROMPT_TEMPLATE = """请为以下知识点生成 {count} 道仿真题。

知识点名称：{kp_name}
分类：{kp_category}
描述：{kp_description}

题型分配（{count} 道）：
- 单选 ≥ 2 道：4 个选项，标记 A-D，answer 是单个字母
- 填空 ≥ 1 道：options 为 null，answer 可用 | 分隔多个合法答案（如 "goes|go"）
- 判断 ≥ 1 道：options 为 null，answer 是 "对" 或 "错"

每题必须含 explanation（≥ 20 字解析）和 difficulty（1-5）。

返回纯 JSON 数组（不要 markdown）：
[
  {{
    "question_type": "单选",
    "stem": "题干...",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "B",
    "explanation": "...",
    "difficulty": 2
  }},
  {{
    "question_type": "填空",
    "stem": "He ___ to school every day.",
    "options": null,
    "answer": "goes",
    "explanation": "...",
    "difficulty": 2
  }},
  {{
    "question_type": "判断",
    "stem": "There be 句型只能用于现在时。",
    "options": null,
    "answer": "错",
    "explanation": "...",
    "difficulty": 1
  }}
]"""


def _is_deepseek_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


def _make_mock_questions(kp_name: str, count: int) -> list[AIGeneratedQuestion]:
    """dev mock：固定 5 题（2 单选 + 2 填空 + 1 判断）。"""
    base = [
        AIGeneratedQuestion(
            question_type="单选",
            stem=f"Mock 单选题 1 about {kp_name}.",
            options=["A. mock1", "B. mock2", "C. mock3", "D. mock4"],
            answer="B",
            explanation="Mock 解析：答案是 B 因为...",
            difficulty=2,
        ),
        AIGeneratedQuestion(
            question_type="单选",
            stem=f"Mock 单选题 2 about {kp_name}.",
            options=["A. opt1", "B. opt2", "C. opt3", "D. opt4"],
            answer="A",
            explanation="Mock 解析：选 A 是因为...",
            difficulty=3,
        ),
        AIGeneratedQuestion(
            question_type="填空",
            stem=f"Mock 填空题 1 about {kp_name}: He ___ play.",
            options=None,
            answer="can|may",
            explanation="Mock 解析：can 和 may 都接受。",
            difficulty=2,
        ),
        AIGeneratedQuestion(
            question_type="填空",
            stem=f"Mock 填空题 2 about {kp_name}: She ___ home.",
            options=None,
            answer="went",
            explanation="Mock 解析：went 是 go 的过去式。",
            difficulty=3,
        ),
        AIGeneratedQuestion(
            question_type="判断",
            stem=f"Mock 判断题 about {kp_name}: This rule applies always.",
            options=None,
            answer="错",
            explanation="Mock 解析：并非总是适用。",
            difficulty=1,
        ),
    ]
    return [base[i % len(base)] for i in range(count)]


async def generate_questions(
    *,
    kp_name: str,
    kp_category: str,
    kp_description: str | None,
    count: int = 5,
) -> list[AIGeneratedQuestion]:
    """为 1 个 KP 生成 count 道仿真题。"""
    if _is_deepseek_dev_mode():
        return _make_mock_questions(kp_name, count)

    prompt = _USER_PROMPT_TEMPLATE.format(
        count=count,
        kp_name=kp_name,
        kp_category=kp_category,
        kp_description=kp_description or "(无)",
    )

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=4096,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI 生题失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="AI 生题返回格式异常")

    try:
        return [AIGeneratedQuestion(**item) for item in data]
    except Exception as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc
