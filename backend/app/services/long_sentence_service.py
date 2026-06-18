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
