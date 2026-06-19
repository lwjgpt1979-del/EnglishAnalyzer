"""整卷拆题：将整卷 OCR 原始文字（印刷体 + 手写体）送入 DeepSeek，拆分为多道结构化题目。

输入：OcrResult（印刷体 = 题目，手写体 = 学生作答）
输出：list[ParsedPaperQuestion]，每题含 question_no / question_type / stem /
      student_answer / correct_answer / explanation。

Dev 模式（deepseek_api_key 以 'sk-placeholder' 开头）跳过真实 API，确定性返回 2 题，
让整条链路在无账号时可完整测试。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.exceptions import AppError
from app.services.llm_provider import chat_completion, is_llm_dev_mode
from app.services.ocr_service import OcrResult

# 与 ai_question_type_enum 对齐
_VALID_TYPES = {"单选", "填空", "完型", "阅读", "写作", "判断", "连线"}


@dataclass
class ParsedPaperQuestion:
    """DeepSeek 从整卷 OCR 文字拆出的单题结构化字段。"""
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None


_SYSTEM_PROMPT = (
    "你是一个专业的英语试卷结构化助手。"
    "你会收到一整张英语试卷的 OCR 识别文字（印刷体为题目，手写体为学生作答），"
    "请把整卷拆分为一道道独立的题目，严格按 JSON 数组输出，不要任何额外文字。"
)

_USER_PROMPT_TEMPLATE = """以下是从一整张英语试卷图片中识别到的文字：

【印刷体识别（题目印刷文字，含题号/题干/选项）】
{printed_text}

【手写体识别（学生作答内容，通常是题号 + 答案）】
{handwritten_text}

请把整卷拆分为多道题目，返回纯 JSON 数组（不要任何 markdown 代码块或额外文字）。
数组每一项格式：
{{
  "question_no": "题号（如 27），无法识别则 null",
  "question_type": "单选|填空|完型|阅读|写作|判断|连线",
  "stem": "该题完整题干（含选项，不含学生作答）",
  "student_answer": "该题学生手写答案（按题号从手写体匹配，无法识别则 null）",
  "correct_answer": "正确答案（可推断则填，否则 null）",
  "explanation": "简要解析（可推断则填，否则 null）"
}}

要求：按题号顺序输出；识别不到任何题目时返回空数组 []。"""


def _normalize_type(raw: object) -> str:
    """归一化题型到 ai_question_type_enum 合法值，非法值兜底为 单选。"""
    return raw if raw in _VALID_TYPES else "单选"


# ─── 确定性结构拆题（文字版 docx/PDF）──────────────────────────────────────────
# 文字版试卷文本已干净，无需过大模型「重写」（会臆造答案、错判题型、丢题/重排）。
# 这里按卷面结构如实切：大题标题定题型 → 题号在大题内切题（题号按卷面循环）→
# 题干/选项逐字保留 → 完形/阅读短文挂到题组 → 嵌入空（信息还原/选词填空）按下划线
# 题号合成 → 答案一律留空（原卷无答案）。

_SECTION_RE = re.compile(r"^[一二三四五六七八九十]+、")
_QNUM_RE = re.compile(r"^\s*(\d{1,2})(?:[.、．)]|\s)")
_BLANK_NUM_RE = re.compile(r"_{2,}\s*(\d{1,2})\s*_{2,}")
_OPTION_RE = re.compile(r"^[A-GＡ-Ｇ]\s*[.、．)]")
_CIRCLE_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]")
_GROUP_BREAK_RE = re.compile(r"^第[一二三四五六七八九十]+[节部]")
_INSTRUCTION_HINTS = (
    "答题卡", "满分", "选出最佳", "请认真", "请先通读", "将所译", "根据下列",
    "从方框中", "从短文后", "写在答题卡", "每小题", "每空", "仅用一次", "听两遍",
    "选择适当", "第一部分", "第二部分", "第一节", "第二节", "将下列句子译成英语",
)


def _is_instruction(s: str) -> bool:
    return any(h in s for h in _INSTRUCTION_HINTS)


def _is_option_like(s: str) -> bool:
    if _OPTION_RE.match(s) or _CIRCLE_RE.match(s) or s.startswith("—"):
        return True
    head = s.split("\t", 1)[0].strip() if "\t" in s else ""
    return bool(head and _OPTION_RE.match(head))


def _classify_kw(blob: str) -> str | None:
    if "完形" in blob or "完型" in blob:
        return "完型"
    if "单项" in blob or "听力" in blob:
        return "单选"
    if "完成句子" in blob:
        return "填空"
    if "拼写" in blob or "单词" in blob:
        return "填空"
    if "书面表达" in blob or "作文" in blob:
        return "写作"
    if "信息还原" in blob or "阅读" in blob:  # 阅读理解 / 阅读表达 / 信息还原
        return "阅读"
    return None


def _section_type(header: str, lines: list[str]) -> str:
    """优先用大题标题判题型；标题无关键词（如「八、（满分6分）」）再补扫前几行正文。"""
    if t := _classify_kw(header):
        return t
    blob = header
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _QNUM_RE.match(s):
            break
        blob += " " + s
        if t := _classify_kw(blob):
            return t
    return "单选"


def _split_one_section(qtype: str, lines: list[str], sec_text: str,
                       out: list[ParsedPaperQuestion]) -> None:
    cur_passage: list[str] = []
    mode = "passage"          # 'passage' | 'questions'
    cur_q: dict | None = None
    last_no = 0
    loose: list[str] = []     # 未挂到题号的选项框（信息还原 A-G / 选词框）
    questions: list[dict] = []

    def flush_q() -> None:
        nonlocal cur_q
        if cur_q:
            questions.append(cur_q)
            cur_q = None

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _GROUP_BREAK_RE.match(s):     # 第一节/第二节 → 断开上一题组并重置短文
            flush_q()
            cur_passage, mode = [], "passage"
            continue
        if _is_instruction(s):
            continue
        m = _QNUM_RE.match(s)
        if m and int(m.group(1)) > last_no:          # 新题号（大题内单调递增）
            flush_q()
            last_no = int(m.group(1))
            cur_q = {"no": m.group(1), "stem": [s],
                     "passage": "\n".join(cur_passage).strip(), "has_opt": False}
            mode = "questions"
        elif _is_option_like(s) or ("____" in s and cur_q is not None):
            if cur_q is not None:                    # 选项 / 完成句子下划线模板 → 并入本题
                cur_q["stem"].append(s)
                if _is_option_like(s):
                    cur_q["has_opt"] = True
            else:
                loose.append(s)
            mode = "questions"
        elif cur_q is not None and not cur_q["has_opt"]:
            cur_q["stem"].append(s)                  # 选项前的嵌入材料（如 Noticeboard 阅读框）
        elif mode == "questions":
            flush_q()                                # 题组已完，散文 = 下一题组短文
            cur_passage, mode = [s], "passage"
        else:
            cur_passage.append(s)
    flush_q()

    # 嵌入空题（信息还原 ____33____ / 选词填空 ____43____）：无独立题号行，按下划线题号合成
    blank_nums = sorted({int(x) for x in _BLANK_NUM_RE.findall(sec_text)})
    existing = {int(q["no"]) for q in questions}
    missing = [n for n in blank_nums if n not in existing]
    bank = "\n".join(loose).strip()
    embed_passage = "\n".join(cur_passage).strip()

    rows: list[tuple[int, str]] = []
    for q in questions:
        stem = (q["passage"] + "\n\n" if q["passage"] else "") + "\n".join(q["stem"])
        rows.append((int(q["no"]), stem.strip()))
    for n in missing:
        stem = "\n".join(p for p in (embed_passage, bank) if p).strip()
        rows.append((n, stem))

    rows.sort(key=lambda r: r[0])
    for no, stem in rows:
        if stem:
            out.append(ParsedPaperQuestion(
                question_no=str(no), question_type=qtype, stem=stem,
                student_answer=None, correct_answer=None, explanation=None,
            ))


def split_paper_text_structural(text: str) -> list[ParsedPaperQuestion]:
    """文字版试卷 → 确定性结构拆题。识别不到大题/题号时返回 []（由调用方决定兜底）。"""
    lines = (text or "").splitlines()
    sections: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if _SECTION_RE.match(ln.strip()):
            if cur:
                sections.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        sections.append(cur)

    out: list[ParsedPaperQuestion] = []
    for sec in sections:
        header = sec[0].strip()
        if not _SECTION_RE.match(header):
            continue  # 卷首标题段
        qtype = _section_type(header, sec[1:])
        _split_one_section(qtype, sec[1:], "\n".join(sec), out)
    return out


def _dev_mock_split(ocr: OcrResult) -> list[ParsedPaperQuestion]:
    """dev 模式确定性拆题：识别 _MOCK_PRINTED 里的两道题。

    OCR mock 文字结构固定（题号 27/28，每题题干一行 + 选项一行），
    手写体为 '27. B\\n28. B'。这里做轻量行解析，保证测试确定性，
    无需真实 DeepSeek。OCR 全空时返回 []。
    """
    if not (ocr.printed_text or "").strip():
        return []

    # 解析手写体答案：'27. B' -> {'27': 'B'}
    answers: dict[str, str] = {}
    for line in (ocr.handwritten_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # 形如 '27. B' 或 '27 B'
        parts = line.replace(".", " ").split()
        if len(parts) >= 2 and parts[0].isdigit():
            answers[parts[0]] = parts[1]

    # 解析印刷体题目：题号行开启一题，后续非题号行并入题干
    questions: list[ParsedPaperQuestion] = []
    cur_no: str | None = None
    cur_lines: list[str] = []

    def _flush() -> None:
        if cur_no is None:
            return
        stem = "\n".join(cur_lines).strip() or None
        questions.append(
            ParsedPaperQuestion(
                question_no=cur_no,
                question_type="单选",
                stem=stem,
                student_answer=answers.get(cur_no),
                correct_answer=None,
                explanation=None,
            )
        )

    for line in ocr.printed_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        head = stripped.split(".", 1)[0]
        if head.isdigit():
            _flush()
            cur_no = head
            rest = stripped.split(".", 1)[1].strip() if "." in stripped else ""
            cur_lines = [rest] if rest else []
        else:
            cur_lines.append(stripped)
    _flush()
    return questions


def _try_parse_doubao_json(text: str) -> list[ParsedPaperQuestion] | None:
    """尝试把豆包直出的 JSON 数组解析为 ParsedPaperQuestion 列表（M40）。

    豆包 Vision 直接返回结构化 JSON，printed_text 即为完整 JSON 字符串，
    handwritten_text 为空。若解析成功返回列表；否则返回 None 降级到传统流程。
    """
    text = text.strip()
    if not text.startswith("["):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    result: list[ParsedPaperQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        result.append(
            ParsedPaperQuestion(
                question_no=item.get("question_no"),
                question_type=_normalize_type(item.get("question_type")),
                stem=item.get("stem"),
                student_answer=item.get("student_answer"),
                correct_answer=item.get("correct_answer"),
                explanation=item.get("explanation"),
            )
        )
    return result if result else None


async def split_paper_questions(ocr: OcrResult) -> list[ParsedPaperQuestion]:
    """将整卷 OCR 文字拆分为多道结构化题目。

    M40 新增：若 printed_text 是豆包直出的 JSON 数组，直接解析（跳过 DeepSeek 拆题）。
    Dev 模式：确定性本地拆题，无需 API。
    Prod 模式（传统OCR）：DeepSeek 拆题，返回 JSON 数组。

    异常处理：
    - API 错误 → AppError(502, "整卷拆题服务暂时不可用")
    - JSON 解析失败 / 非数组 → AppError(500, "整卷拆题返回格式异常")
    """
    # M40: 豆包直出 JSON — 优先尝试直接解析，跳过 DeepSeek 拆题步骤
    if ocr.handwritten_text == "" and (ocr.printed_text or "").strip().startswith("["):
        parsed = _try_parse_doubao_json(ocr.printed_text or "")
        if parsed is not None:
            return parsed

    if is_llm_dev_mode():
        return _dev_mock_split(ocr)

    if not (ocr.printed_text or "").strip():
        return []

    prompt = _USER_PROMPT_TEMPLATE.format(
        printed_text=ocr.printed_text or "(无印刷体识别结果)",
        handwritten_text=ocr.handwritten_text or "(无手写体识别结果)",
    )

    try:
        # 整卷可能含多道题，需较大输出预算（与课程/生题 service 对齐为 8192）
        response = await chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=8192,
        )
    except Exception as exc:
        raise AppError(code=502, message=f"整卷拆题服务暂时不可用（{exc}）") from exc

    raw_text = (response.choices[0].message.content or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[-2] if raw_text.count("```") >= 2 else raw_text
        raw_text = raw_text.lstrip("json").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="整卷拆题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="整卷拆题返回格式异常")

    result: list[ParsedPaperQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        result.append(
            ParsedPaperQuestion(
                question_no=item.get("question_no"),
                question_type=_normalize_type(item.get("question_type")),
                stem=item.get("stem"),
                student_answer=item.get("student_answer"),
                correct_answer=item.get("correct_answer"),
                explanation=item.get("explanation"),
            )
        )
    return result
