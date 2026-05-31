"""V2 课程内容 AI 生成 service（D-079 / M2）。

调 DeepSeek（OpenAI 兼容协议）生成单个单元的完整结构化内容。
dev 模式（DEEPSEEK_API_KEY 以 sk-placeholder 开头）返回 mock 数据，
让 persist + 前端流程在无 API key 时可完整跑通。
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.curriculum import AIGeneratedUnit

_SYSTEM_PROMPT = (
    "你是资深英语教材编辑，擅长按教材大纲为每个单元拆解知识点并生成教学解读。"
    "请严格按 JSON 格式输出，不要任何 markdown 代码块或额外文字。"
)

_USER_PROMPT_TEMPLATE = """请为以下教材单元生成完整教学内容。

教材：{textbook_version}
年级：{grade}
学期：{semester}
单元号：{unit_no}

要求：
1. 推断该单元的标题（unit_title），符合该教材实际编排
2. 列出 5-10 个核心知识点（grammar/vocabulary/reading/writing/listening 任一类）
3. 每个知识点提供 4 维度教学内容（listening/dictation/grammar/writing）markdown
4. 列出 10-20 个核心单词
5. code 字段格式：'yl-g{grade_short}s{sem_short}-u{unit_no}-kp{idx}'，必须全局唯一

返回纯 JSON（不要 markdown）：
{{
  "textbook_version": "{textbook_version}",
  "grade": "{grade}",
  "semester": "{semester}",
  "unit_no": {unit_no},
  "unit_title": "...",
  "knowledge_points": [
    {{
      "code": "yl-g5s1-u1-kp1",
      "name": "一般现在时第三人称单数",
      "category": "grammar",
      "description": "...",
      "contents": {{
        "listening": "## 听力要点\\n...",
        "dictation": "## 听写训练\\n...",
        "grammar": "## 语法解析\\n...",
        "writing": "## 写作应用\\n..."
      }}
    }}
  ],
  "words": [
    {{
      "word": "apple",
      "phonetic": "/ˈæpəl/",
      "definitions": [{{"pos": "n.", "meaning": "苹果"}}],
      "examples": ["I eat an apple every day."],
      "difficulty": 1,
      "is_core": true
    }}
  ]
}}"""


def _is_deepseek_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


def _make_mock_unit(
    textbook_version: str, grade: str, semester: str, unit_no: int
) -> AIGeneratedUnit:
    """dev mock：生成结构合法但内容是占位文本的单元。"""
    grade_short = "5" if "5" in grade else "7"
    sem_short = "1" if semester == "上" else "2"
    prefix = f"yl-g{grade_short}s{sem_short}-u{unit_no}"

    return AIGeneratedUnit(
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,  # type: ignore[arg-type]
        unit_no=unit_no,
        unit_title=f"Unit {unit_no} Mock Title ({grade}{semester})",
        knowledge_points=[
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp1",
                "name": f"知识点 {unit_no}-1（mock 语法）",
                "category": "grammar",
                "description": "占位描述：dev mock 数据",
                "contents": {
                    "listening": f"## 听力要点（U{unit_no}-KP1）\n这是 mock 听力解读。",
                    "dictation": f"## 听写训练（U{unit_no}-KP1）\n这是 mock 听写要点。",
                    "grammar": f"## 语法解析（U{unit_no}-KP1）\n这是 mock 语法讲解。",
                    "writing": f"## 写作应用（U{unit_no}-KP1）\n这是 mock 写作举例。",
                },
            },
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp2",
                "name": f"知识点 {unit_no}-2（mock 词汇）",
                "category": "vocabulary",
                "description": "占位描述",
                "contents": {
                    "listening": "## 听力\nmock",
                    "dictation": "## 听写\nmock",
                    "grammar": "## 语法\nmock",
                    "writing": "## 写作\nmock",
                },
            },
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp3",
                "name": f"知识点 {unit_no}-3（mock 阅读）",
                "category": "reading",
                "description": "占位描述",
                "contents": {
                    "listening": "## 听力\nmock",
                    "dictation": "## 听写\nmock",
                    "grammar": "## 语法\nmock",
                    "writing": "## 写作\nmock",
                },
            },
        ],
        words=[
            {  # type: ignore[list-item]
                "word": f"word{unit_no}_{i}",
                "phonetic": None,
                "definitions": [{"pos": "n.", "meaning": f"mock 释义{i}"}],
                "examples": [f"Mock example {i}."],
                "difficulty": 1,
                "is_core": True,
            }
            for i in range(1, 6)
        ],
    )


async def generate_unit(
    *,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
) -> AIGeneratedUnit:
    """生成 1 个单元的完整结构化内容。dev mock 或真实 DeepSeek 调用。"""
    if _is_deepseek_dev_mode():
        return _make_mock_unit(textbook_version, grade, semester, unit_no)

    grade_short = "5" if "5" in grade else "7"
    sem_short = "1" if semester == "上" else "2"
    prompt = _USER_PROMPT_TEMPLATE.format(
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
        unit_no=unit_no,
        grade_short=grade_short,
        sem_short=sem_short,
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
        raise AppError(code=502, message=f"AI 课程生成失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    # DeepSeek sometimes wraps JSON in markdown fences despite the "no markdown" instruction.
    # Strip them if present so JSON parse succeeds.
    if raw.startswith("```"):
        # Drop the opening fence line and trailing closing fence
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI 课程生成返回格式异常") from exc

    try:
        return AIGeneratedUnit(**data)
    except Exception as exc:
        raise AppError(code=500, message="AI 课程生成返回格式异常") from exc
