"""V2 课程内容 AI 生成 service（D-079 / M2）。

调 DeepSeek（OpenAI 兼容协议）生成单个单元的完整结构化内容。
dev 模式（DEEPSEEK_API_KEY 以 sk-placeholder 开头）返回 mock 数据，
让 persist + 前端流程在无 API key 时可完整跑通。
"""
from __future__ import annotations

import json

from app.core.exceptions import AppError
from app.schemas.curriculum import AIGeneratedUnit, AIUnitPassage
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_PASSAGE_SYS = (
    "你是译林版初中英语教材分析专家。从给定单元原文里**原样抽取**(不改写、不翻译、保留英文原文)"
    "听力、阅读、写作三类材料,**逐篇分开、尽量抽全本单元所有材料,不要遗漏、不要截断**。\n"
    "判别依据(按译林版编排):\n"
    "1) 听力(kind=听力):一切对话/独白脚本——包括「Welcome to the unit」「Greetings」里的问候对话、"
    "带说话人轮次的对话(如 Millie: … / Sandy: …)、Listening / Tapescript、Integrated skills 里的听力材料。"
    "这些都算听力,逐段抽出。\n"
    "2) 阅读(kind=阅读):「Reading」板块的短文,**整篇完整抽取不要截断**;若有多篇则分多条。\n"
    "3) 写作(kind=写作):「Writing」「Task」板块的题目要求与范文(要求/范文照原文)。\n"
    "找不到的类别就不返回。严格输出 JSON,不要解释。"
)


async def extract_unit_passages(unit_text: str) -> list[AIUnitPassage]:
    """从单元原文拆出 听力脚本/阅读短文(可多)/写作要求与范文。dev-mock 返回空。"""
    if not (unit_text or "").strip() or is_llm_dev_mode():
        return []
    user = (
        f"【单元原文】\n{unit_text[:16000]}\n\n"
        '请抽取。返回 JSON:{"passages":[{"kind":"听力|阅读|写作","title":"小标题(可空)","text":"原文"}]}。'
        "text 必须是原文片段、保持完整;同一类有多段就拆成多条(如多组对话、多篇阅读)。"
        "务必把单元里出现的所有对话(听力)都抽出来,别只抽阅读。"
    )
    try:
        resp = await chat_completion(system_prompt=_PASSAGE_SYS, user_prompt=user,
                                     max_tokens=8192, response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return []
    out: list[AIUnitPassage] = []
    for p in (data.get("passages") or []):
        try:
            ap = AIUnitPassage(**p)
        except Exception:  # noqa: BLE001
            continue
        if ap.text.strip():
            out.append(ap)
    return out

_SYSTEM_PROMPT = (
    "你是资深英语教材编辑，擅长按教材大纲为每个单元拆解知识点并生成教学解读。"
    "知识点 name 与 description 一律用中文命名（专有语法/术语可在括号内附英文，如"
    "「一般现在时（present simple）」）；禁止用纯英文作知识点名。"
    "请严格按 JSON 格式输出，不要任何 markdown 代码块或额外文字。"
)

_USER_PROMPT_TEMPLATE = """请为以下教材单元生成完整教学内容。

教材：{textbook_version}
年级：{grade}
学期：{semester}
单元号：{unit_no}

要求：
1. 推断该单元的标题（unit_title），符合该教材实际编排
2. 列出 5-8 个核心知识点（grammar/vocabulary/reading/writing/listening 任一类）；
   知识点 name 与 description **必须用中文**（专有术语可在括号内附英文），不得用纯英文
3. 每个知识点提供 6 维度教学内容（listening/vocabulary/grammar/reading/translation/writing）markdown，每个维度内容简明（2-4 句即可，避免冗长）
4. 列出 10-15 个核心单词
5. code 字段格式：'yl-g{grade_short}s{sem_short}-u{unit_no}-kp{{idx}}'，其中 {{idx}} 是 1 开始的知识点序号，必须全局唯一

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
        "vocabulary": "## 词汇讲解\\n...",
        "grammar": "## 语法解析\\n...",
        "reading": "## 阅读策略\\n...",
        "translation": "## 翻译技巧\\n...",
        "writing": "## 写作要点\\n..."
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
                    "vocabulary": f"## 词汇讲解（U{unit_no}-KP1）\n这是 mock 词汇讲解。",
                    "grammar": f"## 语法解析（U{unit_no}-KP1）\n这是 mock 语法讲解。",
                    "reading": f"## 阅读策略（U{unit_no}-KP1）\n这是 mock 阅读策略。",
                    "translation": f"## 翻译技巧（U{unit_no}-KP1）\n这是 mock 翻译技巧。",
                    "writing": f"## 写作要点（U{unit_no}-KP1）\n这是 mock 写作举例。",
                },
            },
            {  # type: ignore[list-item]
                "code": f"{prefix}-kp2",
                "name": f"知识点 {unit_no}-2（mock 词汇）",
                "category": "vocabulary",
                "description": "占位描述",
                "contents": {
                    "listening": "## 听力\nmock",
                    "vocabulary": "## 词汇\nmock",
                    "grammar": "## 语法\nmock",
                    "reading": "## 阅读\nmock",
                    "translation": "## 翻译\nmock",
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
                    "vocabulary": "## 词汇\nmock",
                    "grammar": "## 语法\nmock",
                    "reading": "## 阅读\nmock",
                    "translation": "## 翻译\nmock",
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
    if is_llm_dev_mode():
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
        response = await chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=8192,
            response_format={"type": "json_object"},
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
    import re as _re
    try:
        # strict=False 允许字符串内出现裸换行/制表符等控制字符
        # （DeepSeek 偶尔在 markdown 内容里直接输出真实换行而非 \\n）
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        # 修复 DeepSeek 偶尔输出的非法 \X 转义（如 \s \p \( 等），
        # 将其替换为合法的 \\X，使 JSON 解析器接受。
        fixed = _re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', raw)
        try:
            data = json.loads(fixed, strict=False)
        except json.JSONDecodeError as exc2:
            raise AppError(code=500, message="AI 课程生成返回格式异常") from exc2

    try:
        return AIGeneratedUnit(**data)
    except Exception as exc:
        raise AppError(code=500, message="AI 课程生成返回格式异常") from exc


# ─── PDF 上下文版本（M3）────────────────────────────────────────────────────────

_PDF_SYSTEM_PROMPT = (
    "你是资深英语教材编辑，擅长从教材原文中拆解知识点并生成结构化教学解读。"
    "用户将提供教材某单元的 PDF 原文，请据此提取本单元真实的核心知识点与词汇。"
    "知识点 name 与 description 一律用中文命名（即使原文是英文，也要用中文概括，"
    "专有术语可在括号内附英文，如「不同类型的房屋（types of houses）」）；禁止用纯英文作知识点名。"
    "请严格按 JSON 格式输出，不要任何 markdown 代码块或额外文字。"
)

_PDF_PROMPT_TEMPLATE = """\
请分析以下教材单元的 PDF 原文，提取本单元教学内容。

教材：{textbook_version}
年级：{grade}
学期：{semester}
单元号：{unit_no}
单元标题（如能识别）：{detected_title}

== 单元原文（pdfplumber 提取，可能含噪声）==
{unit_text}
== 原文结束 ==

要求：
1. 根据原文推断/确认 unit_title
2. 提取 5-8 个核心知识点（grammar/vocabulary/reading/writing/listening 任意类别）；
   知识点 name 与 description **必须用中文**（即使原文英文也用中文概括，专有术语可括号附英文），不得用纯英文
3. 每个知识点提供 6 维度教学内容（listening/vocabulary/grammar/reading/translation/writing）
4. 提取 10-15 个原文出现的核心词汇
5. code 格式：yl-g{grade_short}s{sem_short}-u{unit_no}-kpN（N 从 1 开始）

返回纯 JSON（不要 markdown）：
{{
  "textbook_version": "{textbook_version}",
  "grade": "{grade}",
  "semester": "{semester}",
  "unit_no": {unit_no},
  "unit_title": "...",
  "knowledge_points": [
    {{
      "code": "yl-g{grade_short}s{sem_short}-u{unit_no}-kp1",
      "name": "一般现在时描述日常活动",
      "category": "grammar",
      "description": "...",
      "contents": {{
        "listening": "## 听力要点\\n...",
        "vocabulary": "## 词汇讲解\\n...",
        "grammar": "## 语法解析\\n...",
        "reading": "## 阅读策略\\n...",
        "translation": "## 翻译技巧\\n...",
        "writing": "## 写作要点\\n..."
      }}
    }}
  ],
  "words": [
    {{
      "word": "example",
      "phonetic": "/ɪɡˈzɑːmpəl/",
      "definitions": [{{"pos": "n.", "meaning": "例子"}}],
      "examples": ["This is an example."],
      "difficulty": 2,
      "is_core": true
    }}
  ]
}}"""


# 轻量「骨架」版:只提取 考点名 + 词，**不生成六维讲解正文**。
# 上传批量阶段用它（输出 token 量约为完整版的 1/5，大幅提速）；
# 六维讲解延后/按需，由 generate_unit_content endpoint 用 source_text 单独补全。
_PDF_SKELETON_PROMPT_TEMPLATE = """\
请分析以下教材单元的 PDF 原文，提取本单元的**知识点骨架与核心词汇**（**不要生成任何讲解正文**）。

教材：{textbook_version}
年级：{grade}
学期：{semester}
单元号：{unit_no}
单元标题（如能识别）：{detected_title}

== 单元原文（pdfplumber 提取，可能含噪声）==
{unit_text}
== 原文结束 ==

要求：
1. 根据原文推断/确认 unit_title
2. 提取 5-8 个核心知识点（grammar/vocabulary/reading/writing/listening 任意类别）；
   知识点 name 与 description **必须用中文**（即使原文英文也用中文概括，专有术语可括号附英文），不得用纯英文；
   description 用一句话概括即可，**不要写六维讲解，不要 contents 字段**
3. 提取 10-15 个原文出现的核心词汇
4. code 格式：yl-g{grade_short}s{sem_short}-u{unit_no}-kpN（N 从 1 开始）

返回纯 JSON（不要 markdown）：
{{
  "textbook_version": "{textbook_version}",
  "grade": "{grade}",
  "semester": "{semester}",
  "unit_no": {unit_no},
  "unit_title": "...",
  "knowledge_points": [
    {{
      "code": "yl-g{grade_short}s{sem_short}-u{unit_no}-kp1",
      "name": "一般现在时描述日常活动",
      "category": "grammar",
      "description": "一句话概括"
    }}
  ],
  "words": [
    {{
      "word": "example",
      "phonetic": "/ɪɡˈzɑːmpəl/",
      "definitions": [{{"pos": "n.", "meaning": "例子"}}],
      "examples": ["This is an example."],
      "difficulty": 2,
      "is_core": true
    }}
  ]
}}"""


def _strip_and_fix_json(raw: str) -> dict:
    """去掉 markdown fence 并修复非法转义，返回解析后的 dict。"""
    import re as _re
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        fixed = _re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', raw)
        return json.loads(fixed, strict=False)


async def generate_unit_from_text(
    *,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
    unit_text: str,
    detected_title: str | None = None,
    with_contents: bool = True,
) -> AIGeneratedUnit:
    """从 PDF 提取的单元原文生成结构化课程内容（M3）。

    with_contents=True ：完整版，每个考点带六维讲解（按需/单元级生成用）。
    with_contents=False：骨架版，只出考点名 + 词，**不生成六维讲解**——
        上传批量阶段用，输出 token 量约 1/5，大幅提速；六维讲解延后按需补。
    """
    if is_llm_dev_mode():
        return _make_mock_unit(textbook_version, grade, semester, unit_no)

    grade_short = "5" if "5" in grade else "7"
    sem_short = "1" if semester == "上" else "2"

    # 限制原文长度，避免超 token（约保留前 6000 字符）
    text_truncated = unit_text[:6000] if len(unit_text) > 6000 else unit_text

    template = _PDF_PROMPT_TEMPLATE if with_contents else _PDF_SKELETON_PROMPT_TEMPLATE
    prompt = template.format(
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
        unit_no=unit_no,
        detected_title=detected_title or "（待识别）",
        unit_text=text_truncated,
        grade_short=grade_short,
        sem_short=sem_short,
    )

    try:
        response = await chat_completion(
            system_prompt=_PDF_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=8192 if with_contents else 3000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI PDF 课程生成失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    try:
        data = _strip_and_fix_json(raw)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI PDF 课程生成返回格式异常") from exc

    try:
        return AIGeneratedUnit(**data)
    except Exception as exc:
        raise AppError(code=500, message="AI PDF 课程生成返回格式异常") from exc
