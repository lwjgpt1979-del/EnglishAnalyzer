"""长难句解析服务(L1):长句判定 + AI 结构拆解 + 平台真题抽取(挂句法 node)。

抽取来源由配置 long_sentence.sources 控(默认 ['platform_real']);三来源同构,L1 实现平台真题。
句子有源(记 source 指针),AI 拆解出主干/分层/译文/句法点 → match_kp 挂句法 knowledge_nodes。
dev 模式拆解走确定性 mock(按结构信号词推句法点),不调真实 LLM。
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d12_v2_exams import ExamPaper  # noqa: F401 (确保枚举注册)
from app.models.d16_question_domain import PlatformQuestion
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services.kp_match_service import match_kp
from app.services.llm_provider import chat_completion, complete_json, fast_model, is_llm_dev_mode

_log = logging.getLogger(__name__)

DEFAULT_MIN_WORDS = 20

# 结构信号词 → 句法点名(dev 启发式拆解 + 长句判定共用;裸 -ing/-ed 太宽,非谓语交真 LLM 识别)
_SIGNALS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(which|whom|whose|that|who)\b", re.I), "定语从句"),
    (re.compile(r"\b(because|although|though|while|when|since|unless|if|whereas)\b", re.I), "状语从句"),
    (re.compile(r"\b(what|whether|how|why)\b", re.I), "名词性从句"),
]


@dataclass
class ExtractStats:
    scanned: int = 0
    sentences: int = 0
    long_kept: int = 0
    created: int = 0
    skipped_done: int = 0
    edges: int = 0
    candidates: int = 0
    syntax_points: set = field(default_factory=set)

    def report(self, dry: bool) -> None:
        tag = "[dry-run] 预计" if dry else "[done]"
        print(f"\n{tag}: 扫真题 {self.scanned} / 切句 {self.sentences} / 长句 {self.long_kept} / "
              f"新建长难句 {self.created} / 跳过(已抽) {self.skipped_done} / 挂node边 {self.edges} / "
              f"未命中候选 {self.candidates}")


# ── L5 后台:审核 + 配置 ──────────────────────────────────────
def _cfg_defaults() -> dict:
    return {
        "long_sentence.sources": ["platform_real"],
        "long_sentence.verify_types": _ALL_VERIFY_TYPES,
        "long_sentence.min_words": DEFAULT_MIN_WORDS,
        "long_sentence.required_pass": DEFAULT_REQUIRED_PASS,
        "long_sentence.textbook_difficulty_min": None,  # 教材:难度超过此值的全抽(空=不按阈值)
        "long_sentence.textbook_top_n": 3,              # 教材:无阈值时,每篇阅读取最难 N 句
    }


async def get_config(db: AsyncSession) -> dict:
    """长难句后台配置(缺失回落默认)。"""
    from app.models.d9_system import SystemConfig
    defaults = _cfg_defaults()
    rows = dict((r.key, r.value) for r in (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key.in_(list(defaults)))
    )).scalars().all())
    return {k.split(".", 1)[1]: rows.get(k, v) for k, v in defaults.items()}


async def set_config(db: AsyncSession, *, updated_by: uuid.UUID, sources=None, verify_types=None,
                     min_words=None, required_pass=None, textbook_difficulty_min=...,
                     textbook_top_n=None) -> dict:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d9_system import SystemConfig
    updates = {"long_sentence.sources": sources, "long_sentence.verify_types": verify_types,
               "long_sentence.min_words": min_words, "long_sentence.required_pass": required_pass,
               "long_sentence.textbook_top_n": textbook_top_n}
    # 阈值用 ... 哨兵区分「不改」与「显式清空(None)」
    if textbook_difficulty_min is not ...:
        updates["long_sentence.textbook_difficulty_min"] = textbook_difficulty_min
    for key, val in updates.items():
        if val is None and key != "long_sentence.textbook_difficulty_min":
            continue
        await db.execute(
            pg_insert(SystemConfig).values(id=uuid.uuid4(), key=key, value=val, updated_by=updated_by)
            .on_conflict_do_update(index_elements=["key"], set_={"value": val, "updated_by": updated_by}))
    await db.flush()
    return await get_config(db)


async def list_for_review(
    db: AsyncSession, *, status: str = "draft", node_id: uuid.UUID | None = None,
    skip: int = 0, limit: int = 20, sort_by: str = "created_at", order: str = "asc",
    source_kind: str | None = None, textbook_version: str | None = None,
    stage: str | None = None, grade: str | None = None, semester: str | None = None,
    exam_type: str | None = None,
) -> tuple[list[LongSentence], int]:
    base = sa.select(LongSentence).where(LongSentence.status == status)
    if node_id is not None:
        base = base.join(LongSentenceNode, LongSentenceNode.long_sentence_id == LongSentence.id).where(
            LongSentenceNode.node_id == node_id)
    if source_kind:
        base = base.where(LongSentence.source_kind == source_kind)
    if textbook_version:
        base = base.where(LongSentence.textbook_version == textbook_version)
    if stage:
        base = base.where(LongSentence.stage == stage)
    if grade:
        base = base.where(LongSentence.grade == grade)
    if semester:
        base = base.where(LongSentence.semester == semester)
    if exam_type:
        base = base.where(LongSentence.exam_type == exam_type)
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    col = LongSentence.difficulty if sort_by == "difficulty" else LongSentence.created_at
    direction = col.desc() if order == "desc" else col.asc()
    rows = (await db.execute(
        base.order_by(direction.nulls_last()).offset(skip).limit(limit))).scalars().all()
    return list(rows), total


async def review(db: AsyncSession, *, ls_id: uuid.UUID, approve: bool) -> LongSentence:
    from app.core.exceptions import AppError
    ls = (await db.execute(sa.select(LongSentence).where(LongSentence.id == ls_id))).scalar_one_or_none()
    if ls is None:
        raise AppError(code=404, message="长难句不存在")
    ls.status = "published" if approve else "retired"
    await db.flush()
    return ls


async def reanalyze_one(db: AsyncSession, *, ls_id: uuid.UUID, publish: bool = False) -> bool:
    """重新解析一条长难句:刷新 analysis_json 为新结构(分段/结构/成分/词汇/语法点);可选发布。"""
    ls = (await db.execute(sa.select(LongSentence).where(LongSentence.id == ls_id))).scalar_one_or_none()
    if ls is None:
        return False
    analysis = await analyze_sentence(ls.text)
    comp = syntactic_complexity(ls.text)
    analysis["difficulty"] = comp["difficulty"]
    analysis["complexity"] = comp
    ls.analysis_json = analysis
    ls.difficulty = comp["difficulty"]
    if publish:
        ls.status = "published"
    await db.flush()
    return True


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def detect_syntax_points(sentence: str) -> list[str]:
    pts: list[str] = []
    for pat, name in _SIGNALS:
        if pat.search(sentence) and name not in pts:
            pts.append(name)
    return pts


# ── 句法复杂度(spaCy 依存)──────────────────────────────────────────────────
_NLP = None
_NLP_TRIED = False
# 从句性依存:关系从句/状语从句/补语从句/开放补语/主语从句/分词-不定式作定语/介词补语
_CLAUSAL_DEPS = {"relcl", "advcl", "ccomp", "xcomp", "csubj", "csubjpass", "acl", "pcomp"}
_DEPTH_TH = 5     # 句法树深度阈值(达到即判"难")
_MDD_TH = 2.5     # 平均依存距离阈值(长距离修饰 → 难)


def _get_nlp():
    """惰性加载 spaCy 英文模型;不可用时返回 None(降级到信号词规则)。"""
    global _NLP, _NLP_TRIED
    if _NLP_TRIED:
        return _NLP
    _NLP_TRIED = True
    try:
        import spacy
        _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    except Exception as e:  # noqa: BLE001
        logger.warning("[长难句] spaCy 不可用,降级到规则判定: %s", e)
        _NLP = None
    return _NLP


def _tree_depth(token, guard: int = 0) -> int:
    if guard > 60:
        return guard
    children = list(token.children)
    return 1 + max((_tree_depth(c, guard + 1) for c in children), default=0)


def syntactic_complexity(sentence: str, min_words: int = DEFAULT_MIN_WORDS) -> dict:
    """句法复杂度:词数 / 从句数 / 句法树深度 / 平均依存距离(MDD)+ 0–100 难度分。

    spaCy 可用 → 依存分析;否则用信号词规则近似(仍给出值)。难度分:
      score = 6*从句数 + 3.5*树深 + 4*MDD + 0.4*词数,截断到 [0,100]。
    """
    words = re.findall(r"[A-Za-z'\-]+", sentence or "")
    wc = len(words)
    nlp = _get_nlp()
    if nlp is not None and sentence:
        doc = nlp(sentence)
        sents = list(doc.sents)
        span = max(sents, key=lambda s: len(s)) if sents else doc[:]
        toks = list(span)
        clause = sum(1 for t in toks if t.dep_ in _CLAUSAL_DEPS)
        roots = [t for t in toks if t.head == t or t.dep_ == "ROOT"]
        depth = max((_tree_depth(r) for r in roots), default=1)
        dists = [abs(t.i - t.head.i) for t in toks if t.head != t]
        mdd = round(sum(dists) / len(dists), 2) if dists else 0.0
        method = "spacy"
    else:
        clause = len(detect_syntax_points(sentence))   # 近似:命中的从句信号种类数
        depth, mdd, method = 0, 0.0, "rule"
    score = 6 * clause + 3.5 * depth + 4 * mdd + 0.4 * wc
    return {"word_count": wc, "clause_count": clause, "tree_depth": depth,
            "mdd": mdd, "difficulty": max(0, min(100, round(score))), "method": method}


def _is_long(comp: dict, sentence: str, min_words: int) -> bool:
    if comp["word_count"] < min_words:
        return False
    if comp["method"] == "spacy":
        return comp["clause_count"] >= 1 or comp["tree_depth"] >= _DEPTH_TH or comp["mdd"] >= _MDD_TH
    return bool(detect_syntax_points(sentence))


def is_long_sentence(sentence: str, min_words: int = DEFAULT_MIN_WORDS) -> bool:
    """长难句 = 词数达阈值 且 句法上"难"(从句 / 嵌套深 / 长依存;无 spaCy 时回退信号词)。"""
    return _is_long(syntactic_complexity(sentence, min_words), sentence, min_words)


# 句子成分类型 → 固定配色(美学调色板)。设计:8 大语法族各占一个「色相」(状语=橙、定语=绿、
# 主干=蓝、名词性从句=紫、非谓语=青、并列=品红、介词=天蓝、其他=灰);族内按语义小类沿
# 「明度阶梯」细分,每个小类各占一档,保证同类成分全句/跨句颜色统一、又能区分子类。
# 底色 tint 由主色自动调浅(向白混合 88%)生成,各档底色明度一致、清淡不抢字。
def _tint(hex_color: str, white: float = 0.88) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    mix = lambda c: round(c * (1 - white) + 255 * white)
    return "#%02x%02x%02x" % (mix(r), mix(g), mix(b))


# 规则按「具体 → 泛化」排序,命中第一条即返回(顺序敏感)。每条:(关键词元组, 主色)。
_COLOR_RULES: list[tuple[tuple[str, ...], str]] = [
    # ── 名词性从句族:紫(主/宾/表/同位语各一档) ──
    (("主语从句",),               "#6a3fd0"),
    (("宾语从句",),               "#8a5cf0"),
    (("表语从句",),               "#a07ff3"),
    (("同位语",),                 "#b29bf2"),
    (("名词性",),                 "#8a5cf0"),
    # ── 状语族:橙(语义小类沿明度阶梯,深→浅) ──
    (("让步",),                   "#b8601a"),
    (("条件",),                   "#c96a1c"),
    (("原因", "因果"),            "#d1731f"),
    (("时间",),                   "#e08a2f"),
    (("地点",),                   "#e89c4a"),
    (("目的",),                   "#efb15f"),
    (("结果",),                   "#f3c47e"),
    (("方式", "比较", "伴随", "程度"), "#f6d39b"),
    (("状语",),                   "#e08a2f"),   # 其它状语兜底
    # ── 定语族:绿(限制性/非限制性/从句/短语) ──
    (("非限制性定语", "非限定性定语"), "#3bb583"),
    (("限制性定语", "限定性定语"),     "#15805a"),
    (("定语从句", "关系"),         "#1f9d6b"),
    (("定语",),                   "#59c79a"),   # 定语短语/分词作定语
    # ── 非谓语族:青(不定式/现在分词/过去分词/动名词) ──
    (("不定式",),                 "#0a7d88"),
    (("过去分词",),               "#2bb3bf"),
    (("动名词",),                 "#5cc7d0"),
    (("现在分词", "分词", "非谓语"), "#0e9aa7"),
    # ── 介词短语族:天蓝 ──
    (("介词",),                   "#2f9fc4"),
    # ── 并列族:品红(连词/分句/成分) ──
    (("并列连词", "并列关联"),     "#e0529c"),
    (("并列分句", "并列句"),       "#c93d85"),
    (("并列",),                   "#e974ad"),
    # ── 主干族:蓝(主/谓/宾/表各一档) ──
    (("主语",),                   "#1e4fc8"),
    (("谓语",),                   "#3b6fe0"),
    (("宾语",),                   "#5f87e8"),
    (("表语",),                   "#84a4ee"),
    (("主干", "主句", "核心"),     "#3b6fe0"),
    # ── 其他:灰 ──
    (("插入", "独立"),            "#5a6478"),
]
_OTHER_COLOR_HEX = "#6b7688"
_OTHER_COLOR = (_OTHER_COLOR_HEX, _tint(_OTHER_COLOR_HEX))


def component_color(type_str: str | None) -> tuple[str, str]:
    """成分类型名 → (文字色, 底色)。按 _COLOR_RULES 顺序匹配语义小类,同族同色相、子类沿明度细分。"""
    t = type_str or ""
    for keywords, color in _COLOR_RULES:
        if any(k in t for k in keywords):
            return color, _tint(color)
    return _OTHER_COLOR


def _enrich_analysis(data: dict, sentence: str, syntax: list[str]) -> dict:
    """补 syntax_points(给考点匹配用)+ 每段配色(按成分类型固定)+ 兼容旧字段。"""
    gp = data.get("grammar_points") or []
    data.setdefault("syntax_points", [g.get("name") for g in gp if g.get("name")] or syntax)
    segs = data.get("segments") or []
    # 给每段按成分类型附固定颜色(前端直接用,跨句统一)
    for s in segs:
        color, tint = component_color(s.get("type"))
        s["color"] = color
        s["tint"] = tint
    comp = data.get("components") or {}
    # 旧字段兼容(若 LLM 没给)
    data.setdefault("main_clause",
                    " ".join(x for x in [comp.get("subject"), comp.get("predicate"), comp.get("object")] if x))
    data.setdefault("layers", [{"type": s.get("type"), "text": s.get("text")} for s in segs])
    data.setdefault("difficulty_points", [g.get("name") for g in gp if g.get("name")] or syntax)
    return data


async def analyze_sentence(sentence: str) -> dict:
    """AI 多维结构拆解 → analysis_json(适配小程序「长难句学习」UI)。dev 确定性 mock;生产走 LLM。

    产出结构:
      sentence_type  整句类型(主从复合句/并列句/简单句)
      translation    中文翻译;  summary  整体说明
      segments       [{idx,type,text}]  按原文顺序的成分分段(彩色编号显示)
      structure      [{idx,parent}]     成分层级关系(结构树/思维导图)
      components     {subject,predicate,object,...}  句子成分(主干)
      key_words      [{word,pos,meaning}]            重点词汇
      grammar_points [{name,explanation}]            语法点(name 喂考点匹配)
      explanations   [{idx,text}]                    逐条结构解析
    """
    syntax = detect_syntax_points(sentence)
    if is_llm_dev_mode():
        words = sentence.split()
        segs = [{"idx": i + 1, "type": p, "text": sentence} for i, p in enumerate(syntax or ["主句"])]
        res = _enrich_analysis({
            "sentence_type": "主从复合句" if syntax else "简单句",
            "translation": f"[译] {sentence[:30]}…",
            "summary": "mock 结构解析",
            "segments": segs,
            "structure": [{"idx": s["idx"], "parent": None} for s in segs],
            "components": {"subject": " ".join(words[:2]), "predicate": " ".join(words[2:4]), "object": ""},
            "key_words": [{"word": w, "pos": "", "meaning": "mock 释义"} for w in words[:3]],
            "grammar_points": [{"name": p, "explanation": "mock 讲解"} for p in (syntax or ["长句修饰"])],
            "explanations": [{"idx": s["idx"], "text": f"{s['type']} mock 解析"} for s in segs],
        }, sentence, syntax)
        res["paraphrase"] = await generate_paraphrase(sentence, res.get("translation"))
        return res
    system = (
        "你是英语语法专家。把给定长难句做**多维结构化拆解**,供学习 App 展示。严格输出 JSON,所有 type/name/解析用中文。\n"
        "字段要求:\n"
        "1) sentence_type:整句类型(如 主从复合句/并列句/简单句);\n"
        "2) segments:按**原文顺序**把句子切成成分片段,**切得细一些**——每段尽量是一个**最小的短语/从句单位**"
        "(如把'and the wind was howling around'与'the old house'分开、主句主语与谓语分开、目的状语单列),一般 5-10 段;"
        "每段 {idx(从1递增)、type(成分类型,如 让步状语从句/主句主语/主句谓语/非限制性定语从句/限制性定语从句/"
        "介词短语/目的状语/并列谓语/并列连词)、text(该片段原文连续片段,各段拼起来≈原句)};\n"
        "3) structure:成分层级,每项 {idx(对应 segments)、parent(其修饰/隶属的成分 idx;主干成分 parent=null)};\n"
        "4) components:主干成分 {subject、predicate、object}(没有的留空串);\n"
        "5) key_words:重点词汇 3-6 个 [{word、pos、meaning}];\n"
        "6) grammar_points:涉及语法点 [{name(规范名,如 定语从句/状语从句/非谓语动词)、explanation(一句话)}];\n"
        "7) explanations:逐条结构解析 [{idx(对应 segments)、text}];\n"
        "8) translation:中文翻译;summary:一句话整体说明。"
    )
    user = (
        f"句子:{sentence}\n返回 JSON:"
        '{"sentence_type":..,"translation":..,"summary":..,'
        '"segments":[{"idx":1,"type":..,"text":..}],"structure":[{"idx":1,"parent":null}],'
        '"components":{"subject":..,"predicate":..,"object":..},'
        '"key_words":[{"word":..,"pos":..,"meaning":..}],'
        '"grammar_points":[{"name":..,"explanation":..}],"explanations":[{"idx":1,"text":..}]}'
    )
    # finish_reason 感知:length 截断才升档(2000→≤4000)一次,否则瞬时抖动重试一次;全失败→模板兜底
    data = await complete_json(system_prompt=system, user_prompt=user, max_tokens=2000,
                               model=fast_model(), escalate_ceiling=4000,
                               validate=lambda d: bool(d.get("segments")))
    if data:
        res = _enrich_analysis(data, sentence, syntax)
        res["paraphrase"] = await generate_paraphrase(sentence, res.get("translation"))
        return res
    return _enrich_analysis({"sentence_type": "", "translation": "", "summary": "",
                             "segments": [], "structure": [], "components": {},
                             "key_words": [], "grammar_points": [], "explanations": []},
                            sentence, syntax)


_PARA_PROMPT = "下面哪句最准确地表达了原句的意思?"


async def generate_paraphrase(sentence: str, translation: str | None = None) -> dict | None:
    """生成「释义单选」探针:1 个准确转述 + 3 个诊断性干扰项(各对应一种典型理解失败),
    用于检验学生是否真正读懂句意(而非认词)。dev 确定性 mock;生产走 LLM。无法生成→None。
    返回 {prompt, options[乱序], answer, misconceptions:{干扰项: 错因}}。"""
    base = (translation or "").replace("[译]", "").strip(" .。…")
    if is_llm_dev_mode():
        if not base:
            return None
        d1 = f"(否定/范围反转)并非「{base}」"
        d2 = f"(主宾对调)把「{base}」里的施动者与承受者弄反"
        d3 = "(逻辑关系改变)把句中的因果/转折/条件关系理解反了"
        return {"prompt": _PARA_PROMPT, "options": [base, d1, d2, d3], "answer": base,
                "misconceptions": {d1: "原句并无否定,或范围被改变了",
                                   d2: "主语与宾语的施受关系弄反了",
                                   d3: "句中的逻辑关系(因果/转折/条件)理解反了"}}
    system = (
        "你是英语阅读命题专家。给定英语长难句及其参考中文翻译,出一道**释义单选题**,"
        "检验学生是否真正读懂句子意思(而非只认识单词)。\n要求:\n"
        "1) 1 个正确选项:用简洁中文准确转述原句命题(谁对谁做了什么 + 逻辑关系),不要照抄翻译措辞;\n"
        "2) 3 个干扰项:每个对应一种**典型理解错误**,意思看似接近但关键处错,类型从"
        "【否定或范围反转、主宾/施受对调、逻辑关系改变(因果↔转折↔条件)、修饰成分挂错对象、以偏概全】"
        "中各取不同的;要像「读得半懂的人会选的」,不得无关或荒谬;\n"
        "3) misconceptions:每个干扰项 → 一句话点明错在哪(中文)。\n"
        "严格输出 JSON:{\"prompt\":..,\"options\":[4个乱序],\"answer\":..(须等于其中一个 option),"
        "\"misconceptions\":{\"干扰项原文\":\"错因\"}}。"
    )
    user = f"句子:{sentence}\n参考翻译:{translation or '(无)'}\n返回 JSON:"
    # finish_reason 感知重试;输出小、length 罕见,truncate 直接放弃→调用方退连接词题
    d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=1000,
                            model=fast_model(),
                            validate=lambda x: len([o for o in (x.get("options") or []) if str(o).strip()]) >= 3
                            and bool(x.get("answer")))
    if not d:
        return None
    opts = [str(o) for o in (d.get("options") or []) if str(o).strip()]
    ans = str(d.get("answer") or "")
    if ans not in opts:   # answer 与某 option 仅细微差异时归一化匹配
        norm = lambda s: re.sub(r"\s+", "", s).strip("。.!?！?")
        hit = next((o for o in opts if norm(o) == norm(ans)), None)
        if hit is None:
            return None
        ans = hit
    return {"prompt": _PARA_PROMPT, "options": opts, "answer": ans,
            "misconceptions": {str(k): str(v) for k, v in (d.get("misconceptions") or {}).items()}}


async def backfill_paraphrase(db: AsyncSession, *, limit: int | None = None,
                              only_missing: bool = True) -> dict:
    """给存量长难句补「释义探针」:对 analysis_json 缺 paraphrase 的句子生成并写回。
    返回 {scanned, filled}。"""
    rows = (await db.execute(sa.select(LongSentence))).scalars().all()
    scanned = filled = 0
    for ls in rows:
        a = ls.analysis_json or {}
        if only_missing and a.get("paraphrase"):
            continue
        scanned += 1
        p = await generate_paraphrase(ls.text, a.get("translation"))
        if not p:
            continue
        ls.analysis_json = {**a, "paraphrase": p}   # 新 dict → ORM 感知 JSONB 变更
        filled += 1
        if limit and filled >= limit:
            break
    await db.commit()
    return {"scanned": scanned, "filled": filled}


async def list_published(
    db: AsyncSession, *, node_id: uuid.UUID | None = None, owner_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[LongSentence]:
    """学生读:已发布长难句(平台域共享 + 该生个人域);可按句法 node 过滤。"""
    cond = sa.or_(LongSentence.scope == "platform",
                  sa.and_(LongSentence.scope == "student", LongSentence.owner_id == owner_id))
    stmt = sa.select(LongSentence).where(LongSentence.status == "published", cond)
    if node_id is not None:
        stmt = stmt.join(LongSentenceNode, LongSentenceNode.long_sentence_id == LongSentence.id).where(
            LongSentenceNode.node_id == node_id)
    return list((await db.execute(
        stmt.order_by(LongSentence.created_at.desc()).limit(limit))).scalars().all())


async def get_detail(db: AsyncSession, *, ls_id: uuid.UUID) -> tuple[LongSentence | None, list[dict]]:
    """长难句详情 + 其句法 node(供跳 R6 讲解资源)。"""
    from app.models.d15_knowledge_graph import KnowledgeNode
    ls = (await db.execute(sa.select(LongSentence).where(LongSentence.id == ls_id))).scalar_one_or_none()
    if ls is None:
        return None, []
    nodes = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.node_kind)
        .join(LongSentenceNode, LongSentenceNode.node_id == KnowledgeNode.id)
        .where(LongSentenceNode.long_sentence_id == ls_id)
    )).all()
    return ls, [{"node_id": nid, "name": nm, "node_kind": nk} for nid, nm, nk in nodes]


# ── 收藏 ───────────────────────────────────────────────────────────────────────
async def is_favorited(db: AsyncSession, *, user_id: uuid.UUID, ls_id: uuid.UUID) -> bool:
    from app.models.d20_long_sentence import LongSentenceFavorite
    row = (await db.execute(sa.select(LongSentenceFavorite.long_sentence_id).where(
        LongSentenceFavorite.user_id == user_id,
        LongSentenceFavorite.long_sentence_id == ls_id))).first()
    return row is not None


async def set_favorite(db: AsyncSession, *, user_id: uuid.UUID, ls_id: uuid.UUID, on: bool) -> bool:
    """收藏/取消收藏,返回最终是否已收藏(幂等)。"""
    from app.models.d20_long_sentence import LongSentenceFavorite
    exists = await is_favorited(db, user_id=user_id, ls_id=ls_id)
    if on and not exists:
        db.add(LongSentenceFavorite(user_id=user_id, long_sentence_id=ls_id))
        await db.commit()
    elif not on and exists:
        await db.execute(sa.delete(LongSentenceFavorite).where(
            LongSentenceFavorite.user_id == user_id,
            LongSentenceFavorite.long_sentence_id == ls_id))
        await db.commit()
    return on


async def favorited_ids(db: AsyncSession, *, user_id: uuid.UUID, ls_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    from app.models.d20_long_sentence import LongSentenceFavorite
    if not ls_ids:
        return set()
    rows = (await db.execute(sa.select(LongSentenceFavorite.long_sentence_id).where(
        LongSentenceFavorite.user_id == user_id,
        LongSentenceFavorite.long_sentence_id.in_(ls_ids)))).scalars().all()
    return set(rows)


# ── 验证题型(L3 客观自动判分 / L4 主观 AI·发音评测)────────────────────────────
_OBJECTIVE_TYPES = {"cloze", "struct_type", "main_clause", "paraphrase"}
_SUBJECTIVE_TYPES = {"translate", "rewrite", "span_label", "read_aloud"}  # L4:AI 评分 / 发音评测
_IMPLEMENTED_TYPES = _OBJECTIVE_TYPES | _SUBJECTIVE_TYPES
_READ_ALOUD_PASS = 60          # 朗读发音通过分阈值
_SUBJ_SIM_PASS = 0.5           # dev 主观判分相似度阈值(生产走 LLM)
_ALL_VERIFY_TYPES = ["cloze", "struct_type", "main_clause", "paraphrase", "translate",
                     "span_label", "reorder", "rewrite", "read_aloud"]
_SYNTAX_POOL = ["定语从句", "状语从句", "名词性从句", "非谓语动词", "倒装句", "强调句", "同位语从句"]
_REL_WORDS = ["which", "that", "who", "whom", "whose", "because", "although", "when", "while", "if"]
DEFAULT_REQUIRED_PASS = 3      # 判句法 node 掌握所需净做对数(后台 long_sentence.required_pass 可覆盖)


async def enabled_verify_types(db: AsyncSession) -> list[str]:
    """后台配置 long_sentence.verify_types(默认全开);本期仅客观题型实际可用。"""
    from app.models.d9_system import SystemConfig
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == "long_sentence.verify_types")
    )).scalar_one_or_none()
    configured = _ALL_VERIFY_TYPES
    if row is not None and isinstance(row.value, list):
        configured = row.value
    # 仅返回已实现(客观+主观)且被配置开放的(未实现如 reorder 不返回)
    return [t for t in configured if t in _IMPLEMENTED_TYPES]


def _diag_main_clause(ls: LongSentence) -> dict | None:
    """点主干题:从 segments/components 构造「诊断性」干扰项——每个错项对应一种理解失败。
    返回 {options, answer, misconceptions:{option: 错因}}。无主干→None。"""
    a = ls.analysis_json or {}
    mc = (a.get("main_clause") or "").strip()
    if not mc:
        return None
    segs = a.get("segments") or []
    comp = a.get("components") or {}
    distract: list[str] = []
    miscon: dict[str, str] = {}

    def add(txt: str | None, reason: str):
        if not txt:
            return
        t = txt.strip().strip(",.;:")
        if t and t.lower() != mc.lower() and t not in distract:
            distract.append(t)
            miscon[t] = reason

    # 错项①:把某个从句整体误当主干(认错主干层)
    for s in segs:
        if "从句" in (s.get("type") or ""):
            add(s.get("text"), "这是从句,不是主干——主句才是句子骨架")
            break
    # 错项②:只取主语,丢了主句谓语(主干不完整)
    add((comp.get("subject") or ""), "只抓了主语,缺主句谓语——主干要「主语+谓语」")
    # 错项③:整句当主干(没有剥离修饰的意识)
    full = (ls.text or "").strip()
    add((full[:38] + "…") if len(full) > 40 else full, "整句不是主干——长难句要剥掉修饰/从句后剩下主谓")
    # 兜底补足到 3 个干扰项
    for extra, why in (("(无主干)", "该句有明确主干"), ("全句即主干", "长难句的主干通常只占整句一小部分")):
        if len(distract) >= 3:
            break
        add(extra, why)
    return {"options": [mc] + distract[:3], "answer": mc, "misconceptions": miscon}


def comprehension_probes(ls: LongSentence) -> list[dict]:
    """Phase1 理解检测「双探针」:①点主干(测句法结构)②释义/连接词(测意义)。
    探针2 优先释义(需缓存),退连接词 cloze,再退句法点 struct_type。每题带 key。"""
    out: list[dict] = []
    mc = build_verify(ls, "main_clause")
    if mc:
        out.append({"key": "main_clause", **mc})
    for t in ("paraphrase", "cloze", "struct_type"):
        q = build_verify(ls, t)
        if q:
            out.append({"key": t, **q})
            break
    return out


# 短翻译产出项·维度 rubric(每维 0-2)
_TRANS_DIMS = [("proposition", "命题准确"), ("logic", "逻辑关系"),
               ("modifier", "修饰归属"), ("trunk", "主干完整")]
_TRANS_DIM_MAX = 2
_TRANS_PASS_TOTAL = 6        # 总分 ≥6/8 且命题≥1 视为产出达标
_PRODUCTIVE_BONUS = 2.0      # 产出达标 → θ 小幅上调(实测的强证据)


async def grade_translation(sentence: str, ref_translation: str | None, answer: str) -> dict:
    """短翻译产出项·维度化评分(命题/逻辑/修饰/主干 各 0-2)。
    返回 {dimensions:[{key,label,score,max,note}], total, max, passed, feedback}。dev mock 用相似度近似。"""
    answer = (answer or "").strip()
    total_max = _TRANS_DIM_MAX * len(_TRANS_DIMS)
    ref = (ref_translation or "").replace("[译]", "").strip()
    if not answer:
        dims = [{"key": k, "label": l, "score": 0, "max": _TRANS_DIM_MAX, "note": ""} for k, l in _TRANS_DIMS]
        return {"dimensions": dims, "total": 0, "max": total_max, "passed": False, "feedback": "还没写翻译"}
    if is_llm_dev_mode():
        sim = difflib.SequenceMatcher(None, answer, ref).ratio() if ref else 0.5
        base = 2 if sim >= 0.7 else (1 if sim >= 0.35 else 0)
        dims = [{"key": k, "label": l, "score": base, "max": _TRANS_DIM_MAX, "note": ""} for k, l in _TRANS_DIMS]
        tot = base * len(_TRANS_DIMS)
        return {"dimensions": dims, "total": tot, "max": total_max,
                "passed": tot >= _TRANS_PASS_TOTAL, "feedback": f"(dev)与参考相似度 {sim:.0%}"}
    system = (
        "你是英语翻译评分老师。按 4 个维度给学生的中文翻译打分,每维 0/1/2(0 错/缺、1 部分对、2 准确):\n"
        "- proposition 命题准确:谁对谁做了什么(主体/动作/对象)译对;\n"
        "- logic 逻辑关系:让步/因果/转折/条件/目的等关系译对;\n"
        "- modifier 修饰归属:定语/状语等修饰挂到了正确的中心词;\n"
        "- trunk 主干完整:主句的主语+谓语没丢、没错。\n"
        "每维给一句简短中文点评(note,指出对或错在哪),再给一句总评(feedback,点出最该改进的一处)。\n"
        "严格输出 JSON:{\"proposition\":{\"score\":0-2,\"note\":..},\"logic\":{..},\"modifier\":{..},\"trunk\":{..},\"feedback\":..}"
    )
    user = f"原句:{sentence}\n参考翻译:{ref or '(无)'}\n学生翻译:{answer}\n返回 JSON:"
    # finish_reason 感知重试;至少有一维有内容才算有效,否则瞬时抖动重试一次
    d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=800,
                            model=fast_model(),
                            validate=lambda x: any(x.get(k) for k, _ in _TRANS_DIMS))
    if d:
        dims = []
        for k, l in _TRANS_DIMS:
            cell = d.get(k) or {}
            try:
                sc = max(0, min(_TRANS_DIM_MAX, int(cell.get("score", 0))))
            except (ValueError, TypeError):
                sc = 0
            dims.append({"key": k, "label": l, "score": sc, "max": _TRANS_DIM_MAX, "note": str(cell.get("note") or "")})
        tot = sum(x["score"] for x in dims)
        prop = next((x["score"] for x in dims if x["key"] == "proposition"), 0)
        return {"dimensions": dims, "total": tot, "max": total_max,
                "passed": tot >= _TRANS_PASS_TOTAL and prop >= 1, "feedback": str(d.get("feedback") or "")}
    dims = [{"key": k, "label": l, "score": 0, "max": _TRANS_DIM_MAX, "note": ""} for k, l in _TRANS_DIMS]
    return {"dimensions": dims, "total": 0, "max": total_max, "passed": False, "feedback": "评分服务暂不可用,请稍后再试"}


async def apply_productive(db: AsyncSession, user, *, passed: bool) -> float:
    """短翻译产出达标 → θ 小幅上调(产出是理解的强证据);未达标不扣分。返回新 θ。"""
    if not passed:
        return await get_theta(db, user)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d20_long_sentence import StudentLsState
    cur = await get_theta(db, user)
    new = max(12.0, min(95.0, cur + _PRODUCTIVE_BONUS))
    await db.execute(
        pg_insert(StudentLsState).values(user_id=user.id, theta=new, seen_count=1)
        .on_conflict_do_update(index_elements=["user_id"],
                               set_={"theta": new, "seen_count": StudentLsState.seen_count + 1}))
    await db.commit()
    return new


def build_verify(ls: LongSentence, verify_type: str) -> dict | None:
    """从长难句解析生成一道客观题:{type, prompt, options, answer}。无法生成→None。"""
    a = ls.analysis_json or {}
    syntax = a.get("syntax_points") or []
    if verify_type == "struct_type":
        if not syntax:
            return None
        ans = syntax[0]
        distract = [s for s in _SYNTAX_POOL if s != ans][:3]
        return {"type": verify_type, "prompt": "该句主要涉及的句法点是?",
                "options": [ans] + distract, "answer": ans}
    if verify_type == "main_clause":
        d = _diag_main_clause(ls)
        if d is None:
            return None
        return {"type": verify_type, "prompt": "剥掉修饰和从句,这句的主干(主谓核心)是?",
                "options": d["options"], "answer": d["answer"],
                "misconceptions": d["misconceptions"]}
    if verify_type == "paraphrase":
        # 释义单选:抽取时 LLM 预生成并缓存进 analysis_json.paraphrase(干扰项=典型误解)
        p = a.get("paraphrase") or {}
        opts = p.get("options") or []
        ans = p.get("answer")
        if len(opts) < 2 or not ans:
            return None
        return {"type": verify_type, "prompt": _PARA_PROMPT,   # 固定问法(原句已在页面上方展示)
                "options": opts, "answer": ans, "misconceptions": p.get("misconceptions") or {}}
    if verify_type == "cloze":
        # 挖掉句中第一个出现的关系/连接词
        for w in _REL_WORDS:
            if re.search(rf"\b{w}\b", ls.text, re.I):
                blanked = re.sub(rf"\b{w}\b", "____", ls.text, count=1, flags=re.I)
                distract = [x for x in _REL_WORDS if x.lower() != w.lower()][:3]
                miscon = {x: "连接词决定逻辑关系(因果/转折/时间…),这里的关系判断有误" for x in distract}
                return {"type": verify_type, "prompt": f"填入恰当的连接词:{blanked}",
                        "options": [w] + distract, "answer": w, "misconceptions": miscon}
        return None
    # 主观题(无选项,自由作答/音频;answer 为参考)
    if verify_type == "translate":
        return {"type": verify_type, "prompt": f"翻译这句:{ls.text}",
                "options": [], "answer": a.get("translation", "")}
    if verify_type == "rewrite":
        sp = syntax[0] if syntax else "同句法点"
        return {"type": verify_type, "prompt": f"用「{sp}」改写/仿写一句:{ls.text}",
                "options": [], "answer": ls.text}
    if verify_type == "span_label":
        layers = a.get("layers") or []
        ref = layers[0]["text"] if layers else ls.text
        sp = syntax[0] if syntax else "修饰成分"
        return {"type": verify_type, "prompt": f"标出句中的「{sp}」部分:{ls.text}",
                "options": [], "answer": ref}
    if verify_type == "read_aloud":
        return {"type": verify_type, "prompt": f"朗读这句:{ls.text}",
                "options": [], "answer": ls.text}
    return None


async def _grade_subjective(verify_type: str, ls: LongSentence, q: dict, answer: str) -> bool:
    """主观题判分:translate/rewrite/span_label 走 AI(dev 用相似度);read_aloud 走发音分阈值。"""
    if verify_type == "read_aloud":
        # answer 传发音总分(客户端/发音评测得到);≥阈值算过
        try:
            return int(float(answer)) >= _READ_ALOUD_PASS
        except (ValueError, TypeError):
            return False
    ref = str(q.get("answer") or "")
    if is_llm_dev_mode():
        return difflib.SequenceMatcher(None, answer.strip(), ref.strip()).ratio() >= _SUBJ_SIM_PASS
    system = ("你是英语评分老师。判断学生答案是否达标(语义正确/句法点正确即可,不苛求字面)。"
              "只输出 JSON {\"pass\": true/false}。")
    user = f"题型:{verify_type}\n句子:{ls.text}\n参考:{ref}\n学生答案:{answer}"
    try:
        resp = await chat_completion(system_prompt=system, user_prompt=user, max_tokens=64,
                                     response_format={"type": "json_object"}, model=fast_model())
        return bool(json.loads(resp.choices[0].message.content or "{}").get("pass"))
    except Exception as exc:  # noqa: BLE001
        _log.warning("subjective grade LLM failed: %s", exc)
        return False


async def submit_verify(
    db: AsyncSession, *, student_id: uuid.UUID, ls_id: uuid.UUID, verify_type: str, answer: str,
    required_pass: int = DEFAULT_REQUIRED_PASS,
) -> dict:
    """提交客观验证答案:判分 → 落 answer_log+student_kp(该句各句法 node)→ 错则收口、达标则判掌握。"""
    from app.core.exceptions import AppError
    from app.services import mastery_judge_service, wrong_center_service
    from app.models.d16_question_domain import StudentKp

    ls, nodes = await get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    if verify_type not in _IMPLEMENTED_TYPES:
        raise AppError(code=400, message="该验证题型暂不支持")
    q = build_verify(ls, verify_type)
    if q is None:
        raise AppError(code=400, message="该句无法生成此题型")

    if verify_type in _OBJECTIVE_TYPES:
        correct = answer.strip() == str(q["answer"]).strip()
    else:
        correct = await _grade_subjective(verify_type, ls, q, answer)
    # 合成 question_id(同句+同题型稳定),逐句法 node 记作答 + 判掌握
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"ls-verify:{ls_id}:{verify_type}")
    mastered: list[str] = []
    for n in nodes:
        nid = n["node_id"]
        await mastery_judge_service.log_answer(
            db, student_id=student_id, q_scope="platform", question_id=qid,
            node_id=nid, is_correct=correct, feature="long_sentence_verify")
        # BKT:用先验掌握度 + 本次对错做贝叶斯更新(替代旧「过阈值→1.0」硬规则,抗运气过关)
        sk = (await db.execute(
            sa.select(StudentKp).where(StudentKp.student_id == student_id, StudentKp.node_id == nid)
        )).scalar_one_or_none()
        prior = None if (sk is None or sk.mastery is None) else float(sk.mastery)
        new_p = mastery_judge_service.bkt_update(prior, correct)
        if sk is not None:
            sk.mastery = new_p
        if correct and new_p >= mastery_judge_service.BKT_MASTERED \
                and (prior is None or prior < mastery_judge_service.BKT_MASTERED):
            mastered.append(n["name"])           # 掌握度刚跨过判掌握线
        if not correct:
            await wrong_center_service.record_wrong(
                db, student_id=student_id, q_scope="platform", question_id=qid, node_id=nid)
    await db.flush()
    return {"correct": correct, "correct_answer": q["answer"], "mastered_nodes": mastered}


async def _already_extracted(db: AsyncSession, question_id: uuid.UUID) -> bool:
    return (await db.execute(
        sa.select(LongSentence.id).where(LongSentence.source_question_id == question_id).limit(1)
    )).first() is not None


async def _already_extracted_passage(db: AsyncSession, passage_id: uuid.UUID) -> bool:
    return (await db.execute(
        sa.select(LongSentence.id).where(LongSentence.source_passage_id == passage_id).limit(1)
    )).first() is not None


def _stage_from_grade(grade: str | None) -> str | None:
    """从年级推学段:小|初|高。"""
    g = grade or ""
    if any(k in g for k in ["小学", "小", "一年级", "二年级", "三年级", "四年级", "五年级", "六年级"]):
        return "小"
    if any(k in g for k in ["初", "七年级", "八年级", "九年级"]):
        return "初"
    if any(k in g for k in ["高", "高一", "高二", "高三"]):
        return "高"
    return None


async def _persist_long_sentences(
    db: AsyncSession, st: ExtractStats, *, text: str, scope: str, source_kind: str,
    min_words: int, dry_run: bool, owner_id: uuid.UUID | None = None,
    source_q_scope: str | None = None, source_question_id: uuid.UUID | None = None,
    source_passage_id: uuid.UUID | None = None, locate: dict | None = None,
    select_min: int | None = None, select_top_n: int | None = None,
) -> None:
    """切句 → 候选 → (按难度筛选)→ AI 拆解 → 建 long_sentence(带定位)→ match_kp。
    教材(用难度筛选时):候选放宽为「词数 ≥ 配置 min_words(长句最小词数)」、不要求含从句,
      再按难度挑——select_min 不为空 → 难度 > 阈值的全部;否则 select_top_n → 该篇最难的 N 句。
    平台真题(无难度筛选):仍用 is_long 长难句门槛(≥min_words 且含从句),全留。"""
    loc = locate or {}
    by_difficulty = select_min is not None or select_top_n is not None
    # 一遍:切句 + 廉价算难度(spaCy,不耗 LLM),收集候选
    cands = []
    for sent in split_sentences(text or ""):
        st.sentences += 1
        comp = syntactic_complexity(sent, min_words)
        # 难度筛选模式:词数达配置下限即入候选(不强求从句);否则用 is_long 硬门槛
        if (comp["word_count"] >= min_words) if by_difficulty else _is_long(comp, sent, min_words):
            cands.append((sent, comp))
    st.long_kept += len(cands)
    # 选取:阈值优先,否则取最难 N 句;都没配则全留
    if select_min is not None:
        chosen = [c for c in cands if c[1]["difficulty"] > select_min]
    elif select_top_n is not None:
        chosen = sorted(cands, key=lambda c: c[1]["difficulty"], reverse=True)[:max(0, select_top_n)]
    else:
        chosen = cands
    # 二遍:仅对选中的句子做 AI 拆解 + 落库
    for sent, comp in chosen:
        analysis = await analyze_sentence(sent)
        analysis["difficulty"] = comp["difficulty"]
        analysis["complexity"] = comp
        st.syntax_points.update(analysis.get("syntax_points") or [])
        if dry_run:
            st.created += 1
            continue
        ls = LongSentence(
            id=uuid.uuid4(), scope=scope, owner_id=owner_id, source_kind=source_kind,
            source_q_scope=source_q_scope, source_question_id=source_question_id,
            source_passage_id=source_passage_id,
            text=sent, analysis_json=analysis, difficulty=comp["difficulty"], status="draft",
            textbook_version=loc.get("textbook_version"), stage=loc.get("stage"),
            grade=loc.get("grade"), semester=loc.get("semester"),
            unit_id=loc.get("unit_id"), exam_type=loc.get("exam_type"),
        )
        db.add(ls)
        await db.flush()
        st.created += 1
        for name in (analysis.get("syntax_points") or []):
            m = await match_kp(db, raw_name=name, axis_hint="knowledge", source_type="exam")
            if m.node_id is not None:
                db.add(LongSentenceNode(long_sentence_id=ls.id, node_id=m.node_id))
                st.edges += 1
            elif m.candidate_id is not None:
                st.candidates += 1


async def extract_from_platform(
    db: AsyncSession, *, limit: int | None = None, min_words: int = DEFAULT_MIN_WORDS,
    dry_run: bool = False, only_question_ids: set | None = None, filters: dict | None = None,
) -> ExtractStats:
    """① 扫平台真题(type='real')未抽过的 → 平台长难句。幂等按 source_question_id。
    filters 可按 textbook_version/stage/grade/semester/exam_type/region(均为多值列表)挑范围。
    定位:普通真题用 年级+上下;中考/高考真题用 学段(exam_type 区分)。"""
    f = filters or {}
    st = ExtractStats()
    q = sa.select(PlatformQuestion).where(PlatformQuestion.type == "real")
    if f.get("textbook_version"):
        q = q.where(PlatformQuestion.textbook_version.in_(f["textbook_version"]))
    if f.get("stage"):
        q = q.where(PlatformQuestion.stage.in_(f["stage"]))
    if f.get("grade"):
        q = q.where(PlatformQuestion.grade.in_(f["grade"]))
    if f.get("semester"):
        q = q.where(PlatformQuestion.semester.in_(f["semester"]))
    if f.get("exam_type"):
        q = q.where(PlatformQuestion.exam_type.in_(f["exam_type"]))
    if f.get("region"):
        q = q.where(PlatformQuestion.region_code.in_(f["region"]))
    if only_question_ids is not None:
        q = q.where(PlatformQuestion.id.in_(only_question_ids))
    if limit is not None:
        q = q.limit(limit)
    for pq in (await db.execute(q)).scalars().all():
        st.scanned += 1
        if await _already_extracted(db, pq.id):
            st.skipped_done += 1
            continue
        locate = {
            "textbook_version": pq.textbook_version,
            "stage": pq.stage or _stage_from_grade(pq.grade),
            "grade": pq.grade, "semester": pq.semester,
            "exam_type": pq.exam_type or "普通",
        }
        await _persist_long_sentences(
            db, st, text=pq.stem or "", scope="platform", source_kind="platform_real",
            source_q_scope="platform", source_question_id=pq.id,
            locate=locate, min_words=min_words, dry_run=dry_run)
        if not dry_run:
            await db.flush()
    await (db.rollback() if dry_run else db.commit())
    return st


async def extract_from_textbook(
    db: AsyncSession, *, limit: int | None = None, min_words: int = DEFAULT_MIN_WORDS,
    dry_run: bool = False, only_passage_ids: set | None = None, filters: dict | None = None,
) -> ExtractStats:
    """② 扫课程单元**阅读**短文(curriculum_unit_passages, kind=阅读)未抽过的 → 平台长难句。
    幂等按 source_passage_id。定位:从所属单元取 教材版/年级/学期/单元,学段从年级推。
    难度筛选(配置 long_sentence.textbook_difficulty_min / textbook_top_n):
      配了阈值 → 抽难度超过阈值的全部;否则 → 抽该篇最难的 N 句。"""
    from app.models.d4_knowledge import CurriculumUnit, CurriculumUnitPassage
    cfg = await get_config(db)
    sel_min = cfg.get("textbook_difficulty_min")
    sel_min = int(sel_min) if sel_min not in (None, "", 0, "0") else None
    sel_top = None if sel_min is not None else int(cfg.get("textbook_top_n") or 3)
    st = ExtractStats()
    f = filters or {}
    q = (sa.select(CurriculumUnitPassage, CurriculumUnit)
         .join(CurriculumUnit, CurriculumUnit.id == CurriculumUnitPassage.unit_id)
         .where(CurriculumUnitPassage.text.isnot(None), CurriculumUnitPassage.kind == "阅读"))
    if f.get("textbook_version"):
        q = q.where(CurriculumUnit.textbook_version.in_(f["textbook_version"]))
    if f.get("grade"):
        q = q.where(CurriculumUnit.grade.in_(f["grade"]))
    if f.get("semester"):
        q = q.where(CurriculumUnit.semester.in_(f["semester"]))
    if f.get("unit_ids"):
        q = q.where(CurriculumUnit.id.in_(f["unit_ids"]))
    if only_passage_ids is not None:
        q = q.where(CurriculumUnitPassage.id.in_(only_passage_ids))
    if limit is not None:
        q = q.limit(limit)
    for up, unit in (await db.execute(q)).all():
        st.scanned += 1
        if await _already_extracted_passage(db, up.id):
            st.skipped_done += 1
            continue
        locate = {
            "textbook_version": unit.textbook_version, "grade": unit.grade,
            "semester": unit.semester, "unit_id": unit.id,
            "stage": _stage_from_grade(unit.grade),
        }
        await _persist_long_sentences(
            db, st, text=up.text or "", scope="platform", source_kind="textbook",
            source_passage_id=up.id, locate=locate, min_words=min_words, dry_run=dry_run,
            select_min=sel_min, select_top_n=sel_top)
        if not dry_run:
            await db.flush()
    await (db.rollback() if dry_run else db.commit())
    return st


# 平台抽取来源:仅 真题 + 教材(学生上传走独立表,见 extract_student_for_question)
_SOURCE_KIND_TO_FN = {
    "platform_real": extract_from_platform,
    "textbook": extract_from_textbook,
}


async def _student_already_extracted(db: AsyncSession, question_id: uuid.UUID) -> bool:
    from app.models.d20_long_sentence import StudentLongSentence
    return (await db.execute(sa.select(StudentLongSentence.id).where(
        StudentLongSentence.source_question_id == question_id).limit(1))).first() is not None


async def extract_student_for_question(
    db: AsyncSession, *, owner_id: uuid.UUID, question_id: uuid.UUID, text: str,
    min_words: int = DEFAULT_MIN_WORDS,
) -> int:
    """学生上传作业时调用:把该题文本里的长难句抽到 student_long_sentence(本人可见,直接发布)。
    幂等按 source_question_id。返回新增条数。best-effort,调用方自行 commit。"""
    from app.models.d20_long_sentence import StudentLongSentence
    if not text or await _student_already_extracted(db, question_id):
        return 0
    n = 0
    for sent in split_sentences(text):
        comp = syntactic_complexity(sent, min_words)
        if not _is_long(comp, sent, min_words):
            continue
        analysis = await analyze_sentence(sent)
        analysis["difficulty"] = comp["difficulty"]
        analysis["complexity"] = comp
        db.add(StudentLongSentence(
            id=uuid.uuid4(), owner_id=owner_id, source_question_id=question_id,
            text=sent, analysis_json=analysis, difficulty=comp["difficulty"], status="published"))
        n += 1
    return n


async def list_student_published(
    db: AsyncSession, *, owner_id: uuid.UUID, limit: int = 50,
) -> list:
    from app.models.d20_long_sentence import StudentLongSentence
    return list((await db.execute(
        sa.select(StudentLongSentence).where(
            StudentLongSentence.owner_id == owner_id, StudentLongSentence.status == "published")
        .order_by(StudentLongSentence.created_at.desc()).limit(limit))).scalars().all())


# ── 自适应推荐(按学生水平选下一句)──────────────────────────────────────────
def _theta_from_grade(grade: str | None, stage: str | None = None) -> int:
    """从年级估「长难句水平」θ(与 difficulty 同尺,0–100)。"""
    g = grade or ""
    for k, v in [("高三", 82), ("高3", 82), ("高二", 74), ("高2", 74), ("高一", 66), ("高1", 66),
                 ("九年级", 56), ("初三", 56), ("八年级", 46), ("初二", 46), ("七年级", 36), ("初一", 36)]:
        if k in g:
            return v
    if any(k in g for k in ["六年级", "五年级", "四年级", "三年级", "二年级", "一年级", "小"]):
        return 26
    return {"高": 70, "初": 45, "小": 25}.get(stage or _stage_from_grade(grade) or "", 50)


def ls_tier(theta: float) -> str:
    """按水平分脚手架档:intro(看懂)< 45 ≤ build(划结构)< 70 ≤ challenge(输出)。"""
    if theta < 45:
        return "intro"
    if theta < 70:
        return "build"
    return "challenge"


async def get_theta(db: AsyncSession, user) -> float:
    """学生当前长难句水平 θ:有持久值用之,否则从年级冷启动估。"""
    from app.models.d20_long_sentence import StudentLsState
    s = await db.get(StudentLsState, user.id)
    if s is not None and s.theta is not None:
        return float(s.theta)
    return float(_theta_from_grade(getattr(user, "preferred_grade", None)))


_FEEDBACK_DELTA = {"easy": 5.0, "ok": 1.0, "hard": -4.0}


async def apply_feedback(db: AsyncSession, user, *, rating: str) -> float:
    """按反馈校准 θ:太简单↑5 / 刚好↑1 / 有点难↓4,夹在 [12,95]。返回新 θ。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d20_long_sentence import StudentLsState
    cur = await get_theta(db, user)
    new = max(12.0, min(95.0, cur + _FEEDBACK_DELTA.get(rating, 0.0)))
    await db.execute(
        pg_insert(StudentLsState).values(user_id=user.id, theta=new, seen_count=1)
        .on_conflict_do_update(index_elements=["user_id"],
                               set_={"theta": new, "seen_count": StudentLsState.seen_count + 1}))
    await db.commit()
    return new


# θ 实测校准:理解检测为主(±4),自评为辅(±1)。
_MEASURED_PASS = 4.0       # 双探针全过:略高于当前水平,上调
_MEASURED_PARTIAL = -1.0   # 主干对但意义偏:结构会、理解未到位,略降
_MEASURED_FAIL = -4.0      # 主干就错:明显超出当前水平,下调
_SELF_DELTA = {"easy": 1.0, "ok": 0.0, "hard": -1.0}


async def apply_comprehension(db: AsyncSession, user, *, main_ok: bool, p2_ok: bool,
                              self_rating: str | None = None) -> float:
    """按理解检测结果校准 θ(实测为主、自评为辅),夹在 [12,95]。返回新 θ。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d20_long_sentence import StudentLsState
    cur = await get_theta(db, user)
    if main_ok and p2_ok:
        delta = _MEASURED_PASS
    elif main_ok:
        delta = _MEASURED_PARTIAL
    else:
        delta = _MEASURED_FAIL
    delta += _SELF_DELTA.get(self_rating or "", 0.0)
    new = max(12.0, min(95.0, cur + delta))
    await db.execute(
        pg_insert(StudentLsState).values(user_id=user.id, theta=new, seen_count=1)
        .on_conflict_do_update(index_elements=["user_id"],
                               set_={"theta": new, "seen_count": StudentLsState.seen_count + 1}))
    await db.commit()
    return new


# 间隔重现:Leitner 盒 → 下次间隔(分钟)。盒越高间隔越长,超过最高盒则毕业。
_REVIEW_MIN = {1: 20, 2: 1440, 3: 4320, 4: 10080}   # 20分钟 / 1天 / 3天 / 7天
_REVIEW_MAXBOX = 4


def _review_due(box: int):
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(minutes=_REVIEW_MIN.get(box, 10080))


async def record_review(db: AsyncSession, user, *, ls_id, is_student: bool, rating: str) -> None:
    """按反馈维护间隔重现:难→进/重置盒1(很快再推);刚好→升盒拉长间隔;太简单→毕业。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d20_long_sentence import StudentLsReview
    cur = await db.get(StudentLsReview, (user.id, ls_id))
    if rating == "hard":
        await db.execute(pg_insert(StudentLsReview)
                         .values(user_id=user.id, ls_id=ls_id, is_student=is_student, box=1, due_at=_review_due(1))
                         .on_conflict_do_update(index_elements=["user_id", "ls_id"],
                                                set_={"box": 1, "due_at": _review_due(1), "is_student": is_student}))
    elif cur is not None:
        if rating == "easy" or cur.box + 1 > _REVIEW_MAXBOX:
            await db.execute(sa.delete(StudentLsReview).where(
                StudentLsReview.user_id == user.id, StudentLsReview.ls_id == ls_id))   # 毕业
        else:
            nb = cur.box + 1
            await db.execute(sa.update(StudentLsReview)
                             .where(StudentLsReview.user_id == user.id, StudentLsReview.ls_id == ls_id)
                             .values(box=nb, due_at=_review_due(nb)))
    await db.commit()


async def submit_comprehension(db: AsyncSession, *, user, ls_id: uuid.UUID, answers: dict,
                               self_rating: str | None = None) -> dict:
    """Phase1 理解检测:双探针逐题判分(复用 submit_verify → 回写 node mastery/错题)→ 合成单句
    理解分 → θ 实测校准 → 间隔重现(过=巩固升盒 / 不过=入盒1 很快再推)。
    answers: {probe_key: 学生答案}。返回 {passed, probes[], theta, target, tier}。"""
    from app.core.exceptions import AppError
    ls, _nodes = await get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")

    results: list[dict] = []
    flags: dict[str, bool] = {}
    for key, ans in (answers or {}).items():
        q = build_verify(ls, key)
        if q is None:
            continue
        res = await submit_verify(db, student_id=user.id, ls_id=ls_id, verify_type=key, answer=str(ans))
        miscon = None
        if not res["correct"]:
            miscon = (q.get("misconceptions") or {}).get(str(ans).strip())
        results.append({"key": key, "correct": bool(res["correct"]),
                        "correct_answer": str(res["correct_answer"]), "misconception": miscon})
        flags[key] = bool(res["correct"])

    main_ok = flags.get("main_clause", False)
    p2_keys = [k for k in flags if k != "main_clause"]
    p2_ok = flags.get(p2_keys[0], False) if p2_keys else False
    passed = bool(main_ok and p2_ok)

    theta = await apply_comprehension(db, user, main_ok=main_ok, p2_ok=p2_ok, self_rating=self_rating)
    # 间隔重现:过了→巩固(easy 升盒/毕业);没过→入盒1 很快再推
    try:
        await record_review(db, user, ls_id=ls_id, is_student=False,
                            rating="easy" if passed else "hard")
    except Exception:  # noqa: BLE001
        pass
    await db.commit()
    return {"passed": passed, "probes": results, "theta": theta,
            "target": min(95.0, theta + 5), "tier": ls_tier(theta)}


async def submit_translation(db: AsyncSession, *, user, ls_id: uuid.UUID, answer: str) -> dict:
    """短翻译产出项:维度 rubric 评分 + 达标则 θ 小幅上调。返回 rubric + {theta, target, tier}。"""
    from app.core.exceptions import AppError
    ls, _ = await get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    ref = (ls.analysis_json or {}).get("translation")
    res = await grade_translation(ls.text, ref, answer)
    theta = await apply_productive(db, user, passed=res["passed"])
    return {**res, "theta": theta, "target": min(95.0, theta + 5), "tier": ls_tier(theta)}


# 迁移项:句法结构相似度权重——从句/非谓语等"硬结构"重于介词短语/并列等通用结构
def _syntax_weight(s: str) -> float:
    if re.search(r"从句|非谓语|不定式|分词|动名词|倒装|强调|虚拟|同位语|省略", s):
        return 3.0
    if "并列" in s:
        return 1.5
    return 1.0


async def find_transfer_sentence(db: AsyncSession, *, origin: LongSentence, user,
                                 exclude_ids=None) -> tuple[LongSentence, list[str]] | None:
    """按句法结构检索一句「同结构、新内容」的迁移句:syntax_points 加权重叠最高者(从句等硬结构优先),
    难度接近、有共享 node 额外加分。返回 (迁移句, 共享结构名列表);找不到→None。"""
    ex = set(exclude_ids or [])
    ex.add(origin.id)
    o_syntax = set((origin.analysis_json or {}).get("syntax_points") or [])
    if not o_syntax:
        return None
    rows = (await db.execute(sa.select(LongSentence).where(
        LongSentence.status == "published"))).scalars().all()
    # node 链接(有则共享 node 额外加权;当前多数句无 node,主信号是 syntax_points)
    nm: dict = {}
    for lsid, nid in (await db.execute(sa.select(
            LongSentenceNode.long_sentence_id, LongSentenceNode.node_id))).all():
        nm.setdefault(lsid, set()).add(nid)
    o_nodes = nm.get(origin.id, set())
    o_diff = float(origin.difficulty or 50)
    best = None
    best_score = 0.0
    best_shared: list[str] = []
    for c in rows:
        if c.id in ex:
            continue
        c_syntax = set((c.analysis_json or {}).get("syntax_points") or [])
        shared = o_syntax & c_syntax
        if not shared:
            continue
        score = sum(_syntax_weight(s) for s in shared)
        score += 2.0 * len(o_nodes & nm.get(c.id, set()))      # 共享句法 node 额外加权
        score -= 0.01 * abs(float(c.difficulty or 50) - o_diff)  # 难度接近优先
        if score > best_score:
            best_score = score
            best = c
            best_shared = sorted(shared, key=_syntax_weight, reverse=True)
    if best is None:
        return None
    return best, best_shared


async def submit_transfer(db: AsyncSession, *, user, origin_id: uuid.UUID,
                          transfer_id: uuid.UUID, answers: dict) -> dict:
    """迁移项判分:对「同结构新句」做理解检测(复用 submit_comprehension:θ/node mastery/复习全走通),
    再给出迁移结论——过=真掌握该句法(transferred);不过=疑似记住原题(memorized),原句回炉巩固。
    返回 submit_comprehension 结果 + {verdict, shared}。"""
    res = await submit_comprehension(db, user=user, ls_id=transfer_id, answers=answers)
    origin, _ = await get_detail(db, ls_id=origin_id)
    transfer, _ = await get_detail(db, ls_id=transfer_id)
    o = set((origin.analysis_json or {}).get("syntax_points") or []) if origin else set()
    t = set((transfer.analysis_json or {}).get("syntax_points") or []) if transfer else set()
    shared = sorted(o & t, key=_syntax_weight, reverse=True)
    verdict = "transferred" if res["passed"] else "memorized"
    if not res["passed"]:   # 没迁移成功 → 原句也回炉,巩固这个句法点
        try:
            await record_review(db, user, ls_id=origin_id, is_student=False, rating="hard")
        except Exception:  # noqa: BLE001
            pass
        await db.commit()
    return {**res, "verdict": verdict, "shared": shared}


async def recommend_next(db: AsyncSession, *, user, exclude_ids=None) -> dict:
    """按学生水平选下一句:难度贴近 θ+5(i+1)+ 薄弱句法点 + 课程对齐 + 个人材料,带抖动。
    返回 {best: (kind, row) | None, theta, target, weak_hit}。"""
    import random
    from app.models.d16_question_domain import StudentKp
    from app.models.d20_long_sentence import StudentLongSentence
    ex = set(exclude_ids or [])
    grade = getattr(user, "preferred_grade", None)
    tv = getattr(user, "preferred_textbook_version", None)
    ps = getattr(user, "preferred_semester", None)
    theta = await get_theta(db, user)             # 持久 θ(随反馈校准),冷启动回落年级估
    target = min(95.0, theta + 5)

    # 间隔重现:有到期复习句则优先推(巩固做错的)
    from app.models.d20_long_sentence import StudentLsReview, StudentLongSentence as _SLS
    due = (await db.execute(sa.select(StudentLsReview).where(
        StudentLsReview.user_id == user.id, StudentLsReview.due_at <= sa.func.now())
        .order_by(StudentLsReview.due_at))).scalars().all()
    for rv in due:
        if rv.ls_id in ex:
            continue
        if rv.is_student:
            row = await db.get(_SLS, rv.ls_id)
            if row is not None and row.status == "published" and row.owner_id == user.id:
                return {"best": ("student", row), "theta": theta, "target": target, "weak_hit": False, "review": True}
        else:
            row = await db.get(LongSentence, rv.ls_id)
            if row is not None and row.status == "published":
                return {"best": ("platform", row), "theta": theta, "target": target, "weak_hit": False, "review": True}

    plat = (await db.execute(sa.select(LongSentence).where(LongSentence.status == "published"))).scalars().all()
    stu = (await db.execute(sa.select(StudentLongSentence).where(
        StudentLongSentence.owner_id == user.id, StudentLongSentence.status == "published"))).scalars().all()
    # 句法 node 边(平台句)
    node_map: dict = {}
    pids = [p.id for p in plat]
    if pids:
        for lsid, nid in (await db.execute(sa.select(
                LongSentenceNode.long_sentence_id, LongSentenceNode.node_id)
                .where(LongSentenceNode.long_sentence_id.in_(pids)))).all():
            node_map.setdefault(lsid, set()).add(nid)
    # 薄弱句法点(掌握度 < 0.6 或未掌握)
    weak = set((await db.execute(sa.select(StudentKp.node_id).where(
        StudentKp.student_id == user.id,
        sa.or_(StudentKp.mastery.is_(None), StudentKp.mastery < 0.6)))).scalars().all())

    def score(diff, nodes, is_stu, tbv, gr, sm):
        d = diff if diff is not None else target
        s = -abs(d - target)                 # 难度贴近 target(i+1)
        hit = bool(weak & nodes)
        if hit:
            s += 22                           # 薄弱句法点优先
        if tbv and tbv == tv:
            s += 14                           # 课程对齐:教材版
        if gr and gr == grade:
            s += 9                            # 年级
        if sm and sm == ps:
            s += 5                            # 学期
        if is_stu:
            s += 8                            # 个人真实材料(自己作业)
        s += random.uniform(0, 6)             # 抖动,避免每次都同一句
        return s, hit

    best = None
    best_sc = -1e18
    best_hit = False
    for p in plat:
        if p.id in ex:
            continue
        sc, hit = score(p.difficulty, node_map.get(p.id, set()), False, p.textbook_version, p.grade, p.semester)
        if sc > best_sc:
            best_sc, best, best_hit = sc, ("platform", p), hit
    for s in stu:
        if s.id in ex:
            continue
        sc, hit = score(s.difficulty, set(), True, None, None, None)
        if sc > best_sc:
            best_sc, best, best_hit = sc, ("student", s), hit
    return {"best": best, "theta": theta, "target": target, "weak_hit": best_hit, "review": False}


# ── 抽取选项(供后台精确挑范围)────────────────────────────────────────────────
async def textbook_extract_units(db: AsyncSession) -> list[dict]:
    """可抽取的教材单元(有阅读短文的),供级联多选:版本/年级/册/单元。"""
    from app.models.d4_knowledge import CurriculumUnit, CurriculumUnitPassage
    sub = sa.select(CurriculumUnitPassage.unit_id).where(CurriculumUnitPassage.kind == "阅读")
    rows = (await db.execute(
        sa.select(CurriculumUnit.id, CurriculumUnit.textbook_version, CurriculumUnit.grade,
                  CurriculumUnit.semester, CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .where(CurriculumUnit.id.in_(sub))
        .order_by(CurriculumUnit.textbook_version, CurriculumUnit.grade,
                  CurriculumUnit.semester, CurriculumUnit.unit_no))).all()
    return [{
        "unit_id": str(r[0]), "textbook_version": r[1], "grade": r[2], "semester": r[3],
        "unit_no": r[4], "unit_title": r[5], "stage": _stage_from_grade(r[2]),
    } for r in rows]


async def real_extract_dimensions(db: AsyncSession) -> dict:
    """平台真题(type=real)可选维度的去重值,供多选。"""
    pq = PlatformQuestion
    base = pq.type == "real"

    async def _distinct(col):
        return sorted(v for v in (await db.execute(
            sa.select(col).where(base, col.isnot(None)).distinct())).scalars().all() if v)

    regions = (await db.execute(
        sa.select(pq.region_code, pq.region_name).where(base, pq.region_code.isnot(None)).distinct())).all()
    return {
        "textbook_version": await _distinct(pq.textbook_version),
        "stage": await _distinct(pq.stage),
        "grade": await _distinct(pq.grade),
        "semester": await _distinct(pq.semester),
        "exam_type": await _distinct(pq.exam_type),
        "region": [{"code": c, "name": n} for c, n in sorted(set(regions), key=lambda x: x[0])],
    }


async def run_extract(
    db: AsyncSession, *, sources: list[str] | None = None, limit: int | None = None,
    min_words: int | None = None, dry_run: bool = False, filters: dict | None = None,
) -> ExtractStats:
    """按来源批量抽取。filters 按维度挑范围(各源取相关子集);sources 缺省读配置。"""
    cfg = await get_config(db)
    if sources is None:
        sources = cfg.get("sources") or ["platform_real"]
    if min_words is None:   # 缺省总是读配置(长句最小词数),无论是否显式指定来源
        min_words = int(cfg.get("min_words") or DEFAULT_MIN_WORDS)
    merged = ExtractStats()
    for src in sources:
        fn = _SOURCE_KIND_TO_FN.get(src)
        if fn is None:
            continue
        st = await fn(db, limit=limit, min_words=min_words, dry_run=dry_run, filters=filters)
        merged.scanned += st.scanned
        merged.sentences += st.sentences
        merged.long_kept += st.long_kept
        merged.created += st.created
        merged.skipped_done += st.skipped_done
        merged.edges += st.edges
        merged.candidates += st.candidates
        merged.syntax_points.update(st.syntax_points)
    return merged
