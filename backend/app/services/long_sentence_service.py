"""长难句解析服务(L1):长句判定 + AI 结构拆解 + 平台真题抽取(挂句法 node)。

抽取来源由配置 long_sentence.sources 控(默认 ['platform_real']);三来源同构,L1 实现平台真题。
句子有源(记 source 指针),AI 拆解出主干/分层/译文/句法点 → match_kp 挂句法 knowledge_nodes。
dev 模式拆解走确定性 mock(按结构信号词推句法点),不调真实 LLM。
"""
from __future__ import annotations

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


async def analyze_sentence(sentence: str) -> dict:
    """AI 结构拆解 → analysis_json。dev 确定性 mock;生产走 LLM。"""
    syntax = detect_syntax_points(sentence)
    if is_llm_dev_mode():
        words = sentence.split()
        return {
            "main_clause": " ".join(words[:8]) + ("…" if len(words) > 8 else ""),
            "layers": [{"type": p, "text": sentence} for p in syntax],
            "translation": f"[译] {sentence[:30]}…",
            "difficulty_points": syntax or ["长句修饰"],
            "syntax_points": syntax,
        }
    system = ("你是英语语法专家。把给定长难句拆解为:主干(SVO)、各修饰/从句成分及类型、"
              "中文翻译、难点、涉及句法点名。严格输出 JSON。")
    user = (f"句子:{sentence}\n返回 JSON:"
            '{"main_clause":..,"layers":[{"type":..,"text":..}],"translation":..,'
            '"difficulty_points":[..],"syntax_points":[..]}')
    try:
        resp = await chat_completion(system_prompt=system, user_prompt=user, max_tokens=1024,
                                     response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
        data.setdefault("syntax_points", syntax)
        return data
    except Exception as exc:  # noqa: BLE001
        _log.warning("analyze_sentence LLM failed: %s", exc)
        return {"main_clause": "", "layers": [], "translation": "",
                "difficulty_points": [], "syntax_points": syntax}


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


# ── L3 验证·客观题 ────────────────────────────────────────────
# 客观题型(自动判分、可硬判掌握);主观题型(translate/span_label/rewrite/read_aloud)留 L4。
_OBJECTIVE_TYPES = {"cloze", "struct_type", "main_clause"}
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
    # 仅返回已实现(客观)且被配置开放的
    return [t for t in configured if t in _OBJECTIVE_TYPES]


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
    return None


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
    if verify_type not in _OBJECTIVE_TYPES:
        raise AppError(code=400, message="该验证题型暂不支持自动判分")
    q = build_verify(ls, verify_type)
    if q is None:
        raise AppError(code=400, message="该句无法生成此题型")

    correct = answer.strip() == str(q["answer"]).strip()
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


async def extract_from_platform(
    db: AsyncSession, *, limit: int | None = None, min_words: int = DEFAULT_MIN_WORDS,
    dry_run: bool = False, only_question_ids: set | None = None,
) -> ExtractStats:
    """扫平台真题(type='real')未抽过的 → 切句 → 长句判定 → AI 拆解 → match_kp 挂句法 node → 落 long_sentence。

    幂等:按 source_question_id 标"已抽",复跑跳过。only_question_ids 供测试限定。
    """
    st = ExtractStats()
    q = sa.select(PlatformQuestion).where(PlatformQuestion.type == "real")
    if only_question_ids is not None:
        q = q.where(PlatformQuestion.id.in_(only_question_ids))
    if limit is not None:
        q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()

    for pq in rows:
        st.scanned += 1
        if await _already_extracted(db, pq.id):
            st.skipped_done += 1
            continue
        for sent in split_sentences(pq.stem or ""):
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
                id=uuid.uuid4(), scope="platform", source_kind="platform_real",
                source_q_scope="platform", source_question_id=pq.id,
                text=sent, analysis_json=analysis, status="draft",
            )
            db.add(ls)
            await db.flush()
            st.created += 1
            # 句法点 → match_kp 挂 node / 落候选
            for name in (analysis.get("syntax_points") or []):
                m = await match_kp(db, raw_name=name, axis_hint="knowledge", source_type="exam")
                if m.node_id is not None:
                    db.add(LongSentenceNode(long_sentence_id=ls.id, node_id=m.node_id))
                    st.edges += 1
                elif m.candidate_id is not None:
                    st.candidates += 1
        if not dry_run:
            await db.flush()

    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return st
