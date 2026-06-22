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
from app.services.llm_provider import chat_completion, is_llm_dev_mode

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
                     min_words=None, required_pass=None) -> dict:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d9_system import SystemConfig
    updates = {"long_sentence.sources": sources, "long_sentence.verify_types": verify_types,
               "long_sentence.min_words": min_words, "long_sentence.required_pass": required_pass}
    for key, val in updates.items():
        if val is None:
            continue
        await db.execute(
            pg_insert(SystemConfig).values(id=uuid.uuid4(), key=key, value=val, updated_by=updated_by)
            .on_conflict_do_update(index_elements=["key"], set_={"value": val, "updated_by": updated_by}))
    await db.flush()
    return await get_config(db)


async def list_for_review(
    db: AsyncSession, *, status: str = "draft", node_id: uuid.UUID | None = None,
    skip: int = 0, limit: int = 20,
) -> tuple[list[LongSentence], int]:
    base = sa.select(LongSentence).where(LongSentence.status == status)
    if node_id is not None:
        base = base.join(LongSentenceNode, LongSentenceNode.long_sentence_id == LongSentence.id).where(
            LongSentenceNode.node_id == node_id)
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(LongSentence.created_at).offset(skip).limit(limit))).scalars().all()
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
    ls.analysis_json = await analyze_sentence(ls.text)
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


def is_long_sentence(sentence: str, min_words: int = DEFAULT_MIN_WORDS) -> bool:
    """长难句 = 词数达阈值 且 含结构信号(从句/非谓语)。"""
    words = re.findall(r"[A-Za-z'\-]+", sentence)
    if len(words) < min_words:
        return False
    return bool(detect_syntax_points(sentence))


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
        return _enrich_analysis({
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
    # 重试:推理模型偶发把 token 预算耗在推理上、返回空内容(finish_reason=length)→ 再试一次
    for _attempt in range(2):
        try:
            resp = await chat_completion(system_prompt=system, user_prompt=user, max_tokens=8192,
                                         response_format={"type": "json_object"})
            data = json.loads(resp.choices[0].message.content or "{}")
            if data.get("segments"):          # 拿到有效结构 → 用之
                return _enrich_analysis(data, sentence, syntax)
        except Exception as exc:  # noqa: BLE001
            _log.warning("analyze_sentence attempt %d failed: %s", _attempt + 1, exc)
    return _enrich_analysis({"sentence_type": "", "translation": "", "summary": "",
                             "segments": [], "structure": [], "components": {},
                             "key_words": [], "grammar_points": [], "explanations": []},
                            sentence, syntax)


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


# ── 验证题型(L3 客观自动判分 / L4 主观 AI·发音评测)────────────────────────────
_OBJECTIVE_TYPES = {"cloze", "struct_type", "main_clause"}
_SUBJECTIVE_TYPES = {"translate", "rewrite", "span_label", "read_aloud"}  # L4:AI 评分 / 发音评测
_IMPLEMENTED_TYPES = _OBJECTIVE_TYPES | _SUBJECTIVE_TYPES
_READ_ALOUD_PASS = 60          # 朗读发音通过分阈值
_SUBJ_SIM_PASS = 0.5           # dev 主观判分相似度阈值(生产走 LLM)
_ALL_VERIFY_TYPES = ["cloze", "struct_type", "main_clause", "translate",
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
        mc = a.get("main_clause")
        if not mc:
            return None
        return {"type": verify_type, "prompt": "该句的主干(主谓宾核心)是?",
                "options": [mc, "(无主干)", mc.split()[0] if mc.split() else "X", "全句即主干"],
                "answer": mc}
    if verify_type == "cloze":
        # 挖掉句中第一个出现的关系/连接词
        for w in _REL_WORDS:
            if re.search(rf"\b{w}\b", ls.text, re.I):
                blanked = re.sub(rf"\b{w}\b", "____", ls.text, count=1, flags=re.I)
                distract = [x for x in _REL_WORDS if x.lower() != w.lower()][:3]
                return {"type": verify_type, "prompt": f"填入恰当的连接词:{blanked}",
                        "options": [w] + distract, "answer": w}
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
        resp = await chat_completion(system_prompt=system, user_prompt=user, max_tokens=32,
                                     response_format={"type": "json_object"})
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
        if correct:
            sk = (await db.execute(
                sa.select(StudentKp).where(StudentKp.student_id == student_id, StudentKp.node_id == nid)
            )).scalar_one_or_none()
            if sk is not None and (sk.practice_count - sk.wrong_count) >= required_pass \
                    and (sk.mastery is None or float(sk.mastery) < 1.0):
                sk.mastery = 1.0
                mastered.append(n["name"])
        else:
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


async def _persist_long_sentences(
    db: AsyncSession, st: ExtractStats, *, text: str, scope: str, source_kind: str,
    min_words: int, dry_run: bool, owner_id: uuid.UUID | None = None,
    source_q_scope: str | None = None, source_question_id: uuid.UUID | None = None,
    source_passage_id: uuid.UUID | None = None,
) -> None:
    """三源共用:切句 → 长句判定 → AI 拆解 → 建 long_sentence → match_kp 挂句法 node / 落候选。"""
    for sent in split_sentences(text or ""):
        st.sentences += 1
        if not is_long_sentence(sent, min_words):
            continue
        st.long_kept += 1
        analysis = await analyze_sentence(sent)
        st.syntax_points.update(analysis.get("syntax_points") or [])
        if dry_run:
            st.created += 1
            continue
        ls = LongSentence(
            id=uuid.uuid4(), scope=scope, owner_id=owner_id, source_kind=source_kind,
            source_q_scope=source_q_scope, source_question_id=source_question_id,
            source_passage_id=source_passage_id,
            text=sent, analysis_json=analysis, status="draft",
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
    dry_run: bool = False, only_question_ids: set | None = None,
) -> ExtractStats:
    """① 扫平台真题(type='real')未抽过的 → 长难句。幂等按 source_question_id;only_* 供测试限定。"""
    st = ExtractStats()
    q = sa.select(PlatformQuestion).where(PlatformQuestion.type == "real")
    if only_question_ids is not None:
        q = q.where(PlatformQuestion.id.in_(only_question_ids))
    if limit is not None:
        q = q.limit(limit)
    for pq in (await db.execute(q)).scalars().all():
        st.scanned += 1
        if await _already_extracted(db, pq.id):
            st.skipped_done += 1
            continue
        await _persist_long_sentences(
            db, st, text=pq.stem or "", scope="platform", source_kind="platform_real",
            source_q_scope="platform", source_question_id=pq.id,
            min_words=min_words, dry_run=dry_run)
        if not dry_run:
            await db.flush()
    await (db.rollback() if dry_run else db.commit())
    return st


async def extract_from_textbook(
    db: AsyncSession, *, limit: int | None = None, min_words: int = DEFAULT_MIN_WORDS,
    dry_run: bool = False, only_passage_ids: set | None = None,
) -> ExtractStats:
    """② 扫平台语料 Passage(reading_text/dialogue)未抽过的 → 长难句(平台域)。幂等按 source_passage_id。"""
    from app.models.d16_question_domain import Passage
    st = ExtractStats()
    q = sa.select(Passage).where(
        Passage.scope == "platform", Passage.kind.in_(["reading_text", "dialogue"]),
        Passage.text.isnot(None))
    if only_passage_ids is not None:
        q = q.where(Passage.id.in_(only_passage_ids))
    if limit is not None:
        q = q.limit(limit)
    for pg in (await db.execute(q)).scalars().all():
        st.scanned += 1
        if await _already_extracted_passage(db, pg.id):
            st.skipped_done += 1
            continue
        await _persist_long_sentences(
            db, st, text=pg.text or "", scope="platform", source_kind="textbook",
            source_passage_id=pg.id, min_words=min_words, dry_run=dry_run)
        if not dry_run:
            await db.flush()
    await (db.rollback() if dry_run else db.commit())
    return st


async def extract_from_uploaded(
    db: AsyncSession, *, owner_id: uuid.UUID | None = None, limit: int | None = None,
    min_words: int = DEFAULT_MIN_WORDS, dry_run: bool = False, only_question_ids: set | None = None,
) -> ExtractStats:
    """③ 扫学生上传题(owner_scope='student')未抽过的 → 长难句(个人域,owner_id=该生)。

    幂等按 source_question_id;owner_id 限定单生,only_* 供测试限定。
    """
    from app.models.d16_question_domain import UploadedQuestion
    st = ExtractStats()
    q = sa.select(UploadedQuestion).where(
        UploadedQuestion.owner_scope == "student", UploadedQuestion.stem.isnot(None))
    if owner_id is not None:
        q = q.where(UploadedQuestion.owner_id == owner_id)
    if only_question_ids is not None:
        q = q.where(UploadedQuestion.id.in_(only_question_ids))
    if limit is not None:
        q = q.limit(limit)
    for uq in (await db.execute(q)).scalars().all():
        st.scanned += 1
        if await _already_extracted(db, uq.id):
            st.skipped_done += 1
            continue
        await _persist_long_sentences(
            db, st, text=uq.stem or "", scope="student", owner_id=uq.owner_id,
            source_kind="uploaded", source_q_scope="uploaded", source_question_id=uq.id,
            min_words=min_words, dry_run=dry_run)
        if not dry_run:
            await db.flush()
    await (db.rollback() if dry_run else db.commit())
    return st


_SOURCE_KIND_TO_FN = {
    "platform_real": extract_from_platform,
    "textbook": extract_from_textbook,
    "uploaded": extract_from_uploaded,
}


async def run_extract(
    db: AsyncSession, *, sources: list[str] | None = None, limit: int | None = None,
    min_words: int | None = None, dry_run: bool = False,
) -> ExtractStats:
    """按来源配置批量抽取(sources 缺省读 long_sentence.sources)。合并各源 ExtractStats。"""
    if sources is None:
        cfg = await get_config(db)
        sources = cfg.get("sources") or ["platform_real"]
        if min_words is None:
            min_words = int(cfg.get("min_words") or DEFAULT_MIN_WORDS)
    if min_words is None:
        min_words = DEFAULT_MIN_WORDS
    merged = ExtractStats()
    for src in sources:
        fn = _SOURCE_KIND_TO_FN.get(src)
        if fn is None:
            continue
        st = await fn(db, limit=limit, min_words=min_words, dry_run=dry_run)
        merged.scanned += st.scanned
        merged.sentences += st.sentences
        merged.long_kept += st.long_kept
        merged.created += st.created
        merged.skipped_done += st.skipped_done
        merged.edges += st.edges
        merged.candidates += st.candidates
        merged.syntax_points.update(st.syntax_points)
    return merged
