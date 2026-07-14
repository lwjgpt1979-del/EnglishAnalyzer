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
from app.services.llm_provider import chat_completion, is_llm_dev_mode, fast_model
from app.services.ocr_service import OcrResult

# 与 ai_question_type_enum 对齐
_VALID_TYPES = {"单选", "填空", "完型", "阅读", "写作", "判断", "连线"}


@dataclass
class ParsedPaperQuestion:
    """从整卷文字拆出的单题结构化字段。

    passage/block_key 用于「短文 + 多小问」题组(阅读/完形/信息还原):同一短文的小问
    共享同一 block_key,passage 为短文正文(仅在组内重复，导入时去重存一份 passage)。
    标准独立题(单选/完成句子/书面)passage 与 block_key 均为 None。
    """
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None
    passage: str | None = None
    block_key: str | None = None
    section: str | None = None     # 原卷大题名(听力选择/单项填空/完形填空…)


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

请把整卷拆分为多道题目。每道题格式：
{{
  "section": "该题所属大题名（如 听力理解/单项选择/完形填空/阅读理解/任务型阅读/词汇运用/首字母填空/短文填空/书面表达 等，忠实原卷大题标题；无法判断则 null）",
  "question_no": "题号（如 27），无法识别则 null",
  "question_type": "单选|填空|完型|阅读|写作|判断|连线",
  "stem": "该题完整题干（含选项，不含学生作答）",
  "block_key": "阅读理解/完形填空/任务型阅读 这类『一篇短文带多道小题』的小题，同一篇短文的小题都给同一个 key（如 readingA、readingB、cloze1）；独立小题（单选等）为 null",
  "student_answer": "该题学生手写答案（按题号从手写体匹配，无法识别则 null）",
  "correct_answer": "正确答案（可推断则填，否则 null）",
  "explanation": "简要解析（可推断则填，否则 null）"
}}

另外**单独**返回一个 passages 对象，键是 block_key，值是该短文/语篇的**完整原文（逐字照抄印刷体识别，不要改写、不要缩略）**：
{{ "readingA": "短文全文……", "cloze1": "完形填空的语篇全文……" }}

铁律：
- **只要识别文字里出现了阅读理解/完形填空/任务型阅读的短文正文，就必须把它完整放进 passages，并让对应小题的 block_key 指向它**——绝不能因为题干没重复短文就把短文丢掉。短文通常在这组小题的前面。
- 完形填空的语篇（带 1/2/3… 空的整段文章）也要作为 passage 放进 passages。
- 没有任何短文的卷子，passages 返回 {{}}。
- **务必按原卷大题给每题填 section**；同一大题下的题 section 相同；按题号顺序输出；识别不到任何题目时 questions 返回 []。"""


def _normalize_type(raw: object) -> str:
    """归一化题型到 ai_question_type_enum 合法值，非法值兜底为 单选。"""
    return raw if raw in _VALID_TYPES else "单选"


# ─── 确定性结构拆题（文字版 docx/PDF）──────────────────────────────────────────
# 文字版试卷文本已干净，无需过大模型「重写」（会臆造答案、错判题型、丢题/重排）。
# 这里按卷面结构如实切：大题标题定题型 → 题号在大题内切题（题号按卷面循环）→
# 题干/选项逐字保留 → 完形/阅读短文挂到题组 → 嵌入空（信息还原/选词填空）按下划线
# 题号合成 → 答案一律留空（原卷无答案）。

_SECTION_RE = re.compile(r"^[一二三四五六七八九十]+、")
# 大题标题前缀:中文序号、第X部分/节、Part/Section、罗马数字(Ⅰ/I)
_SECTION_PREFIX_RE = re.compile(
    r"^\s*(?:[一二三四五六七八九十]+\s*[、.．]"
    r"|第[一二三四五六七八九十]+\s*[部节]"
    r"|(?:Part|PART|Section|SECTION)\b"
    r"|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[.、．]?"
    r"|[IVX]{1,4}\s*[.、．])")
# 大题关键词(裸标题如「完形填空」「阅读理解 A」也算大题头)
_SECTION_KW = ("听力", "单项选择", "单项填空", "完形填空", "完型填空", "阅读理解", "阅读表达",
               "任务型阅读", "词汇运用", "词语运用", "首字母", "短文填空", "信息还原",
               "补全对话", "连词成句", "书面表达", "完成句子", "选词填空", "综合填空")
# 完整大题名(供从「标题+说明合并成一行」中提取干净名;按长度降序,先匹配长名如「单项填空」再「单项」)
_SECTION_NAME_KW = tuple(sorted(
    ("听力理解", "单项选择", "单项填空", "完形填空", "完型填空", "阅读理解", "阅读表达",
     "任务型阅读", "词汇运用", "词语运用", "首字母填空", "短文填空", "信息还原", "阅读填空",
     "补全对话", "连词成句", "书面表达", "完成句子", "选词填空", "缺词填空", "综合填空"),
    key=len, reverse=True))
_QNUM_RE = re.compile(r"^\s*(\d{1,2})(?:[.、．)]|\s)")
# 答案/听力材料/评分标准区标记:「试题及答案」文档在此之后会重复题号→需截断,避免题目翻倍
_ANSWER_HDR_RE = re.compile(
    r"^\s*(?:参考答案|答案与解析|答案解析|答案要点|答案[:：\s]|听力材料|听力原文|听力录音材料"
    r"|评分标准|评分建议|评分说明|作文范文|参考范文|书面表达评分|【解析】|【答案】)")
_BLANK_NUM_RE = re.compile(r"_{2,}\s*(\d{1,2})\s*_{2,}")
_OPTION_RE = re.compile(r"^[A-GＡ-Ｇ]\s*[.、．)]")
_CIRCLE_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]")
_GROUP_BREAK_RE = re.compile(r"^第[一二三四五六七八九十]+[节部]")
_INSTRUCTION_HINTS = (
    "答题卡", "满分", "选出最佳", "请认真", "请先通读", "将所译", "根据下列",
    "从方框中", "从短文后", "写在答题卡", "每小题", "每空", "仅用一次", "听两遍",
    "选择适当", "第一部分", "第二部分", "第一节", "第二节", "将下列句子译成英语",
    "阅读表达",   # 大题子标题(仅作判题型,不入短文)；正文段落不含此词
)


def _is_instruction(s: str) -> bool:
    return any(h in s for h in _INSTRUCTION_HINTS)


def _is_option_like(s: str) -> bool:
    if _OPTION_RE.match(s) or _CIRCLE_RE.match(s) or s.startswith("—"):
        return True
    head = s.split("\t", 1)[0].strip() if "\t" in s else ""
    return bool(head and _OPTION_RE.match(head))


def _is_section_header(s: str) -> bool:
    """判定一行是否为「大题标题」:标准前缀(一、/Part/Ⅰ.)或短行含大题关键词。

    排除题号行/选项行/超长说明句,避免把正文误判成大题头。
    """
    s = (s or "").strip()
    if not s:
        return False
    if _QNUM_RE.match(s) or _is_option_like(s):
        return False
    # 直接以完整大题名开头(如「单项选择 从下列…」「完形填空 阅读短文…」)→ 不论长短都算大题头
    # (原卷常把标题与说明挤在一行且无「一、」序号)
    if any(s.startswith(kw) for kw in _SECTION_NAME_KW):
        return True
    # 「中文序号 + 大题关键词(在开头 16 字内)」→ 即使标题与说明挤成一长行(PDF 抽取常见)也算大题头
    if re.match(r"^\s*(?:[一二三四五六七八九十]+|第\s*[一二三四五六七八九十]+\s*[部节])\s*[、.．]", s) \
            and any(k in s[:16] for k in _SECTION_KW):
        return True
    if len(s) > 40:
        return False
    mp = _SECTION_PREFIX_RE.match(s)
    if mp:
        head = mp.group(0)
        # 中文序号(一、/第X部/第X节)= 真大题;英文/罗马前缀(Part/Section/Ⅰ/IVX)易误伤阅读短文里的
        # 「Part 1: Facts」「Ⅰ. Intro」等子标题 → 需另含大题关键词或计分括注(满分/小题/计N分)才算大题头。
        if re.match(r"^\s*(?:[一二三四五六七八九十]|第)", head):
            return True
        return (any(k in s for k in _SECTION_KW)
                or bool(re.search(r"满分|小题|计\s*\d+\s*分", s))
                or bool(re.search(r"\b(?:Listening|Reading|Cloze|Writing|Vocabulary|Grammar|"
                                  r"Comprehension|Dialogue|Composition)\b", s, re.IGNORECASE)))
    return len(s) <= 20 and any(k in s for k in _SECTION_KW)


def _classify_kw(blob: str) -> str | None:
    if "完形" in blob or "完型" in blob:
        return "完型"
    # 动词填空(用所给动词的适当形式)——须先于「词汇运用/单项」判定,否则被吞成单选。P0
    if ("动词" in blob and "填空" in blob) or "所给动词" in blob:
        return "动词填空"
    # 词汇运用(用所给词适当形式/词形变化)——独立题型,勿再降级成单选。P0
    if ("词汇运用" in blob or "词语运用" in blob or "词汇检测" in blob
            or "适当形式" in blob or "词形" in blob):
        return "词汇运用"
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


def _section_name(header: str, lines: list[str]) -> str:
    """原卷大题名(听力选择/单项填空/完形填空…),供列表/校对按大题区分。

    标题去掉「序号、」和尾部的计分括注(如「（满分8分）」「(共20小题；满分20分)」)
    即为大题名；标题无名(如「八、（满分6分）」)时,取首个短中文标签行(如「阅读表达」)。
    """
    name = re.sub(
        r"^\s*(?:[一二三四五六七八九十\d]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]{1,4}|Part\s*\d*|Section\s*[A-D]?)"
        r"\s*[、.．]?\s*", "", header, flags=re.IGNORECASE)
    # 去掉尾部含「满分/小题/分」的整段括注
    name = re.sub(r"\s*[（(][^（()]*?(?:满分|小题|分)[^（()]*?[)）]\s*$", "", name).strip()
    # 标题与说明挤在一行(如「单项填空 （满分15分）请认真阅读…」)→ 取开头的完整大题名
    if len(name) > 10:
        for kw in _SECTION_NAME_KW:
            if header.find(kw) != -1:
                return kw
    if name:
        return name
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _QNUM_RE.match(s):
            break
        if 2 <= len(s) <= 8 and re.fullmatch(r"[一-龥]+", s):
            return s
    return "其他"


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


def _split_one_section(qtype: str, sname: str, lines: list[str], sec_text: str,
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

    # (题号, 题干, 短文)；短文非空 = 属于某题组(短文与小问分离，不再塞进题干)
    rows: list[tuple[int, str, str]] = []
    for q in questions:
        rows.append((int(q["no"]), "\n".join(q["stem"]).strip(), q["passage"]))
    embed_material = "\n".join(p for p in (embed_passage, bank) if p).strip()
    for n in missing:
        rows.append((n, f"第 {n} 空", embed_material))   # 嵌入空：题干为空位标签，材料在短文

    rows.sort(key=lambda r: r[0])
    for no, stem, passage in rows:
        if stem:
            out.append(ParsedPaperQuestion(
                question_no=str(no), question_type=qtype, stem=stem,
                student_answer=None, correct_answer=None, explanation=None,
                passage=passage or None, block_key=None,   # block_key 在全局分配
                section=sname,
            ))


def split_paper_text_structural(text: str) -> list[ParsedPaperQuestion]:
    """文字版试卷 → 确定性结构拆题。识别不到大题/题号时返回 []（由调用方决定兜底）。"""
    lines = (text or "").splitlines()
    # 截断①:「参考答案/听力材料/评分标准/【解析】」区之前
    for i, ln in enumerate(lines):
        if i > len(lines) * 0.3 and _ANSWER_HDR_RE.match(ln.strip()):
            lines = lines[:i]
            break
    # 截断②:「试题+解析版」双份文档——大题标题一旦重复出现,说明进入第二份(答案/解析),截断
    _seen: set[str] = set()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_header(s):
            key = re.sub(r"[\s（(].*$", "", _section_name(s, []))  # 大题名(去括注/空白)
            # 只用「实打实的中文大题名」判重复(≥2 字且含中文),避免退化 key(如短文子标题的 ':')误截断
            if len(key) >= 2 and re.search(r"[一-龥]", key):
                if key in _seen:
                    lines = lines[:i]
                    break
                _seen.add(key)
    sections: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if _is_section_header(ln.strip()):
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
        if not _is_section_header(header):
            continue  # 卷首标题段
        qtype = _section_type(header, sec[1:])
        sname = _section_name(header, sec[1:])
        _split_one_section(qtype, sname, sec[1:], "\n".join(sec), out)

    # 兜底:一个大题头都没识别到,但有题号 → 整卷按题号切(section=其他),至少不走 LLM
    if not out and any(_QNUM_RE.match(ln.strip()) for ln in lines):
        _split_one_section("单选", "其他", lines, text, out)

    # 全局分配题组 block_key：连续同一短文的小问归一组，短文为空的题保持独立
    blk_seq, prev_passage, prev_key = 0, None, None
    for q in out:
        if q.passage:
            if q.passage != prev_passage:
                blk_seq += 1
                prev_key = f"blk{blk_seq}"
            q.block_key = prev_key
            prev_passage = q.passage
        else:
            prev_passage, prev_key = None, None
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
    if text[:1] not in "[{":          # 兼容:裸数组(旧) 或 {questions,passages}(新)
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    passages_map: dict[str, str] = {}
    if isinstance(data, dict):
        pm = data.get("passages")
        if isinstance(pm, dict):
            passages_map = {str(k): (str(v) or "").strip() for k, v in pm.items()
                            if v and str(v).strip()}
        data = (data.get("questions")
                or next((v for v in data.values() if isinstance(v, list)), None))
    if not isinstance(data, list):
        return None
    result: list[ParsedPaperQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        block_key = (item.get("block_key") or "").strip() or None
        passage = (item.get("passage") or "").strip() or None
        if not passage and block_key:      # 短文单独放 passages → 按 block_key 回填
            passage = passages_map.get(block_key) or None
        result.append(
            ParsedPaperQuestion(
                question_no=item.get("question_no"),
                question_type=_normalize_type(item.get("question_type")),
                stem=item.get("stem"),
                student_answer=item.get("student_answer"),
                correct_answer=item.get("correct_answer"),
                explanation=item.get("explanation"),
                section=(item.get("section") or "").strip() or None,
                passage=passage,
                block_key=block_key,
            )
        )
    return result if result else None


async def _split_cache_get(md5: str) -> str | None:
    from app.core.database import async_session_factory
    from app.models.d13_v2_user_papers import PaperSplitCache
    try:
        async with async_session_factory() as db:
            row = await db.get(PaperSplitCache, md5)
            return row.raw_json if row is not None else None
    except Exception:  # noqa: BLE001  缓存不可用不阻断,照常真调
        return None


async def _split_cache_put(md5: str, raw_json: str) -> None:
    from app.core.database import async_session_factory
    from app.models.d13_v2_user_papers import PaperSplitCache
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    try:
        async with async_session_factory() as db:
            await db.execute(pg_insert(PaperSplitCache)
                             .values(input_md5=md5, raw_json=raw_json)
                             .on_conflict_do_nothing(index_elements=["input_md5"]))
            await db.commit()
    except Exception:  # noqa: BLE001
        pass


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
    if ocr.handwritten_text == "" and (ocr.printed_text or "").strip()[:1] in "[{":
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

    # 拆题 LLM 结果暂存:按输入文本 md5 全局缓存(真题按题型段分段调 → 天然「按块」缓存;
    # 整卷调用则「按卷」缓存)。同段/同卷再解析不重复付费。豆包 Vision 直出 JSON 走前面分支,不到这里。
    import hashlib
    _norm = "".join(c.lower() for c in (ocr.printed_text or "") if c.isalnum())
    _md5 = hashlib.md5(_norm.encode()).hexdigest() if _norm else None
    raw_text = await _split_cache_get(_md5) if _md5 else None
    if raw_text is None:
        try:
            # 用 fast 模型(非重推理):主模型重推理会把 token 预算耗光、content 返空→「格式异常」再被重试 3 次。
            # 整卷题多,输出预算给足 16384。
            response = await chat_completion(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=prompt + '\n\n返回 JSON 对象:{"questions":[ ...上面格式的每道题... ], "passages":{ "block_key":"短文原文", ... }}。',
                model=fast_model(),
                max_tokens=16384,
                disable_thinking=True,   # 关思考:拆题是结构化抽取,开思考会烧光 token 致 JSON 截断→失败
                response_format={"type": "json_object"},
                feature="paper_split",
            )
        except Exception as exc:
            raise AppError(code=502, message=f"整卷拆题服务暂时不可用（{exc}）") from exc

        raw_text = (response.choices[0].message.content or "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[-2] if raw_text.count("```") >= 2 else raw_text
            raw_text = raw_text.lstrip("json").strip()
        if _md5 and raw_text:
            await _split_cache_put(_md5, raw_text)

    try:
        data = json.loads(raw_text or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="整卷拆题返回格式异常") from exc

    # 短文单独放 passages 映射(block_key→原文);题只带 block_key。省 token、更可靠。
    passages_map: dict[str, str] = {}
    # 容错:接受裸数组,或 {questions:[...]} / {items:[...]} / 首个是 list 的值
    if isinstance(data, dict):
        pm = data.get("passages")
        if isinstance(pm, dict):
            passages_map = {str(k): (str(v) or "").strip() for k, v in pm.items()
                            if v and str(v).strip()}
        data = (data.get("questions") or data.get("items")
                or next((v for v in data.values() if isinstance(v, list)), None))
    if not isinstance(data, list):
        raise AppError(code=500, message="整卷拆题返回格式异常")

    result: list[ParsedPaperQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        block_key = (item.get("block_key") or "").strip() or None
        # passage 优先取题内联;没有则按 block_key 从 passages 映射回填
        passage = (item.get("passage") or "").strip() or None
        if not passage and block_key:
            passage = passages_map.get(block_key) or None
        result.append(
            ParsedPaperQuestion(
                question_no=item.get("question_no"),
                question_type=_normalize_type(item.get("question_type")),
                stem=item.get("stem"),
                student_answer=item.get("student_answer"),
                correct_answer=item.get("correct_answer"),
                explanation=item.get("explanation"),
                section=(item.get("section") or "").strip() or None,
                passage=passage,
                block_key=block_key,
            )
        )
    return result
