"""课程精讲单元列表公共处理:当前学期解析 / 下一学期导航 / 顺序解锁 + 学期通关。

三个模块(词/语法/长难句)的 course_units 共用:
- resolve_semester:默认聚焦学生当前学期(preferred_grade/semester),缺省回退教材第一个学期。
- next_semester:学完当前学期后「预习下学期」跳转目标。
- decorate_units:闯关地图顺序解锁 + 判「本学期通关」(触发庆祝弹层)。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import CurriculumUnit


async def _semesters(db: AsyncSession, tv: str) -> list[tuple]:
    rows = (await db.execute(
        sa.select(CurriculumUnit.grade, CurriculumUnit.semester)
        .where(CurriculumUnit.textbook_version == tv)
        .group_by(CurriculumUnit.grade, CurriculumUnit.semester)
        .order_by(CurriculumUnit.grade, CurriculumUnit.semester))).all()
    return [(g, s) for g, s in rows]


def _clean(v):
    """挡掉前端可能传来的字符串 'undefined'/'null'/空,避免 enum/查询报错。"""
    v = (v or "").strip() if isinstance(v, str) else v
    return v if v and v not in ("undefined", "null") else None


async def resolve_semester(db: AsyncSession, tv: str, student, grade, semester):
    """入参优先;否则用学生 preferred_grade/preferred_semester;都无则回退教材第一个学期。"""
    grade, semester = _clean(grade), _clean(semester)
    g = grade or (getattr(student, "preferred_grade", None) if student else None)
    s = semester or (getattr(student, "preferred_semester", None) if student else None)
    if not g or not s:
        seq = await _semesters(db, tv)
        if seq:
            g = g or seq[0][0]
            s = s or seq[0][1]
    return g, s


async def next_semester(db: AsyncSession, tv: str, grade, semester):
    """教材里 (grade,semester) 的下一个学期;已是最后一册则 None。"""
    seq = await _semesters(db, tv)
    try:
        i = seq.index((grade, semester))
    except ValueError:
        return None
    return ({"grade": seq[i + 1][0], "semester": seq[i + 1][1]}
            if i + 1 < len(seq) else None)


def decorate_units(units: list[dict]) -> bool:
    """给按 unit_no 升序的单元列表加 unlocked,返回本学期是否通关。
    每项须已有 studied / total。解锁规则:第 1 关恒解锁;上一关通关即解锁;
    **本关已有学习痕迹(studied>0,可能来自作业精讲同词)也解锁**,不把有进度的单元锁住。"""
    prev_done = True
    for u in units:
        st = int(u.get("studied") or 0)
        tot = int(u.get("total") or 0)
        u["studied"], u["total"] = st, tot
        done = tot == 0 or st >= tot
        u["unlocked"] = bool(prev_done or st > 0 or done)
        prev_done = done
    return bool(units) and all((u["total"] == 0 or u["studied"] >= u["total"]) for u in units)
