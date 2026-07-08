"""教材主数据(curriculum_catalog)服务——版本/年级/学期 唯一真源 + 上下架。

全站「版本/年级/学期」可选项与学生内容可见性均以本表为准(见 CLAUDE.md「主数据上架/下架」铁律)。
- 消费侧(学生小程序 / 机构平台):只见 published(上架)。
- admin 后台:上架/下架全部可见可管(include_unpublished=True)。
上架粒度 = 版本 + 年级 + 学期 组合;可先建版本(内容后补)。
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import CurriculumCatalog

_STATUSES = {"draft", "published"}


def _grade_rank(g: str) -> tuple:
    """年级排序:小学<初中<高中,同学段按数字。无法解析的排最后(按名)。"""
    import re
    m = re.match(r"^(小学|初中|高中)?(\d+)", g or "")
    stage = {"小学": 0, "初中": 1, "高中": 2}.get(m.group(1), 3) if m else 9
    num = int(m.group(2)) if m and m.group(2) else 99
    return (stage, num, g or "")


async def list_catalog(
    db: AsyncSession,
    *,
    include_unpublished: bool = False,
    textbook_version: str | None = None,
    grade: str | None = None,
    semester: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """分页列出教材目录(admin 传 include_unpublished=True 见全部)。返回 {total, items}。"""
    conds = []
    if not include_unpublished:
        conds.append(CurriculumCatalog.status == "published")
    if textbook_version:
        conds.append(CurriculumCatalog.textbook_version == textbook_version)
    if grade:
        conds.append(CurriculumCatalog.grade == grade)
    if semester:
        conds.append(CurriculumCatalog.semester == semester)

    total = (await db.execute(
        select(func.count()).select_from(CurriculumCatalog).where(*conds)
    )).scalar_one()
    rows = (await db.execute(
        select(CurriculumCatalog).where(*conds)
        .order_by(CurriculumCatalog.textbook_version, CurriculumCatalog.grade, CurriculumCatalog.semester)
        .offset(skip).limit(limit)
    )).scalars().all()
    items = [{
        "id": str(r.id),
        "textbook_version": r.textbook_version,
        "grade": r.grade,
        "semester": r.semester,
        "status": r.status,
        "sort_order": r.sort_order,
    } for r in rows]
    return {"total": total, "items": items}


async def add_offering(db: AsyncSession, *, textbook_version: str, grade: str, semester: str) -> dict:
    """新增一条目录(版本+年级+学期),默认下架(draft)。已存在则返回既有行(幂等)。"""
    textbook_version, grade, semester = textbook_version.strip(), grade.strip(), semester.strip()
    if not (textbook_version and grade and semester):
        raise ValueError("版本/年级/学期均不能为空")
    stmt = (
        pg_insert(CurriculumCatalog)
        .values(id=uuid.uuid4(), textbook_version=textbook_version, grade=grade,
                semester=semester, status="draft")
        .on_conflict_do_nothing(index_elements=["textbook_version", "grade", "semester"])
    )
    await db.execute(stmt)
    await db.commit()
    row = (await db.execute(select(CurriculumCatalog).where(
        CurriculumCatalog.textbook_version == textbook_version,
        CurriculumCatalog.grade == grade,
        CurriculumCatalog.semester == semester,
    ))).scalars().first()
    return {"id": str(row.id), "textbook_version": row.textbook_version, "grade": row.grade,
            "semester": row.semester, "status": row.status}


async def set_status(db: AsyncSession, *, catalog_id: uuid.UUID, status: str) -> int:
    """上架/下架一条目录(published/draft)。"""
    if status not in _STATUSES:
        raise ValueError(f"非法状态:{status}")
    r = await db.execute(update(CurriculumCatalog).where(CurriculumCatalog.id == catalog_id)
                         .values(status=status))
    await db.commit()
    return r.rowcount or 0


async def delete_offering(db: AsyncSession, *, catalog_id: uuid.UUID) -> int:
    """删除一条目录(仅移除可选项/可见闸门,不动已上传的教材单元内容)。"""
    r = await db.execute(delete(CurriculumCatalog).where(CurriculumCatalog.id == catalog_id))
    await db.commit()
    return r.rowcount or 0


async def is_published(db: AsyncSession, *, textbook_version: str, grade: str, semester: str) -> bool:
    """该 版本+年级+学期 组合是否已上架(学生内容可见闸门)。"""
    st = (await db.execute(select(CurriculumCatalog.status).where(
        CurriculumCatalog.textbook_version == textbook_version,
        CurriculumCatalog.grade == grade,
        CurriculumCatalog.semester == semester,
    ))).scalar_one_or_none()
    return st == "published"


async def preference_options(db: AsyncSession, *, include_unpublished: bool = False) -> dict:
    """教材版本/年级/学期可选值——以教材主数据为唯一真源 + 上架过滤。

    消费侧(学生/机构)只见上架组合派生的版本/年级/学期;admin 传 include_unpublished 见全部。
    版本/年级/学期均只保留「有上架目录」的取值,数量与后台维护天然对齐;年级按学段+数字排序。
    """
    conds = [] if include_unpublished else [CurriculumCatalog.status == "published"]
    rows = (await db.execute(select(
        CurriculumCatalog.textbook_version, CurriculumCatalog.grade, CurriculumCatalog.semester,
    ).where(*conds).distinct())).all()
    versions = sorted({t for t, _g, _s in rows})
    grades = sorted({g for _t, g, _s in rows}, key=_grade_rank)
    semesters = sorted({s for _t, _g, s in rows})   # '上'<'下'(拼音序恰好)
    return {"textbook_versions": versions, "grades": grades, "semesters": semesters}
