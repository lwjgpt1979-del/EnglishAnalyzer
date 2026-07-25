"""作业阅读题·题型细标(reading_skill)服务 —— P1「阅读理解学情统计」。

目标表:user_paper_questions(学生上传作业题,section_type='reading' 的阅读小题)。
题型细标固定 8 类。产出路径:
  ① 精讲顺手写 —— reading_intensive_service.question_analysis 里落 reading_skill;
  ② 回填 backfill —— 存量从 reading_analysis_cache 按题 md5 命中,或同内容邻题已标则复制;
  ③ 补跑 classify —— 仍未标的按内容去重后调 LLM 归类(feature=reading_qtype_classify,快档);
  ④ admin 复核 set_skill 人工改。
对错用现成 is_wrong,不建表。第三方付费暂存:同内容(md5)只归类一次(回填/邻题/批内去重)。
"""
from __future__ import annotations

import hashlib
import json as _json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d13_v2_user_papers import (
    ReadingAnalysisCache, UserPaperQuestion, UserPaperSection,
)

# 固定 8 类(与精讲 skill 对齐;统计口径单一,避免同义异名分散)
SKILLS: list[str] = [
    "细节理解", "主旨大意", "推理判断", "词义猜测",
    "作者态度", "指代关系", "图表数字", "其他",
]

# 归一映射:精讲输出的自由中文 skill → 固定枚举(命中即取,顺序即优先级)
_SKILL_RULES: list[tuple[tuple[str, ...], str]] = [
    (("细节",), "细节理解"),
    (("主旨", "大意", "标题", "中心", "概括"), "主旨大意"),
    (("推理", "推断", "推测", "暗示", "隐含"), "推理判断"),
    (("词义", "猜词", "含义", "词汇"), "词义猜测"),
    (("态度", "观点", "情感", "语气", "作者"), "作者态度"),
    (("指代", "代词", "指的是", "refer"), "指代关系"),
    (("图表", "数字", "数据"), "图表数字"),
]


def normalize_skill(raw: str | None) -> str:
    """自由中文题型名 → 固定 8 类之一;识别不了归「其他」。"""
    s = (raw or "").strip()
    if not s:
        return "其他"
    if s in SKILLS:
        return s
    for keys, canon in _SKILL_RULES:
        if any(k in s for k in keys):
            return canon
    return "其他"


def _content_md5(q: UserPaperQuestion) -> str:
    """与 reading_intensive_service.question_analysis 完全一致的题 md5(用于命中同一缓存)。
    UserPaperQuestion 无独立 options 列(选项内嵌题干)→ options 段恒为 []。"""
    context = (q.passage or q.stem or "").strip()
    key = f"{context}||{q.stem or ''}||{_json.dumps([], ensure_ascii=False)}||{q.correct_answer or ''}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()  # noqa: S324


def _reading_q_stmt():
    """所有「作业阅读小题」:归属 section_type='reading' 的题。"""
    return (select(UserPaperQuestion)
            .join(UserPaperSection,
                  UserPaperSection.id == UserPaperQuestion.section_id)
            .where(UserPaperSection.section_type == "reading"))


async def backfill(db: AsyncSession) -> dict:
    """存量回填:未标题型的阅读题,先从 reading_analysis_cache(精讲已算)按 md5 命中,
    再从同内容已标邻题复制。不调 LLM、不花钱。返回 {scanned, filled, still_missing}。"""
    rows = (await db.execute(_reading_q_stmt())).scalars().all()
    if not rows:
        return {"scanned": 0, "filled": 0, "still_missing": 0}
    # 内容 md5 → 已知题型(来自已标邻题)
    md5_of: dict[uuid.UUID, str] = {q.id: _content_md5(q) for q in rows}
    known: dict[str, str] = {}
    for q in rows:
        if q.reading_skill:
            known.setdefault(md5_of[q.id], q.reading_skill)
    # 缺的题的 md5 → 查缓存
    missing = [q for q in rows if not q.reading_skill]
    need_md5 = {md5_of[q.id] for q in missing if md5_of[q.id] not in known}
    if need_md5:
        cache_rows = (await db.execute(
            select(ReadingAnalysisCache.q_md5, ReadingAnalysisCache.analysis)
            .where(ReadingAnalysisCache.q_md5.in_(need_md5)))).all()
        for md5, ana in cache_rows:
            sk = normalize_skill((ana or {}).get("skill"))
            known[md5] = sk
    filled = 0
    for q in missing:
        sk = known.get(md5_of[q.id])
        if sk:
            q.reading_skill = sk
            filled += 1
    if filled:
        await db.commit()
    still = sum(1 for q in missing if not q.reading_skill)
    return {"scanned": len(rows), "filled": filled, "still_missing": still}


_CLASSIFY_SYS = (
    "你是中小学英语阅读题题型归类助手。判断给定阅读小题属于哪种题型,"
    "只返回 JSON:{\"skill\":\"题型\"}。题型必须是以下之一:"
    "细节理解 / 主旨大意 / 推理判断 / 词义猜测 / 作者态度 / 指代关系 / 图表数字 / 其他。"
)


async def classify_missing(db: AsyncSession, *, limit: int = 100) -> dict:
    """补跑归类:回填后仍未标的阅读题,按内容 md5 去重(同内容只调一次)后调 LLM。
    limit = 本次最多归类的「不同内容」数(成本闸)。返回 {classified_contents, tagged_questions, remaining}。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    rows = (await db.execute(
        _reading_q_stmt().where(UserPaperQuestion.reading_skill.is_(None)))
    ).scalars().all()
    if not rows:
        return {"classified_contents": 0, "tagged_questions": 0, "remaining": 0}
    # 按内容 md5 分组,去重
    groups: dict[str, list[UserPaperQuestion]] = {}
    for q in rows:
        groups.setdefault(_content_md5(q), []).append(q)
    md5s = list(groups.keys())
    todo = md5s[:limit]
    classified = 0
    tagged = 0
    for md5 in todo:
        grp = groups[md5]
        sample = grp[0]
        context = (sample.passage or sample.stem or "").strip()
        if is_llm_dev_mode():
            sk = "细节理解"
        else:
            user = (f"【原文】\n{context[:2000]}\n\n【题目】{sample.stem or ''}\n"
                    f"【正确答案】{sample.correct_answer or '未知'}")
            try:
                data = await complete_json(
                    system_prompt=_CLASSIFY_SYS, user_prompt=user,
                    model=fast_model(), disable_thinking=True, max_tokens=64,
                    feature="reading_qtype_classify") or {}
            except Exception:  # noqa: BLE001
                continue
            sk = normalize_skill(data.get("skill"))
        for q in grp:
            q.reading_skill = sk
            tagged += 1
        classified += 1
    if tagged:
        await db.commit()
    return {"classified_contents": classified, "tagged_questions": tagged,
            "remaining": len(md5s) - len(todo)}


async def stats(db: AsyncSession) -> dict:
    """概况:阅读题总数 / 已标 / 未标 + 按题型分布。"""
    total = (await db.execute(
        select(func.count()).select_from(_reading_q_stmt().subquery()))).scalar() or 0
    dist_rows = (await db.execute(
        select(UserPaperQuestion.reading_skill, func.count())
        .join(UserPaperSection, UserPaperSection.id == UserPaperQuestion.section_id)
        .where(UserPaperSection.section_type == "reading")
        .group_by(UserPaperQuestion.reading_skill))).all()
    dist = {(sk or "未标"): int(c) for sk, c in dist_rows}
    tagged = sum(c for sk, c in dist.items() if sk != "未标")
    return {"total": int(total), "tagged": tagged, "untagged": int(total) - tagged,
            "distribution": dist}


async def list_admin(db: AsyncSession, *, skill: str | None = None,
                     only_untagged: bool = False, skip: int = 0,
                     limit: int = 50) -> tuple[list[dict], int]:
    """admin 归类页逐题列表(分页)。skill 筛某题型;only_untagged 只看未标。"""
    stmt = _reading_q_stmt()
    if only_untagged:
        stmt = stmt.where(UserPaperQuestion.reading_skill.is_(None))
    elif skill:
        stmt = stmt.where(UserPaperQuestion.reading_skill == skill)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(UserPaperQuestion.created_at.desc())
        .offset(skip).limit(limit))).scalars().all()
    items = [{
        "id": str(q.id),
        "stem": (q.stem or "")[:160],
        "skill": q.reading_skill,
        "is_wrong": bool(q.is_wrong),
        "has_passage": bool(q.passage),
    } for q in rows]
    return items, int(total)


async def set_skill(db: AsyncSession, *, question_id: uuid.UUID, skill: str) -> bool:
    """admin 人工改题型(复核)。skill 必须是固定 8 类之一。"""
    if skill not in SKILLS:
        return False
    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        return False
    q.reading_skill = skill
    await db.commit()
    return True
