"""真题「题目层科学解析」service(试点:阅读理解;见 docs/AI整卷匹配-分题型科学解析)。

铁律:**AI 只出建议,人工逐题确认后才写库**(confirm_analysis 是唯一写入口)。
防胡说机制(程序一票否决,不合格建议直接标 invalid,不进人工队列):
- 定位句 evidence 必须是原文(短文;无短文则题干)的子串——空白归一后比对;
- 干扰项错因必须在封闭枚举内;rc_code 必须是图谱既有 rc-* 节点。
解析存 platform_question.meta["analysis"](JSONB,免迁移)。
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, Passage
from app.services.kp_suggest_service import classify_reading_skill
from app.services.llm_provider import chat_completion, complete_json, is_llm_dev_mode

# 逐空/逐题 LLM 建议并发上限(完形一篇十几个空,串行必超时;并发限流跑,墙钟砍到 ~1/N)
_LLM_CONCURRENCY = 6


async def _gather_bounded(coros: list, *, limit: int) -> list:
    """限流并发跑一批协程,保持入参顺序返回。仅用于**无 DB 写**的独立任务(如 LLM 调用)。"""
    sem = asyncio.Semaphore(limit)

    async def _run(c):
        async with sem:
            return await c
    return await asyncio.gather(*[_run(c) for c in coros])

# 干扰项错因封闭枚举(干扰项理据分析 distractor rationale 的常用分类)
DISTRACTOR_TYPES = ("原文近似词误配", "以偏概全", "过度推断", "无中生有", "张冠李戴", "因果倒置")

# ── 完形填空:双轴解析(载体槽=形式,线索类型=真构念;Bachman 完形约束跨度分类)────
# 线索类型封闭枚举——决定学情归因与仿真变式("同线索类型"),载体(词性)区分度≈0
CLUE_TYPES = ("句内固定搭配", "句内语法约束", "跨句逻辑关系", "跨句词汇复现",
              "全篇情感基调", "指代与人物追踪", "情景交际惯用")
SLOT_TYPES = ("副词槽", "连词槽", "介词槽", "代词槽", "交际用语槽", "动词形式槽",
              "动词短语槽", "实义动词槽", "名词槽", "形容词槽", "数词槽")

# ── 书面表达:写作解析(要点覆盖=客观锚 + 5 维 wr-* 量表 + 范文/目标句型/失分点)──────
# 体裁与主时态封闭枚举;要点(points)是提示作文最客观、可逐条机检的锚,压 LLM 主观波动
WRITING_GENRES = ("记叙文", "议论文", "说明文", "应用文")
WRITING_TENSES = ("一般现在时", "一般过去时", "一般将来时", "现在完成时",
                  "现在进行时", "过去进行时", "混合时态")

# 常见「动词 + 小品词」里的小品词(判动词短语槽:gave up/got up/set up/picked up…)
_PARTICLES = {"up", "down", "on", "off", "in", "out", "away", "back", "over",
              "around", "along", "through", "forward", "aside", "apart", "by"}

# LLM 偶尔用同义词写载体槽,归一到枚举值(程序判不出时的兜底)
_SLOT_ALIASES = {
    "动词短语": "动词短语槽", "短语动词": "动词短语槽", "词组动词": "动词短语槽",
    "实义动词": "实义动词槽", "动词": "实义动词槽", "名词": "名词槽",
    "形容词": "形容词槽", "副词": "副词槽", "介词": "介词槽", "连词": "连词槽",
    "代词": "代词槽", "数词": "数词槽", "交际用语": "交际用语槽", "动词形式": "动词形式槽",
}


def normalize_slot(slot: str | None) -> str | None:
    """把 LLM 给的载体槽归一到枚举(动词短语→动词短语槽);已是枚举值原样返回。"""
    if not slot:
        return slot
    s = str(slot).strip()
    return s if s in SLOT_TYPES else _SLOT_ALIASES.get(s, s)

_OPT_PREFIX = re.compile(r"^[A-DＡ-Ｄa-d][.、．)]\s*")
# 拆 embedded 选项:仅大写 A-D(避免 "a history" 误识别);支持 A. x / A x / tab
_OPT_MARKER = re.compile(
    r"(?:^|[\s\t\r\n])([A-DＡ-Ｄ])[.、．)]?\s+"
    r"(.+?)"
    r"(?=(?:[\s\t\r\n][A-DＡ-Ｄ][.、．)]?\s+)|\s*$)",
    re.DOTALL,
)
_OPT_SPLIT = re.compile(
    r"[\s\t\r\n]*[A-DＡ-Ｄ](?:[.、．)]\s*|\s+)(?=[^\s\t\r\n])"
)
_GIVEN_IN_STEM = re.compile(r"[（(]\s*([A-Za-z][A-Za-z\s'\-]{0,40})\s*[）)]")


def _norm_option_letter(ch: str) -> str:
    """全角/小写 → 大写 A-D。"""
    c = str(ch or "").strip()
    if c in "ａｂｃｄ":
        return chr(ord(c) - ord("ａ") + ord("A"))
    if c in "abcd":
        return c.upper()
    if c in "ＡＢＣＤ":
        return chr(ord(c) - ord("Ａ") + ord("A"))
    return c.upper()


def parse_options_lettered(stem: str) -> dict[str, str]:
    """从题干解析嵌入式选项 → {A: text, B: text, …}。支持 A good / A. good / tab。"""
    out: dict[str, str] = {}
    for m in _OPT_MARKER.finditer(stem or ""):
        letter = _norm_option_letter(m.group(1))
        if letter not in "ABCD":
            continue
        text = m.group(2).strip().strip("\t").strip()
        if text:
            out[letter] = text
    return out


def parse_given_from_stem(stem: str) -> str | None:
    """括号所给词:(work) → work。"""
    m = _GIVEN_IN_STEM.search(stem or "")
    if not m:
        return None
    return m.group(1).strip()


def _section_is_word_fill(sec: str) -> bool:
    import re as _re
    s = sec or ""
    if _re.search(r"短文|完成句子|翻译|句型转换|缺词|完形|完型|阅读|听力", s):
        return False
    return bool(_re.search(r"词汇|词语|动词|单词|所给|适当形式|词形", s))


def stem_looks_word_fill(stem: str) -> bool:
    """题干含 (所给词) 且非四选一选项卷面。"""
    if not parse_given_from_stem(stem):
        return False
    return len(parse_options_lettered(stem)) < 2


def parse_options_from_stem(stem: str) -> list[str] | None:
    """从题干解析嵌入式选项(切题器常把 'A. x  B. y  C. z  D. w' 留在 stem、options 列为空)。
    解析出 3-4 项才认,否则 None(宁缺勿错)。"""
    lettered = parse_options_lettered(stem)
    if lettered:
        opts = [lettered[k] for k in "ABCD" if k in lettered]
        return opts if 3 <= len(opts) <= 4 else None
    parts = [p.strip().strip("\t").strip() for p in _OPT_SPLIT.split(stem or "")]
    opts = [p for p in parts[1:] if p]
    return opts if 3 <= len(opts) <= 4 else None


_CONJS = {"but", "and", "so", "or", "because", "though", "although", "while", "until",
          "unless", "if", "when", "before", "after", "since", "as", "however", "besides"}
_PREPS = {"in", "on", "at", "for", "with", "by", "from", "of", "to", "about", "under",
          "over", "through", "during", "between", "among", "behind", "above", "below",
          "near", "inside", "outside", "without", "against", "across", "towards"}
_PRONS = {"he", "him", "his", "himself", "she", "her", "hers", "herself", "they", "them",
          "their", "theirs", "themselves", "it", "its", "itself", "we", "us", "our",
          "ours", "ourselves", "you", "your", "yours", "yourself", "i", "me", "my", "mine", "myself"}
_COMMS = {"thanks", "sorry", "excuse me", "please", "congratulations", "well done",
          "good idea", "no problem", "you're welcome", "never mind", "cheer up",
          "good luck", "come on", "pardon"}
_VERB_SUFFIX = {"", "s", "es", "d", "ed", "ing", "en", "ne"}


def classify_cloze_slot(options: list | None) -> str | None:
    """载体槽确定性判定:完形四选项同词性即定槽(区分度=0 的形式轴,程序判,零 LLM)。
    拿不准返回 None(交 LLM/人工)。"""
    if not options or len(options) < 2:
        return None
    words = [_OPT_PREFIX.sub("", str(o)).strip().lower() for o in options]
    if any(not w for w in words):
        return None
    if all(w.endswith("ly") and " " not in w for w in words):
        return "副词槽"
    if all(w in _CONJS for w in words):
        return "连词槽"
    if all(w in _PREPS for w in words):
        return "介词槽"
    if all(w in _PRONS for w in words):
        return "代词槽"
    if all(w in _COMMS for w in words):
        return "交际用语槽"
    # 动词短语槽:全是「动词 + 小品词」(gave up/got up/set up/picked up)——2 词且末词是小品词
    split = [w.split() for w in words]
    if all(len(p) == 2 and p[1] in _PARTICLES for p in split):
        return "动词短语槽"
    # 动词形式槽:同一词干的不同形态(goes/going/gone)——共同前缀≥2 且余部是屈折后缀
    prefix = words[0]
    for w in words[1:]:
        while prefix and not w.startswith(prefix):
            prefix = prefix[:-1]
    if len(prefix) >= 2 and all(w[len(prefix):] in _VERB_SUFFIX for w in words):
        return "动词形式槽"
    return None

_SYSTEM_PROMPT = (
    "你是中小学英语阅读测评专家。对给定的阅读理解小题做「题目层解析」,只返回 JSON:"
    '{"rc_code":"rc-x-x 技能编码","evidence":"答案定位句(必须逐字摘自原文)",'
    '"answer_reason":"由定位句到正确项的推理(1-2句)",'
    '"distractors":{"A":{"meaning":"该选项的义项/主张(中文)","why_wrong":"为何是干扰项——与原文哪处冲突,可点明错因类型"},...}}。'
    "distractors 只列**非正确项**(正确项不出现),每项必须给 meaning(该选项说了什么)+why_wrong(错在哪、与哪条定位句/原文事实冲突)。"
    "why_wrong 可点明错因类型(参考:" + "、".join(DISTRACTOR_TYPES) + "),但必须结合本题原文具体说明,不能只写一个类型词。"
)


# 印刷体标点 → ASCII 归一(弯引号/弯撇号/破折号/省略号/不间断空格)。
# LLM 照抄原文时常把弯引号写成直引号,若不折叠会误判「不是原文子串」。
_TYPO_MAP = {
    "‘": "'", "’": "'", "‛": "'",          # ‘ ’ ‛ → '
    "“": '"', "”": '"', "„": '"',          # “ ” „ → "
    "–": "-", "—": "-", "―": "-",          # – — ― → -
    "…": "...",                                       # … → ...
    " ": " ", "　": " ",                          # 不间断/全角空格 → 空格
    "＂": '"', "＇": "'",                          # 全角 " ' → 直引号
}
_TYPO_TABLE = {ord(k): v for k, v in _TYPO_MAP.items()}


def _norm(s: str) -> str:
    """归一:印刷体标点折叠 + 标点→空格 + 空白折叠 + 小写。用于线索句/定位句的原文子串比对。

    只影响「是否原文子串」的判定,不改写入库的原文。防幻觉强度不变(仍要求所有词按原序
    连续出现),但对标点不敏感:LLM 常把句末 `…`/`.` 规整成 `!`(如原文 `animals...`↔建议
    `animals!`)或改弯直引号,这类纯标点差异不再被误判为幻觉。按 unicode 词字符保留中英文。
    """
    folded = re.sub(r"[^\w\s]", " ", (s or "").translate(_TYPO_TABLE).lower())
    return re.sub(r"\s+", " ", folded).strip()


def _answer_words_for_logic_stem(q: PlatformQuestion, analysis: dict) -> list[str]:
    """校验 logic_stem 时用于检测是否误填答案。"""
    from app.services.option_vocab_service import effective_answer

    words: list[str] = []
    ans = effective_answer(q, analysis)
    if ans and len(ans.strip()) > 1:
        words.append(ans.strip())
    lettered = parse_options_lettered(q.stem or "")
    if not lettered and q.options:
        opts = q.options if isinstance(q.options, list) else []
        lettered = {L: opts[i] for i, L in enumerate("ABCD") if i < len(opts)}
    al = (analysis.get("answer_letter") or "").strip().upper()
    if al in lettered and lettered[al]:
        words.append(lettered[al])
    aw = (analysis.get("answer_word") or analysis.get("target_form") or "").strip()
    if aw:
        words.append(aw)
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            out.append(w)
    return out


def validate_reading_analysis(analysis: dict, *, context_text: str) -> list[str]:
    """校验一份阅读题目层解析;返回错误列表(空=通过)。"""
    errs: list[str] = []
    ev = (analysis.get("evidence") or "").strip()
    if not ev:
        errs.append("缺少定位句 evidence")
    elif _norm(ev) not in _norm(context_text):
        errs.append("定位句不是原文子串(疑似幻觉)")
    code = (analysis.get("rc_code") or "").strip()
    if not code.startswith("rc-"):
        errs.append("rc_code 缺失或不合法")
    # 阅读干扰项与完形同构:原义(meaning)+干扰机制(why_wrong)。每项须双全;不强制列满(可只标错项)。
    dss = analysis.get("distractors") or {}
    if not isinstance(dss, dict):
        errs.append("distractors 须为对象 {选项: {meaning, why_wrong}}")
    else:
        for k, v in dss.items():
            if str(k).upper() not in {"A", "B", "C", "D"}:
                errs.append(f"干扰项键非法:{k}")
            if not isinstance(v, dict) or not (v.get("meaning") or "").strip() \
                    or not (v.get("why_wrong") or "").strip():
                errs.append(f"干扰项 {k} 须含 义项(meaning)+干扰机制(why_wrong)")
    if not (analysis.get("answer_reason") or "").strip():
        errs.append("缺少 answer_reason")
    return errs


def validate_passage_fill_analysis(analysis: dict, *, context_text: str) -> list[str]:
    """校验短文填空(开放填空)解析:复用完形「线索类型+线索句」轴,但**无载体槽/无干扰项**(无选项)。
    线索句须短文子串(防幻觉);线索类型枚举;应填词非空;kp_codes(cf-/jf-/rc-)非空。"""
    errs: list[str] = []
    clue = (analysis.get("clue") or "").strip()
    if not clue:
        errs.append("缺少线索句 clue")
    elif _norm(clue) not in _norm(context_text):
        errs.append("线索句不是原文子串(疑似幻觉)")
    if analysis.get("clue_type") not in CLUE_TYPES:
        errs.append("clue_type 不在枚举内")
    if not (analysis.get("answer_word") or "").strip():
        errs.append("缺少 answer_word(应填的词)")
    codes = analysis.get("kp_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("kp_codes 须为非空编码列表(cf-/jf-/rc-)")
    elif not all(str(c).startswith(("cf-", "jf-", "rc-")) for c in codes):
        errs.append("kp_codes 须为 cf-/jf-/rc- 编码")
    from app.services.logic_display_service import validate_analysis_logic_stem
    aw = [(analysis.get("answer_word") or "").strip()]
    aw = [w for w in aw if w]
    errs.extend(validate_analysis_logic_stem(
        analysis, context_text=context_text, answer_words=aw, require_blank=True))
    return errs


def validate_cloze_analysis(
    analysis: dict, *, context_text: str, answer_words: list[str] | None = None,
) -> list[str]:
    """校验一份完形逐空解析;返回错误列表(空=通过)。"""
    errs: list[str] = []
    clue = (analysis.get("clue") or "").strip()
    if not clue:
        errs.append("缺少线索句 clue")
    elif _norm(clue) not in _norm(context_text):
        errs.append("线索句不是原文子串(疑似幻觉)")
    if analysis.get("clue_type") not in CLUE_TYPES:
        errs.append("clue_type 不在枚举内")
    slot = analysis.get("slot")
    if slot and slot not in SLOT_TYPES:
        errs.append(f"载体槽非法:{slot}")
    codes = analysis.get("kp_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("kp_codes 须为非空编码列表(线索轴为主)")
    # 完形干扰项 = 原义 + 干扰机制(词义本身合理、但与语境线索冲突——与阅读的枚举错因不同)
    dts = analysis.get("distractors") or {}
    if not isinstance(dts, dict):
        errs.append("distractors 须为对象 {选项: {meaning, why_wrong}}")
    else:
        for k, v in dts.items():
            if str(k).upper() not in {"A", "B", "C", "D"}:
                errs.append(f"干扰项键非法:{k}")
            if not isinstance(v, dict) or not (v.get("meaning") or "").strip() \
                    or not (v.get("why_wrong") or "").strip():
                errs.append(f"干扰项 {k} 须含 原义(meaning)+干扰机制(why_wrong)")
    from app.services.logic_display_service import validate_analysis_logic_stem
    errs.extend(validate_analysis_logic_stem(
        analysis, context_text=context_text, answer_words=answer_words, require_blank=True))
    return errs


def validate_grammar_mc_analysis(analysis: dict, *, context_text: str = "") -> list[str]:
    """校验语法单选(词法/句法)解析。单选自足→**不强制原文子串**;校验:考点(cf-/jf-)+ 答案依据 +
    干扰项「原义/形态 + 违规机制」双全。"""
    errs: list[str] = []
    codes = analysis.get("kp_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("kp_codes 须为非空考点编码列表(词法 cf-/句法 jf-)")
    elif not all(str(c).startswith(("cf-", "jf-")) for c in codes):
        errs.append("kp_codes 须为词法 cf- 或句法 jf- 编码")
    if not (analysis.get("answer_reason") or "").strip():
        errs.append("缺少 answer_reason(正确项命中哪条语法/搭配规则)")
    dts = analysis.get("distractors") or {}
    if not isinstance(dts, dict):
        errs.append("distractors 须为对象 {选项: {meaning, why_wrong}}")
    else:
        for k, v in dts.items():
            if str(k).upper() not in {"A", "B", "C", "D"}:
                errs.append(f"干扰项键非法:{k}")
            if not isinstance(v, dict) or not (v.get("meaning") or "").strip() \
                    or not (v.get("why_wrong") or "").strip():
                errs.append(f"干扰项 {k} 须含 原义/形态(meaning)+违规机制(why_wrong)")
    return errs


def validate_word_fill_analysis(
    analysis: dict, *, context_text: str = "", answer_words: list[str] | None = None,
) -> list[str]:
    """校验填空词形类(动词填空/词汇运用/单词拼写)解析:给词→定形。开放填空无干扰项。
    校验:考点(cf-/jf-)+ 词形变化类型 + 定形依据/答案依据。单句自足,不强制原文子串。"""
    errs: list[str] = []
    codes = analysis.get("kp_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("kp_codes 须为非空考点编码列表(词法 cf-/句法 jf-)")
    elif not all(str(c).startswith(("cf-", "jf-")) for c in codes):
        errs.append("kp_codes 须为词法 cf- 或句法 jf- 编码")
    if not (analysis.get("change_type") or "").strip():
        errs.append("缺少 change_type(词形变化类型:时态/语态/非谓语/名词复数/派生等)")
    if not (analysis.get("answer_reason") or "").strip():
        errs.append("缺少 answer_reason(定形依据:据什么线索定这个形式)")
    ctx = context_text or (analysis.get("logic_stem") or "")
    from app.services.logic_display_service import validate_word_fill_logic_stem
    errs.extend(validate_word_fill_logic_stem(
        analysis, stem_text=ctx, answer_words=answer_words))
    return errs


def validate_sentence_analysis(analysis: dict, *, context_text: str = "") -> list[str]:
    """校验完成句子/翻译/句型转换(句法结构)解析。production 型→无干扰项、不强制原文子串。
    校验:目标句型 + 考点(jf-/cf-)+ 采分点(非空)+ 参考答案。"""
    errs: list[str] = []
    if not (analysis.get("target_structure") or "").strip():
        errs.append("缺少 target_structure(目标句型/结构:强调句/宾语从句/被动/非谓语等)")
    codes = analysis.get("kp_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("kp_codes 须为非空考点编码列表(句法 jf-/词法 cf-)")
    elif not all(str(c).startswith(("cf-", "jf-")) for c in codes):
        errs.append("kp_codes 须为句法 jf- 或词法 cf- 编码")
    kps = analysis.get("key_points") or []
    if not isinstance(kps, list) or not kps or not all(isinstance(x, str) and x.strip() for x in kps):
        errs.append("key_points 须为非空采分点列表")
    if not (analysis.get("answer") or "").strip():
        errs.append("缺少 answer(参考答案句)")
    return errs


def validate_writing_analysis(analysis: dict, *, context_text: str) -> list[str]:
    """校验一份书面表达写作解析;返回错误列表(空=通过)。

    要点(points)非空=最客观锚;目标句型(target_expressions)必须能在范文里逐字定位(防幻觉,
    同 evidence/clue 子串思路);体裁/主时态在枚举;wr_codes 非空(图谱存在性在 confirm 里查)。"""
    errs: list[str] = []
    if analysis.get("genre") not in WRITING_GENRES:
        errs.append("genre 体裁不在枚举内")
    tense = analysis.get("main_tense")
    if tense and tense not in WRITING_TENSES:
        errs.append("main_tense 主时态不在枚举内")
    points = analysis.get("points") or []
    if not isinstance(points, list) or not points \
            or not all(isinstance(p, dict) and (p.get("point") or "").strip() for p in points):
        errs.append("points 须为非空要点列表,每条含 point 文本")
    codes = analysis.get("wr_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("wr_codes 须为非空写作考点编码列表")
    essay = (analysis.get("model_essay") or "").strip()
    if not essay:
        errs.append("缺少范文 model_essay(可点「AI 重新解析」生成范文候选,或人工补)")
    tgts = analysis.get("target_expressions") or []
    if not isinstance(tgts, list):
        errs.append("target_expressions 须为列表")
    elif essay:                       # 目标句型必须逐字取自范文(防 AI 编句型)
        essay_n = _norm(essay)
        for t in tgts:
            if not (t or "").strip():
                continue
            if _norm(t) not in essay_n:
                errs.append(f"目标句型不是范文子串(疑似幻觉):{str(t)[:24]}")
    # 结构套路:选填(是"照着能写"的脚手架);若给则每段须有 guide(该段怎么写)
    struct = analysis.get("structure")
    if struct is not None:
        if not isinstance(struct, list) \
                or not all(isinstance(b, dict) and (b.get("guide") or "").strip() for b in struct):
            errs.append("structure 若填,须为逐段 {role, guide} 列表且每段 guide 非空")
    return errs


def analysis_constraints_text(analysis: dict | None) -> str:
    """解析对象 → 仿真派生 prompt 的约束文本(同线索类型+同载体槽/同技能+同错因策略)。"""
    if not analysis:
        return ""
    lines: list[str] = []
    if analysis.get("clue_type"):                    # 完形
        slot = analysis.get("slot")
        lines.append(f"本空线索类型:{analysis['clue_type']}(变式必须保持同线索类型)")
        if slot:
            lines.append(f"载体槽:{slot}(四个选项保持同词性)")
    if analysis.get("rc_code"):                      # 阅读
        lines.append(f"本题阅读技能:{analysis['rc_code']}(变式必须考同一技能,答案须可回文定位)")
    if analysis.get("genre"):                        # 书面表达:同体裁+同要点数+同考点+同目标句型
        pts = analysis.get("points") or []
        lines.append(f"本题体裁:{analysis['genre']}"
                     + (f"({analysis.get('sub_format')})" if analysis.get("sub_format") else "")
                     + f",主时态:{analysis.get('main_tense') or '不限'}"
                     + f"(变式须同体裁、要点条数保持 {len(pts)} 条)")
        if analysis.get("strategy"):     # 套路复用:仿真同体裁题沿用同一写作套路
            lines.append(f"写作套路(变式沿用同套路,让学生一套打多题):{analysis['strategy']}")
        if analysis.get("wr_codes"):
            lines.append("写作考点(变式须同考点):" + "、".join(analysis["wr_codes"]))
        tgts = [t for t in (analysis.get("target_expressions") or []) if (t or "").strip()]
        if tgts:
            lines.append("目标高级句型(变式范文须示范同类句型):" + "; ".join(tgts)[:300])
    if analysis.get("kind") == "grammar_mc" and analysis.get("kp_codes"):   # 语法单选:同词法/句法考点
        lines.append("本题语法考点:" + "、".join(analysis["kp_codes"]) + "(变式必须考同考点、同结构,只换话题/词汇)")
    if analysis.get("kind") == "word_fill":                                 # 填空词形类:同考点+同词形变化
        lines.append(f"本题词形考点:{'、'.join(analysis.get('kp_codes') or [])};词形变化类型:"
                     f"{analysis.get('change_type', '')}(变式考同考点、同变化类型,换词/情境)")
    if analysis.get("kind") == "sentence":                                  # 完成句子:同句法结构+同考点
        lines.append(f"本题目标句型:{analysis.get('target_structure', '')};句法考点:"
                     f"{'、'.join(analysis.get('kp_codes') or [])}(变式考同句型/结构,换话题/词汇)")
    dts = analysis.get("distractor_types") or {}
    if dts:                                          # 阅读:枚举错因策略
        lines.append("干扰项错因策略(变式按同策略造干扰项):" +
                     "、".join(sorted(set(dts.values()))))
    dss = analysis.get("distractors") or {}
    if dss:                                          # 完形:同干扰机制(原义合理×语境冲突)
        mech = "; ".join(f"{k}:{(v or {}).get('why_wrong', '')}" for k, v in sorted(dss.items()))
        lines.append(f"干扰项设计机制(变式按同机制造干扰项——词义本身合理但与语境线索冲突):{mech[:300]}")
    return ("\n".join(lines) + "\n") if lines else ""


async def _kp_codes_exist(db: AsyncSession, codes: list[str]) -> list[str]:
    """返回图谱里不存在的编码列表(空=全部存在)。"""
    if not codes:
        return []
    found = set((await db.execute(
        sa.select(KnowledgeNode.code).where(KnowledgeNode.code.in_(codes)))).scalars().all())
    return [c for c in codes if c not in found]


async def _rc_code_exists(db: AsyncSession, code: str) -> bool:
    return (await db.execute(
        sa.select(KnowledgeNode.id).where(KnowledgeNode.code == code).limit(1)
    )).first() is not None


async def _passage_map(db: AsyncSession, questions: list[PlatformQuestion]) -> dict:
    """block_id → 短文正文。"""
    block_ids = {q.block_id for q in questions if q.block_id}
    if not block_ids:
        return {}
    return {pid: txt for pid, txt in (await db.execute(
        sa.select(Passage.id, Passage.text).where(Passage.id.in_(block_ids))
    )).all()}


async def _load_with_context(
    db: AsyncSession, question_ids: list[uuid.UUID]
) -> list[tuple[PlatformQuestion, str]]:
    """加载题目 + 其上下文正文(题组短文;无短文用题干,微题短文内嵌 stem)。"""
    qs = list((await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id.in_(question_ids))
    )).scalars().all())
    block_ids = {q.block_id for q in qs if q.block_id}
    pmap: dict = {}
    if block_ids:
        pmap = {pid: txt for pid, txt in (await db.execute(
            sa.select(Passage.id, Passage.text).where(Passage.id.in_(block_ids)))).all()}
    out = []
    for q in qs:
        passage = pmap.get(q.block_id) if q.block_id else None
        # 定位句可来自短文或题干(自含微题);校验语境 = 两者拼接
        out.append((q, f"{passage or ''}\n{q.stem or ''}"))
    return out


def _mock_suggestion(q: PlatformQuestion, context: str) -> dict:
    """dev-mock:确定性建议(取语境第一句为定位句),离线可测。"""
    first = re.split(r"(?<=[.!?])\s+", context.strip())[0][:200]
    ans = (q.answer or "").strip().upper()
    opts = q.options if isinstance(q.options, list) else []
    dss = {chr(65 + i): {"meaning": f"mock 义项{i}", "why_wrong": "mock:与定位句事实冲突"}
           for i in range(len(opts)) if chr(65 + i) != ans}
    return {
        "rc_code": classify_reading_skill(q.stem or "") or "rc-1-1",
        "evidence": first,
        "answer_reason": "dev-mock:据第一句可定位答案。",
        "distractors": dss,
    }


async def _llm_suggestion(q: PlatformQuestion, context: str, rc_catalog: str) -> dict:
    opts = json.dumps(q.options, ensure_ascii=False) if q.options else "(无选项)"
    user = (f"【rc 技能目录】\n{rc_catalog}\n\n【原文】\n{context[:3500]}\n\n"
            f"【题目】{q.stem}\n【选项】{opts}\n【正确答案】{q.answer or '未知'}")
    # 用 complete_json:length 截断升档重试、抖动重试(裸 chat_completion 一截断/抖动即失败)
    data = await complete_json(
        system_prompt=_SYSTEM_PROMPT, user_prompt=user, max_tokens=1024,
        escalate_ceiling=2048, validate=lambda d: bool((d.get("evidence") or "").strip()),
        feature="reading_analysis")
    return data or {}   # None → 空 dict,由 validate_reading_analysis 报「缺定位句」


async def suggest_reading_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为阅读小题生成「题目层解析」**建议**(不写库)。逐条带校验结果,invalid 的直接标明错误。"""
    pairs = await _load_with_context(db, question_ids)
    rc_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name)
            .where(KnowledgeNode.code.like("rc-%")).order_by(KnowledgeNode.code))).all())
    # 1) LLM 建议:逐题并发(互不依赖);2) 校验/图谱查用共享 db 串行
    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_suggestion(q, context), None
            return await _llm_suggestion(q, context, rc_catalog), None
        except Exception as exc:  # noqa: BLE001 单题失败不拖垮整批
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        errs = validate_reading_analysis(ana, context_text=context)
        if not errs and not await _rc_code_exists(db, ana.get("rc_code", "")):
            errs = [f"rc_code 不在图谱:{ana.get('rc_code')}"]
        _stage_draft(q, ana, errs)      # 暂存(随 suggest 端点一次 commit)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


_CLOZE_SYSTEM = (
    "你是中小学英语完形填空测评专家。完形四选项同词性,词性本身区分度为零;"
    "真正被测的是「语境线索」——干扰项的词义本身合理,错在与语境线索冲突。"
    "对给定空做双轴解析,只返回 JSON:"
    '{"clue_type":"线索类型","clue":"决定答案的线索句(必须逐字摘自原文)",'
    '"logic_stem":"单独逻辑题挖空句(根据原文改写/生成、自足可读、含 ____ 、禁止填入正确选项词)",'
    '"answer_letter":"正确项字母(未给答案时按语境推断)",'
    '"kp_codes":["考点编码(从目录挑,线索轴为主)"],'
    '"distractors":{"A":{"meaning":"该词原义(中文)","why_wrong":"为何在本语境是干扰(必须指出与哪条线索冲突)"},...}}。'
    "线索类型只能取:" + "、".join(CLUE_TYPES) + "。"
    "distractors 只列**非正确项**,每项必须给 meaning+why_wrong。\n"
    "★线索句 clue 的铁律(违反即作废):必须从【原文】里**逐字复制**一句(或连续的一小段),"
    "单词、拼写、缩写('It's'不改成'It is')原样不动,**不得改写、翻译、缩写、补全或拼接不相邻的句子**。"
    "clue 会用程序在原文里做子串比对(弯直引号、破折号会自动归一,大小写不敏感),凑不出原文子串就判幻觉作废。"
    "★logic_stem 与 clue 分工(重要):clue=教研证据(原文子串);logic_stem=给学生单独作答的**自足挖空题干**。"
    "logic_stem **允许且应当根据原文改写/生成**(不是照抄空所在句):学生不看短文也能理解句意并选出正确项。"
    "必须消解指代:把 it/they/this/that 等换成具体名词(如 the seed/the flower),补上必要对象或场景;"
    "语义忠实本空考查点,不得改变答案;除目标考点词外其余用词简单常见;挖空用 ____ ;**不得填入正确选项词**。"
    "反例(不合格):Every day she ____ it three times…(it 无指代,无法独立选 watered)。"
    "正例:Every day she ____ the little seed three times, singing to it like Grandma taught her。"
    "为避免 JSON 出错:**clue 优先选不含双引号的那段**;若线索落在对话里,**只取引号内的句子、去掉两侧的英文双引号 \"**"
    "(去掉后仍是原文子串,照样通过)。"
)


def _effective_options(q: PlatformQuestion) -> list[str] | None:
    """options 列优先;为空则从 stem 解析嵌入式选项(切题器常把选项留在题干)。"""
    if q.options:
        return list(q.options) if isinstance(q.options, list) else None
    return parse_options_from_stem(q.stem or "")


def _mock_cloze_suggestion(q: PlatformQuestion, context: str) -> dict:
    from app.services.logic_display_service import (
        _normalize_blank_markers, _sentence_with_blank_from_passage,
    )
    first = re.split(r"(?<=[.!?])\s+", context.strip())[0][:200]
    clue = first
    # mock:自足挖空句(允许改写),优先短文空位句,否则拼一条带对象的兜底
    logic = _sentence_with_blank_from_passage(context, q.question_no)
    if not logic:
        logic = _normalize_blank_markers(clue) or (
            "She ____ the little plant every day, just like Grandma taught her.")
    opts = _effective_options(q) or []
    dss = {chr(65 + i): {"meaning": f"mock 原义{i}", "why_wrong": "mock:与线索句语境冲突"}
           for i, _ in enumerate(opts[:2])}
    return {"slot": classify_cloze_slot(opts),
            "clue_type": "跨句逻辑关系", "clue": clue, "logic_stem": logic,
            "kp_codes": ["rc-6-1"], "distractors": dss}


async def _llm_cloze_suggestion(q: PlatformQuestion, context: str, clue_catalog: str) -> dict:
    eff = _effective_options(q)
    slot = classify_cloze_slot(eff)
    opts = json.dumps(eff, ensure_ascii=False) if eff else "(无选项)"
    slot_hint = (f"{slot}(程序已判,以此为准)" if slot
                 else "未定,请你从以下里选一个:" + "、".join(SLOT_TYPES))
    user = (f"【线索轴考点目录】\n{clue_catalog}\n\n【原文(空格即本题)】\n{context[:3500]}\n\n"
            f"【本空题干】{q.stem}\n【选项(A-D 顺序)】{opts}\n【正确答案】{q.answer or '未知(请按语境推断)'}\n"
            f"【载体槽】{slot_hint};在 JSON 里用 \"slot\" 字段回填(只能取上述枚举值)")
    # complete_json:length 截断→升档 max_tokens 重试(完形短文长,2200 常被截);
    # JSON 破损/无线索句(validate 不过)/网络抖动→重试。取代原固定预算的盲重试。
    ana = await complete_json(
        system_prompt=_CLOZE_SYSTEM, user_prompt=user, max_tokens=2200,
        escalate_ceiling=4400,
        # clue 必有;logic_stem 缺则后续 ensure 程序回填(方案 A),不在此把整题打成 None
        validate=lambda d: bool((d.get("clue") or "").strip()),
        feature="cloze_analysis")
    if ana is None:
        raise ValueError("LLM 未产出有效解析(截断/抖动重试后仍失败),可点「改」重试")
    ana["slot"] = slot or normalize_slot(ana.get("slot"))   # 程序判优先;LLM 值归一到枚举
    return ana


def _stage_draft(q: PlatformQuestion, ana: dict, errs: list[str]) -> None:
    """把 AI 建议**暂存**到 meta.analysis_draft(区别于人工确认的 meta.analysis)。

    暂存≠正式:一关弹窗/刷新不丢、再开秒读不重跑 LLM;人工确认(confirm)才写 meta.analysis 并清暂存。
    """
    from sqlalchemy.orm.attributes import flag_modified
    q.meta = {**(q.meta or {}), "analysis_draft": {
        "analysis": ana, "errors": errs,
        "staged_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}}
    flag_modified(q, "meta")


def _cached_item(q: PlatformQuestion) -> dict | None:
    """不跑 LLM,从 meta 取「已确认」或「暂存」的解析;都没有则 None(需生成)。"""
    meta = q.meta or {}
    confirmed = meta.get("analysis")
    if confirmed:
        return {"question_id": str(q.id), "analysis": confirmed,
                "errors": [], "existing": confirmed}
    draft = meta.get("analysis_draft")
    if draft and draft.get("analysis"):
        return {"question_id": str(q.id), "analysis": draft["analysis"],
                "errors": draft.get("errors") or [], "existing": None, "staged": True}
    return None


async def suggest_cloze_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为完形逐空生成双轴解析**建议**并暂存(meta.analysis_draft):载体槽程序判,线索类型/线索句 LLM+校验。"""
    pairs = await _load_with_context(db, question_ids)
    clue_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name).where(sa.or_(
                KnowledgeNode.code.like("rc-4%"), KnowledgeNode.code.like("rc-6%"),
                KnowledgeNode.name == "情景交际用语",
            )).order_by(KnowledgeNode.code))).all())
    # 1) LLM 建议:逐空并发(慢、网络、互不依赖),避免一篇十几空串行必超时
    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_cloze_suggestion(q, context), None
            return await _llm_cloze_suggestion(q, context, clue_catalog), None
        except Exception as exc:  # noqa: BLE001 单空失败不拖垮整批
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    # 2) 校验 + 图谱查:用共享 db 串行(单会话不可并发)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        from app.services.logic_display_service import ensure_analysis_logic_stem
        ensure_analysis_logic_stem(q, ana, passage=context, context_text=context)
        errs = validate_cloze_analysis(
            ana, context_text=context, answer_words=_answer_words_for_logic_stem(q, ana))
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        _stage_draft(q, ana, errs)      # 暂存(随 suggest 端点一次 commit)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


_WRITING_SYSTEM = (
    "你是中小学英语写作测评专家。对给定的书面表达真题做「写作解析」,产出教学与仿真所需的结构,"
    "**重点是给学生一套「照着能写」的套路**,只返回 JSON:"
    '{"genre":"体裁","sub_format":"具体文体(如 演讲稿/书信/通知,可空)",'
    '"points":[{"id":1,"point":"要点(从题目提示逐条抽,一条一句)"}],'
    '"main_tense":"主时态","wr_codes":["写作考点编码(从目录挑)"],'
    '"strategy":"一句话套路名(好记的公式,如 三段式演讲稿:问候引题→分点论述→升华号召)",'
    '"structure":[{"role":"段落角色(开头/主体1/主体2/结尾…)","guide":"该段写什么+给出现成开头语/连接词/句式模板句(学生照着套)","point_ids":[该段落实哪些要点的id]}],'
    '"model_essay":"符合要求的范文(覆盖全部要点、词数达标)",'
    '"point_map":{"1":"范文中落实该要点的那句"},'
    '"target_expressions":["范文里用到的高级句型/词块(必须逐字取自范文)"],'
    '"pitfalls":[{"type":"错因类型(时态/中式英语/搭配等)","trap":"本题学生常见失分点"}]}。'
    "体裁只能取:" + "、".join(WRITING_GENRES) + ";主时态只能取:" + "、".join(WRITING_TENSES) + "。"
    "★铁律:target_expressions 每条必须是 model_essay 里**逐字**出现的片段(会用程序在范文里做子串比对,凑不出即判幻觉作废)。"
    "points 必须齐全且切题;范文必须覆盖所有 points;structure 的套路要通用于该体裁(仿真同体裁题可复用),"
    "guide 里要给可直接照抄的开头语/连接词/句式,让弱基础学生也能套着写。"
)


def _mock_writing_suggestion(q: PlatformQuestion, context: str) -> dict:
    essay = "This is a mock model essay. Only by working hard can we grow. I am grateful to my parents."
    return {
        "genre": "应用文", "sub_format": "演讲稿",
        "points": [{"id": 1, "point": "mock 要点一"}, {"id": 2, "point": "mock 要点二"}],
        "main_tense": "一般现在时", "wr_codes": ["wr-1-2", "wr-4-1"],
        "strategy": "三段式演讲稿:问候引题 → 分点论述 → 升华号召",
        "structure": [
            {"role": "开头", "guide": "问候+引出主题:Good morning! Today I'd like to talk about…", "point_ids": []},
            {"role": "主体", "guide": "分点论述,用 Firstly,… Besides,… 展开要点", "point_ids": [1, 2]},
            {"role": "结尾", "guide": "升华+号召:In a word,… Let's…", "point_ids": []},
        ],
        "model_essay": essay, "point_map": {"1": "Only by working hard can we grow."},
        "target_expressions": ["Only by working hard can we grow"],
        "pitfalls": [{"type": "时态", "trap": "演讲稿主时态用一般现在,学生易误用过去时"}],
    }


async def _llm_writing_suggestion(q: PlatformQuestion, context: str, wr_catalog: str) -> dict:
    user = (f"【写作考点目录】\n{wr_catalog}\n\n【题目(含提示/要点表)】\n{context[:3500]}\n"
            f"【参考范文(有则据此,无则你写)】{(q.answer or '(原卷无范文,请生成符合要求的范文)')[:1500]}")
    # complete_json:范文长易截断→升档;JSON 破损/无范文(validate)→重试
    ana = await complete_json(
        system_prompt=_WRITING_SYSTEM, user_prompt=user, max_tokens=2200,
        escalate_ceiling=4400, validate=lambda d: bool((d.get("model_essay") or "").strip()),
        feature="writing_analysis")
    if ana is None:
        raise ValueError("LLM 未产出有效写作解析(截断/抖动重试后仍失败),可点「AI 重新解析」重试")
    return ana


async def suggest_writing_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为书面表达生成「写作解析」**建议**并暂存(meta.analysis_draft):要点/体裁/范文/目标句型 LLM+校验。"""
    pairs = await _load_with_context(db, question_ids)
    wr_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name)
            .where(KnowledgeNode.code.like("wr-%")).order_by(KnowledgeNode.code))).all())

    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_writing_suggestion(q, context), None
            return await _llm_writing_suggestion(q, context, wr_catalog), None
        except Exception as exc:  # noqa: BLE001
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        errs = validate_writing_analysis(ana, context_text=context)
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("wr_codes") or [])
            if missing:
                errs = [f"wr_codes 不在图谱:{','.join(missing)}"]
        _stage_draft(q, ana, errs)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


_GRAMMAR_MC_SYSTEM = (
    "你是中小学英语语法命题测评专家。对给定的语法单项选择题做「题目层解析」——考的是词法/句法(时态/非谓语/"
    "从句/介词/情态/搭配等),不是话题。只返回 JSON:"
    '{"kp_codes":["考点编码(从目录挑,词法 cf- / 句法 jf-)"],'
    '"answer_reason":"正确项命中哪条语法/搭配规则(1-2句)",'
    '"distractors":{"A":{"meaning":"该选项的形态/义(中文)","why_wrong":"为何错——违反哪条规则(时态不符/搭配错/结构非法等)"},...}}。'
    "distractors 只列**非正确项**;每项 meaning(它是什么)+why_wrong(违反的规则)双全。"
    "kp_codes 必须来自给定目录且为 cf-/jf- 编码。"
)


def _mock_grammar_mc_suggestion(q: PlatformQuestion, context: str) -> dict:
    ans = (q.answer or "").strip().upper()
    opts = q.options if isinstance(q.options, list) else []
    dss = {chr(65 + i): {"meaning": f"mock 形态{i}", "why_wrong": "mock:与本句时态/搭配不符"}
           for i in range(len(opts)) if chr(65 + i) != ans}
    return {"kp_codes": ["jf-1-1"], "answer_reason": "dev-mock:命中该语法规则。", "distractors": dss}


async def _llm_grammar_mc_suggestion(q: PlatformQuestion, context: str, gram_catalog: str) -> dict:
    opts = json.dumps(q.options, ensure_ascii=False) if q.options else "(选项在题干)"
    user = (f"【词法/句法考点目录】\n{gram_catalog}\n\n【题目】{q.stem}\n【选项】{opts}\n【正确答案】{q.answer or '未知'}")
    data = await complete_json(
        system_prompt=_GRAMMAR_MC_SYSTEM, user_prompt=user, max_tokens=1200, escalate_ceiling=2400,
        validate=lambda d: bool(d.get("kp_codes")), feature="grammar_mc_analysis")
    return data or {}


async def suggest_grammar_mc_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为语法单选生成「题目层解析」建议并暂存:cf-/jf- 考点 + 答案规则依据 + 干扰项违规机制。"""
    pairs = await _load_with_context(db, question_ids)
    gram_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name).where(sa.or_(
                KnowledgeNode.code.like("cf-%"), KnowledgeNode.code.like("jf-%")))
            .order_by(KnowledgeNode.code))).all())

    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_grammar_mc_suggestion(q, context), None
            return await _llm_grammar_mc_suggestion(q, context, gram_catalog), None
        except Exception as exc:  # noqa: BLE001
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        errs = validate_grammar_mc_analysis(ana)
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        _stage_draft(q, ana, errs)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


_WORD_FILL_SYSTEM = (
    "你是中小学英语语法/词汇测评专家。对给定的「用所给词的适当形式填空」题(动词填空/词汇运用/单词拼写)做题目层解析——"
    "考的是**词形变化**(时态/语态/非谓语/主谓一致/名词复数/所有格/形容词副词级/派生构词)。只返回 JSON:"
    '{"given":"所给原词(括号里给的词,如 divide)","target_form":"应填的正确形式(如 was dividing)",'
    '"logic_stem":"单独逻辑题挖空句:把题干里括号所给词 (divide) 换成 ____ ,其余与题干一致",'
    '"change_type":"词形变化类型(如 过去进行时/被动语态/名词复数/形容词比较级/动词→名词派生)",'
    '"kp_codes":["考点编码(词法 cf- / 句法 jf-)"],"answer_reason":"定形依据(据什么线索定这个形式:时间状语/主句时态/主谓一致/语义)"}。'
    "kp_codes 必须来自给定目录且为 cf-/jf- 编码;change_type 精确到具体变化。"
    "logic_stem 不得填入 target_form,须保留 ____ 挖空。"
)


def _mock_word_fill_suggestion(q: PlatformQuestion, context: str) -> dict:
    given = "divide"
    stem = q.stem or ""
    logic = re.sub(rf"\(\s*{re.escape(given)}\s*\)", "____", stem, count=1, flags=re.I)
    if logic == stem:
        logic = f"{stem} ____" if stem else "____"
    return {"given": given, "target_form": q.answer or "was dividing", "logic_stem": logic,
            "change_type": "过去进行时", "kp_codes": ["jf-3-1-3"],
            "answer_reason": "dev-mock:据时间线索定时态。"}


async def _llm_word_fill_suggestion(q: PlatformQuestion, context: str, cat: str) -> dict:
    user = (f"【词法/句法考点目录】\n{cat}\n\n【题目(含所给词)】{q.stem}\n【参考答案】{q.answer or '未知'}")
    data = await complete_json(
        system_prompt=_WORD_FILL_SYSTEM, user_prompt=user, max_tokens=1000, escalate_ceiling=2000,
        validate=lambda d: bool(d.get("kp_codes") and (d.get("change_type") or "").strip()),
        feature="word_fill_analysis")
    return data or {}


async def suggest_word_fill_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为填空词形类(动词填空/词汇运用/单词拼写)生成解析建议:词形变化类型 + cf/jf 考点 + 定形依据。"""
    pairs = await _load_with_context(db, question_ids)
    cat = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name).where(sa.or_(
                KnowledgeNode.code.like("cf-%"), KnowledgeNode.code.like("jf-%")))
            .order_by(KnowledgeNode.code))).all())

    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_word_fill_suggestion(q, context), None
            return await _llm_word_fill_suggestion(q, context, cat), None
        except Exception as exc:  # noqa: BLE001
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        from app.services.logic_display_service import ensure_analysis_logic_stem
        ensure_analysis_logic_stem(
            q, ana, passage=context, context_text=context or (q.stem or ""))
        errs = validate_word_fill_analysis(
            ana, context_text=context or (q.stem or ""),
            answer_words=_answer_words_for_logic_stem(q, ana))
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        _stage_draft(q, ana, errs)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


_PASSAGE_FILL_SYSTEM = (
    "你是中小学英语短文填空(开放填空)测评专家。整篇短文挖空、学生按语境填词——被测的是「语境线索」。"
    "对给定空做解析,只返回 JSON:"
    '{"clue_type":"线索类型","clue":"决定答案的线索句(必须逐字摘自短文)",'
    '"logic_stem":"单独逻辑题挖空句(根据短文改写/生成、自足可读、含 ____ 、禁止填入 answer_word)",'
    '"answer_word":"应填的词","kp_codes":["考点编码(cf-/jf-/rc-,线索轴为主)"]}。'
    "线索类型只能取:" + "、".join(CLUE_TYPES) + "。"
    "★clue 必须从【短文】里**逐字复制**一句(或连续一小段),不得改写/翻译/拼接;程序会做子串比对,凑不出即判幻觉。"
    "★logic_stem 与 clue 分工:clue=证据句(原文子串);logic_stem=给学生单独作答的**自足挖空题干**,"
    "**允许且应当根据短文改写/生成**,消解 it/they 等指代为具体名词,补足场景,使学生不看短文也能选对;"
    "语义忠实本空;挖空用 ____ ;不得填入 answer_word。"
)


def _mock_passage_fill_suggestion(q: PlatformQuestion, context: str) -> dict:
    from app.services.logic_display_service import (
        _normalize_blank_markers, _sentence_with_blank_from_passage,
    )
    first = re.split(r"(?<=[.!?])\s+", context.strip())[0][:200]
    logic = _sentence_with_blank_from_passage(context, q.question_no)
    if not logic:
        logic = _normalize_blank_markers(first) or (
            "The girl ____ the little plant every morning.")
    return {"clue_type": "跨句词汇复现", "clue": first, "logic_stem": logic,
            "answer_word": q.answer or "word", "kp_codes": ["rc-4-1"]}


async def _llm_passage_fill_suggestion(q: PlatformQuestion, context: str, clue_catalog: str) -> dict:
    user = (f"【线索轴考点目录】\n{clue_catalog}\n\n【短文(空格即本题)】\n{context[:3500]}\n\n"
            f"【本空题干】{q.stem}\n【参考答案】{q.answer or '未知(请按语境推断)'}")
    ana = await complete_json(
        system_prompt=_PASSAGE_FILL_SYSTEM, user_prompt=user, max_tokens=1400, escalate_ceiling=2800,
        validate=lambda d: bool((d.get("clue") or "").strip()),
        feature="passage_fill_analysis")
    if ana is None:
        raise ValueError("LLM 未产出有效解析(截断/抖动重试后仍失败),可点「改」重试")
    return ana


async def suggest_passage_fill_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为短文填空(开放填空)生成解析建议:线索类型 + 线索句(短文子串)+ 应填词 + 线索轴考点。"""
    pairs = await _load_with_context(db, question_ids)
    clue_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name).where(sa.or_(
                KnowledgeNode.code.like("cf-%"), KnowledgeNode.code.like("jf-%"),
                KnowledgeNode.code.like("rc-4%"), KnowledgeNode.code.like("rc-6%")))
            .order_by(KnowledgeNode.code))).all())

    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_passage_fill_suggestion(q, context), None
            return await _llm_passage_fill_suggestion(q, context, clue_catalog), None
        except Exception as exc:  # noqa: BLE001
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        from app.services.logic_display_service import ensure_analysis_logic_stem
        ensure_analysis_logic_stem(q, ana, passage=context, context_text=context)
        errs = validate_passage_fill_analysis(ana, context_text=context)
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        _stage_draft(q, ana, errs)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


_SENTENCE_SYSTEM = (
    "你是中小学英语句法测评专家。对给定的「完成句子/句子翻译/句型转换」题做题目层解析——考的是**句法结构**"
    "(时态/语态/从句/非谓语/强调/倒装/固定句型)。只返回 JSON:"
    '{"target_structure":"目标句型/结构(如 宾语从句/被动语态/It is … that 强调句/not … until)",'
    '"kp_codes":["考点编码(句法 jf- / 词法 cf-)"],'
    '"key_points":["采分点(必须写对的结构/连接词/形态,逐条)"],'
    '"answer":"参考答案(完整英文句)"}。'
    "kp_codes 必须来自给定目录且为 jf-/cf- 编码;key_points 精确到具体采分点。"
)


def _mock_sentence_suggestion(q: PlatformQuestion, context: str) -> dict:
    return {"target_structure": "一般过去时", "kp_codes": ["jf-3-2-3"],
            "key_points": ["谓语动词过去式", "语序"], "answer": q.answer or "It was made of wood."}


async def _llm_sentence_suggestion(q: PlatformQuestion, context: str, cat: str) -> dict:
    user = (f"【词法/句法考点目录】\n{cat}\n\n【题目(含中文提示/所给词)】{q.stem}\n【参考答案】{q.answer or '未知'}")
    data = await complete_json(
        system_prompt=_SENTENCE_SYSTEM, user_prompt=user, max_tokens=1200, escalate_ceiling=2400,
        validate=lambda d: bool(d.get("kp_codes") and (d.get("target_structure") or "").strip()),
        feature="sentence_analysis")
    return data or {}


async def suggest_sentence_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为完成句子/翻译/句型转换生成解析建议:目标句型 + jf/cf 考点 + 采分点 + 参考答案。"""
    pairs = await _load_with_context(db, question_ids)
    cat = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name).where(sa.or_(
                KnowledgeNode.code.like("cf-%"), KnowledgeNode.code.like("jf-%")))
            .order_by(KnowledgeNode.code))).all())

    async def _gen(q, context):
        try:
            if is_llm_dev_mode():
                return _mock_sentence_suggestion(q, context), None
            return await _llm_sentence_suggestion(q, context, cat), None
        except Exception as exc:  # noqa: BLE001
            return None, f"生成失败:{exc}"
    gens = await _gather_bounded(
        [_gen(q, ctx) for q, ctx in pairs], limit=_LLM_CONCURRENCY)
    out = []
    for (q, context), (ana, gen_err) in zip(pairs, gens):
        existing = (q.meta or {}).get("analysis")
        if gen_err:
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [gen_err], "existing": existing})
            continue
        errs = validate_sentence_analysis(ana)
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        _stage_draft(q, ana, errs)
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


async def suggest_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID], force: bool = False
) -> list[dict]:
    """按题型分发解析建议并**暂存**:完型→双轴;阅读→rc技能+定位句。
    force=False(默认):已确认/已暂存的直接秒读(不跑 LLM),只对没解析过的生成;
    force=True:全部重跑(「重新解析」)。完型判定 = question_type 或 section 含完形/完型。"""
    qrows = (await db.execute(sa.select(PlatformQuestion).where(
        PlatformQuestion.id.in_(question_ids)))).scalars().all()
    qmap = {q.id: q for q in qrows}

    def _is_cloze(q: PlatformQuestion) -> bool:
        qt, sec = q.question_type, q.section
        return (qt or "") == "完型" or "完形" in (sec or "") or "完型" in (sec or "")

    def _is_writing(q: PlatformQuestion) -> bool:
        qt, sec = q.question_type, q.section
        return (qt or "") == "写作" or "书面" in (sec or "") or "写作" in (sec or "")

    def _is_grammar_mc(q: PlatformQuestion) -> bool:
        # 语法单选(词法/句法):题型单选,且不是阅读理解/听力/动词填空词形段
        sec = q.section or ""
        if stem_looks_word_fill(q.stem or "") or _section_is_word_fill(sec):
            return False
        return (q.question_type or "") == "单选" and "阅读" not in sec and "听力" not in sec

    import re as _re
    def _is_word_fill(q: PlatformQuestion) -> bool:
        # 填空词形类(动词填空/词汇运用):段名或题干 (所给词) 形态
        sec = q.section or ""
        if stem_looks_word_fill(q.stem or ""):
            return True
        if (q.question_type or "") != "填空":
            return False
        if _re.search(r"短文|完成句子|翻译|句型转换|缺词|完形|完型", sec):
            return False
        return _section_is_word_fill(sec)

    def _is_passage_fill(q: PlatformQuestion) -> bool:
        # 短文填空/缺词填空(开放填空):填空题 + 短文/缺词段
        sec = q.section or ""
        return (q.question_type or "") == "填空" and bool(_re.search(r"短文|缺词", sec))

    def _is_sentence(q: PlatformQuestion) -> bool:
        # 完成句子/翻译/句型转换(句法结构):填空题 + 完成句子/翻译/句型转换段
        sec = q.section or ""
        return (q.question_type or "") == "填空" and bool(_re.search(r"完成句子|翻译|句型转换|根据.*中文", sec))

    cached: dict[str, dict] = {}
    to_gen: list[uuid.UUID] = []
    for qid in question_ids:
        q = qmap.get(qid)
        if q is None:
            continue
        ci = None if force else _cached_item(q)      # 已确认/已暂存 → 秒读
        if ci is not None:
            cached[str(qid)] = ci
        else:
            to_gen.append(qid)

    gen: list[dict] = []
    if to_gen:
        cloze_ids = [i for i in to_gen if _is_cloze(qmap[i])]
        rest = [i for i in to_gen if not _is_cloze(qmap[i])]
        writing_ids = [i for i in rest if _is_writing(qmap[i])]
        rest2 = [i for i in rest if not _is_writing(qmap[i])]
        grammar_ids = [i for i in rest2 if _is_grammar_mc(qmap[i])]
        rest3 = [i for i in rest2 if not _is_grammar_mc(qmap[i])]
        wordfill_ids = [i for i in rest3 if _is_word_fill(qmap[i])]
        passfill_ids = [i for i in rest3 if not _is_word_fill(qmap[i]) and _is_passage_fill(qmap[i])]
        rest4 = [i for i in rest3 if not _is_word_fill(qmap[i]) and not _is_passage_fill(qmap[i])]
        sentence_ids = [i for i in rest4 if _is_sentence(qmap[i])]
        reading_ids = [i for i in rest4 if not _is_sentence(qmap[i])]
        if cloze_ids:
            gen += await suggest_cloze_analysis(db, question_ids=cloze_ids)
        if writing_ids:
            gen += await suggest_writing_analysis(db, question_ids=writing_ids)
        if grammar_ids:
            gen += await suggest_grammar_mc_analysis(db, question_ids=grammar_ids)
        if wordfill_ids:
            gen += await suggest_word_fill_analysis(db, question_ids=wordfill_ids)
        if passfill_ids:
            gen += await suggest_passage_fill_analysis(db, question_ids=passfill_ids)
        if sentence_ids:
            gen += await suggest_sentence_analysis(db, question_ids=sentence_ids)
        if reading_ids:
            gen += await suggest_reading_analysis(db, question_ids=reading_ids)
        await db.commit()        # 暂存落库(生成的建议写进 meta.analysis_draft)

    by_id = {**cached, **{it["question_id"]: it for it in gen}}
    order = {str(q): i for i, q in enumerate(question_ids)}
    items = sorted(by_id.values(), key=lambda it: order.get(it["question_id"], 999))
    # 挂词预览 + 单独逻辑题;旧暂存缺 logic_stem → ensure 回填并刷新 errors 后落库
    from app.services import option_vocab_service as ovs
    from app.services.logic_display_service import (
        compose_logic_display, ensure_analysis_logic_stem,
    )
    qlist = [qmap[uuid.UUID(str(it["question_id"]))] for it in items
             if it.get("question_id") and uuid.UUID(str(it["question_id"])) in qmap]
    pmap = await _passage_map(db, qlist)
    draft_touched = False
    for it in items:
        q = qmap.get(uuid.UUID(str(it["question_id"]))) if it.get("question_id") else None
        if q is None:
            it["option_vocab"] = {"correct": [], "distractor": [], "unresolved": False}
            it["logic_display"] = {"ready": False}
            continue
        try:
            ana = it.get("analysis") or (it.get("existing") if isinstance(it.get("existing"), dict) else None)
            it["option_vocab"] = ovs.preview_option_vocab(q, analysis=ana)
            passage = pmap.get(q.block_id) if q.block_id else None
            # 仅暂存草稿做 ensure+重校验落库;已确认解析不在此改写
            if isinstance(ana, dict) and it.get("analysis") is ana and it.get("staged"):
                ensure_analysis_logic_stem(
                    q, ana, passage=passage, vocab_preview=it["option_vocab"],
                    context_text=passage or (q.stem or ""))
                ctx = passage or (q.stem or "")
                if ana.get("clue_type") and isinstance(ana.get("distractors"), dict):
                    it["errors"] = validate_cloze_analysis(
                        ana, context_text=ctx,
                        answer_words=_answer_words_for_logic_stem(q, ana))
                elif ana.get("clue_type"):
                    it["errors"] = validate_passage_fill_analysis(ana, context_text=ctx)
                elif ana.get("change_type"):
                    it["errors"] = validate_word_fill_analysis(
                        ana, context_text=ctx,
                        answer_words=_answer_words_for_logic_stem(q, ana))
                _stage_draft(q, ana, it.get("errors") or [])
                draft_touched = True
            it["logic_display"] = compose_logic_display(
                q, ana, passage=passage, vocab_preview=it["option_vocab"])
        except Exception:  # noqa: BLE001
            it["option_vocab"] = {"correct": [], "distractor": [], "unresolved": False}
            it["logic_display"] = {"ready": False}
    if draft_touched:
        await db.commit()
    return items


async def confirm_analysis(
    db: AsyncSession, *, question_id: uuid.UUID, analysis: dict, admin_id: uuid.UUID,
    force: bool = False,
) -> dict:
    """人工确认后写库(唯一写入口):按解析形态分发校验(完形=clue_type;阅读=rc_code)→
    meta.analysis(带确认者/时间)。

    force=True:人工判定校验为误报(如定位句实为原文但子串比对过严),忽略校验强制写库;
    被忽略的错误记入 meta.analysis.validation_skipped 留审计,不静默吞掉。"""
    q = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="题目不存在")
    pairs = await _load_with_context(db, [question_id])
    context = pairs[0][1]
    from app.services.logic_display_service import ensure_analysis_logic_stem
    if "clue_type" in analysis and "distractors" in analysis:   # 完形双轴(有干扰项)
        if analysis.get("slot"):                       # 手输/旧建议的「动词短语」等归一到枚举
            analysis = {**analysis, "slot": normalize_slot(analysis.get("slot"))}
        ensure_analysis_logic_stem(q, analysis, passage=context, context_text=context)
        errs = validate_cloze_analysis(
            analysis, context_text=context,
            answer_words=_answer_words_for_logic_stem(q, analysis))
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "cloze"}
    elif "clue_type" in analysis:                     # 短文填空(开放填空,线索轴无干扰项)
        ensure_analysis_logic_stem(q, analysis, passage=context, context_text=context)
        errs = validate_passage_fill_analysis(analysis, context_text=context)
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "passage_fill"}
    elif "genre" in analysis:                         # 书面表达写作解析
        errs = validate_writing_analysis(analysis, context_text=context)
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("wr_codes") or [])
            if missing:
                errs = [f"wr_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "writing"}
    elif "rc_code" in analysis:                       # 阅读题目层解析
        errs = validate_reading_analysis(analysis, context_text=context)
        if not errs and not await _rc_code_exists(db, analysis.get("rc_code", "")):
            errs = [f"rc_code 不在图谱:{analysis.get('rc_code')}"]
        analysis = {**analysis, "kind": "reading"}
    elif "change_type" in analysis:                   # 填空词形类(动词填空/词汇运用/单词拼写)
        ensure_analysis_logic_stem(
            q, analysis, passage=context, context_text=context or (q.stem or ""))
        errs = validate_word_fill_analysis(
            analysis, context_text=context or (q.stem or ""),
            answer_words=_answer_words_for_logic_stem(q, analysis))
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "word_fill"}
    elif "target_structure" in analysis:              # 完成句子/翻译/句型转换(句法结构)
        errs = validate_sentence_analysis(analysis)
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "sentence"}
    else:                                             # 语法单选(词法/句法):kp_codes(cf-/jf-)+ 干扰机制
        errs = validate_grammar_mc_analysis(analysis)
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "grammar_mc"}
    if errs and not force:
        raise AppError(code=400, message="解析未通过校验:" + ";".join(errs))
    saved = {**analysis,
             "confirmed_by": str(admin_id),
             "confirmed_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    if errs:                       # force 写库:留审计,标明是人工忽略了哪些校验
        saved["validation_skipped"] = errs
    # 把解析里的考点码挂成 platform_question_kp 边(幂等·附加):让 BKT/仿真继承考点/学情统计都吃到
    # 完形→kp_codes、写作→wr_codes、阅读→rc_code。force 跳过校验时,只挂图谱里真实存在的码。
    codes = (analysis.get("kp_codes") or []) if saved["kind"] in ("cloze", "grammar_mc", "word_fill", "passage_fill", "sentence") else \
            (analysis.get("wr_codes") or []) if saved["kind"] == "writing" else \
            [analysis.get("rc_code")]
    codes = [c for c in codes if c and str(c).strip()]
    if codes:
        from app.services.platform_question_service import attach_node
        node_ids = (await db.execute(
            sa.select(KnowledgeNode.id).where(KnowledgeNode.code.in_(codes)))).scalars().all()
        for nid in node_ids:
            await attach_node(db, question_id, nid)
    # 选项挂词(主考/干扰):程序抽取,best-effort,不挡解析;answer 空则反推并回写
    attach_res = {"attached": 0, "correct": 0, "distractor": 0}
    from app.services import option_vocab_service as ovs
    try:
        async with db.begin_nested():
            attach_res = await ovs.attach_platform_option_vocab(
                db, question=q, analysis_kind=saved.get("kind"),
                analysis=saved, writeback_answer=True)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("option vocab attach failed q=%s: %s", question_id, exc)
    from app.services.logic_display_service import compose_logic_display, ensure_analysis_logic_stem
    pmap = await _passage_map(db, [q])
    passage = pmap.get(q.block_id) if q.block_id else None
    ensure_analysis_logic_stem(q, saved, passage=passage, context_text=passage or (q.stem or ""))
    vocab_preview = ovs.preview_option_vocab(q, saved)
    ld = compose_logic_display(q, saved, passage=passage, vocab_preview=vocab_preview)
    ready = (
        not saved.get("validation_skipped")
        and attach_res.get("correct", 0) > 0
        and bool(ld.get("ready"))
        and saved.get("kind") in ("grammar_mc", "cloze", "word_fill", "passage_fill")
    )
    # 一次写全 analysis(含 ready/logic_display)。禁止先写 meta 再改 saved:
    # SQLAlchemy JSONB 对嵌套 dict 二次赋值常不落库 → 统计永远看不到 option_vocab_ready。
    from sqlalchemy.orm.attributes import flag_modified
    final_ana = {
        **saved,
        "logic_display": ld,
        "option_vocab_ready": ready,
    }
    new_meta = {**(q.meta or {}), "analysis": final_ana}
    new_meta.pop("analysis_draft", None)      # 确认即正式保存,清掉暂存草稿
    q.meta = new_meta
    flag_modified(q, "meta")
    await db.flush()
    return final_ana


async def confirm_analysis_batch(
    db: AsyncSession, *, items: list[dict], admin_id: uuid.UUID,
) -> dict:
    """批量确认写库(降人工):逐条复用 confirm_analysis 的硬校验;通过的写库、失败的收原因。
    每条独立 savepoint,一条异常不毒化后续。返回 {confirmed, failed}。"""
    confirmed: list[str] = []
    failed: list[dict] = []
    for it in items:
        qid = it.get("question_id")
        ana = it.get("analysis")
        try:
            async with db.begin_nested():
                await confirm_analysis(
                    db, question_id=uuid.UUID(str(qid)), analysis=ana or {}, admin_id=admin_id)
            confirmed.append(str(qid))
        except AppError as exc:
            failed.append({"question_id": str(qid), "error": exc.message})
        except Exception as exc:  # noqa: BLE001
            failed.append({"question_id": str(qid), "error": f"异常:{exc}"})
    return {"confirmed": confirmed, "failed": failed}
