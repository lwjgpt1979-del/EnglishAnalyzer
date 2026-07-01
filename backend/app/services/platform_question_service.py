"""R2 平台题(真题/仿真)写入与生成。

统一进 platform_question(type=real|sim),小题挂 knowledge_nodes(走 kp_match_service)。
仿真**强制有源**(parent_real_id 派生 / is_fallback 备选,DB CHECK 兜底,见 m85)。

R2.1:真题导入 import_real_question + 挂 KP(继承/匹配)骨架 + 低层 add_sim(强校验)。
R2.2/R2.3:AI 改写派生仿真 / KP 直生备选 + 真题到来下架备选。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import (
    PlatformQuestion, PlatformQuestionKp, Passage, PlatformPaper,
)
from app.services.kp_match_service import match_kp
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_log = logging.getLogger(__name__)


_EXAM_COLS = ("textbook_version", "stage", "grade", "semester", "region_name", "exam_type")


def _exam_cols_from_meta(meta: dict | None) -> dict:
    """从批次 meta 提取可筛选字段(落 platform_question 独立列)。"""
    m = meta or {}
    out = {c: m.get(c) for c in _EXAM_COLS}
    out["region_code"] = m.get("city_code") or m.get("region_code")
    return out


@dataclass
class ImportResult:
    question_id: uuid.UUID
    matched_nodes: list[uuid.UUID] = field(default_factory=list)
    candidates: list[uuid.UUID] = field(default_factory=list)


async def create_passage(db: AsyncSession, *, text: str, kind: str = "reading_text") -> uuid.UUID:
    """新建一份题组语料(平台域),返回 passage.id;供阅读/完形/信息还原题组挂 block_id。"""
    p = Passage(id=uuid.uuid4(), scope="platform", kind=kind, text=text)
    db.add(p)
    await db.flush()
    return p.id


_STAGE_LABEL = {"小": "小学", "初": "初中", "高": "高中"}


def _compose_paper_name(meta: dict | None) -> str:
    """无显式试卷名时，由批次 meta 自动合成一个可读名。"""
    m = meta or {}
    parts = [
        m.get("region_name") or "",
        m.get("textbook_version") or "",
        m.get("grade") or _STAGE_LABEL.get(m.get("stage") or "", ""),
        f"{m.get('semester')}册" if m.get("semester") else "",
        m.get("exam_type") or "",
    ]
    name = " ".join(p for p in parts if p).strip()
    return name or "未命名试卷"


def _year_from_name(name: str | None) -> int | None:
    """从试卷名提取年份(1900–2099);取第一个四位年份。"""
    m = re.search(r"(19|20)\d{2}", name or "")
    return int(m.group(0)) if m else None


async def create_paper(db: AsyncSession, *, name: str | None, meta: dict | None) -> uuid.UUID:
    """整卷上传时建一份试卷，聚合其下所有真题；返回 paper.id。"""
    m = meta or {}
    pname = (name or "").strip() or _compose_paper_name(m)
    p = PlatformPaper(
        id=uuid.uuid4(), name=pname,
        textbook_version=m.get("textbook_version"), stage=m.get("stage"),
        grade=m.get("grade"), semester=m.get("semester"),
        region_code=m.get("city_code") or m.get("region_code"),
        region_name=m.get("region_name"), exam_type=m.get("exam_type"),
        status="draft", year=_year_from_name(pname), meta=m or None,
    )
    db.add(p)
    await db.flush()
    return p.id


async def existing_paper_names(db: AsyncSession, names: list[str]) -> set[str]:
    """返回 names 里**已存在**的试卷名集合(供上传查重去重)。"""
    names = [n for n in {(x or "").strip() for x in names} if n]
    if not names:
        return set()
    rows = (await db.execute(
        sa.select(PlatformPaper.name).where(PlatformPaper.name.in_(names)))).scalars().all()
    return set(rows)


async def create_paper_placeholder(
    db: AsyncSession, *, name: str | None, meta: dict | None,
    source_file_url: str | None, source_filename: str | None,
) -> uuid.UUID:
    """批量上传:建一份**草稿占位试卷**(0 题,挂原卷 word/pdf 的 COS 直链),题目延后解析。"""
    m = meta or {}
    pname = (name or "").strip() or _compose_paper_name(m)
    p = PlatformPaper(
        id=uuid.uuid4(), name=pname,
        textbook_version=m.get("textbook_version"), stage=m.get("stage"),
        grade=m.get("grade"), semester=m.get("semester"),
        region_code=m.get("city_code") or m.get("region_code"),
        region_name=m.get("region_name"), exam_type=m.get("exam_type"),
        status="draft", year=_year_from_name(pname), meta=m or None,
        source_file_url=source_file_url, source_filename=source_filename,
    )
    db.add(p)
    await db.flush()
    return p.id


async def list_papers(
    db: AsyncSession, *, status: str | None = None,
    textbook_version: str | None = None, stage: str | None = None,
    grade: str | None = None, exam_type: str | None = None,
    region_code: str | None = None, year: int | None = None,
    skip: int = 0, limit: int = 20
) -> tuple[list[tuple[PlatformPaper, int, int]], int]:
    """试卷分页:每项含 (paper, 题数, 已发布题数)。支持按教材/学段/年级/地区/考试/年份筛选;按年份倒序。"""
    base = sa.select(PlatformPaper)
    if status is not None:
        base = base.where(PlatformPaper.status == status)
    if textbook_version:
        base = base.where(PlatformPaper.textbook_version == textbook_version)
    if stage:
        base = base.where(PlatformPaper.stage == stage)
    if grade:
        base = base.where(PlatformPaper.grade == grade)
    if exam_type:
        base = base.where(PlatformPaper.exam_type == exam_type)
    if region_code:        # 前缀匹配:省码(2位)含其下所有市;市码(4位)精确
        base = base.where(PlatformPaper.region_code.like(f"{region_code}%"))
    if year:
        base = base.where(PlatformPaper.year == year)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    papers = (await db.execute(
        base.order_by(PlatformPaper.year.desc().nullslast(),
                      PlatformPaper.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    out: list[tuple[PlatformPaper, int, int]] = []
    for p in papers:
        cnt = (await db.execute(sa.select(sa.func.count()).where(
            PlatformQuestion.paper_id == p.id))).scalar_one()
        pub = (await db.execute(sa.select(sa.func.count()).where(
            PlatformQuestion.paper_id == p.id,
            PlatformQuestion.status == "published"))).scalar_one()
        out.append((p, cnt, pub))
    return out, total


def _qnum(no: str | None) -> int:
    """题号前导数字,用于卷内排序;无则置大数殿后。"""
    m = re.match(r"\s*(\d+)", no or "")
    return int(m.group(1)) if m else 9999


# 标准卷面大题次序(关键词命中即定序);同一事务 created_at 相同不可靠,故用此还原卷序
_SECTION_ORDER = [
    "听力", "单项", "单选", "语法", "完形", "完型", "阅读理解", "信息还原",
    "单词", "选词", "短文填空", "首字母", "完成句子", "翻译", "句子", "阅读表达",
    "书面", "作文",
]


def _section_rank(section: str | None) -> int:
    s = section or ""
    for i, kw in enumerate(_SECTION_ORDER):
        if kw in s:
            return i
    return len(_SECTION_ORDER)      # 未知大题殿后(再按出现序细分)


async def paper_questions(
    db: AsyncSession, paper_id: uuid.UUID
) -> tuple[PlatformPaper | None, list[PlatformQuestion], dict[uuid.UUID, str | None]]:
    """试卷详情:试卷 + 其全部真题 + 题组短文映射。

    稳定排序(大题首次出现次序 → 题号 → created_at):即使入库 created_at 乱序,
    也能把同一大题归并、题号顺序还原,贴近原卷呈现。
    """
    paper = await db.get(PlatformPaper, paper_id)
    if paper is None:
        return None, [], {}
    rows = list((await db.execute(
        sa.select(PlatformQuestion).where(
            PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real"
        ).order_by(PlatformQuestion.created_at)
    )).scalars().all())
    seen: dict[str, int] = {}
    for r in rows:
        seen.setdefault(r.section or "", len(seen))
    # 主序:标准大题次序;未知大题按出现序殿后;段内按题号
    rows.sort(key=lambda r: (_section_rank(r.section), seen.get(r.section or "", 0), _qnum(r.question_no)))
    pmap = await passages_for(db, [r.block_id for r in rows if r.block_id])
    return paper, rows, pmap


async def delete_papers(db: AsyncSession, paper_ids: list[uuid.UUID]) -> int:
    """批量删除试卷:连带删其真题、派生仿真、题组短文、KP 边、错题/作答引用、**COS 原文件**。返回删除卷数。"""
    if not paper_ids:
        return 0
    # 收集要删的 COS 原文件(原卷/转换后 PDF + 保留的原 .doc)
    cos_urls: list[str] = []
    for p in (await db.execute(sa.select(PlatformPaper).where(PlatformPaper.id.in_(paper_ids)))).scalars().all():
        if p.source_file_url:
            cos_urls.append(p.source_file_url)
        du = (p.meta or {}).get("doc_file_url")
        if du:
            cos_urls.append(du)
    real_ids = list((await db.execute(
        sa.select(PlatformQuestion.id).where(PlatformQuestion.paper_id.in_(paper_ids)))).scalars().all())
    block_ids = list({b for b in (await db.execute(
        sa.select(PlatformQuestion.block_id).where(
            PlatformQuestion.paper_id.in_(paper_ids),
            PlatformQuestion.block_id.isnot(None)))).scalars().all() if b})
    sim_ids = list((await db.execute(
        sa.select(PlatformQuestion.id).where(
            PlatformQuestion.parent_real_id.in_(real_ids)))).scalars().all()) if real_ids else []
    all_qids = real_ids + sim_ids

    if all_qids:
        # 题↔KP 边(虽 CASCADE,显式清更稳)+ 学生侧无 FK 的引用(错题/作答)
        await db.execute(sa.delete(PlatformQuestionKp).where(PlatformQuestionKp.question_id.in_(all_qids)))
        for tbl, col in (("wrong_record", "question_id"), ("answer_log", "question_id")):
            try:
                await db.execute(sa.text(f"DELETE FROM {tbl} WHERE {col} = ANY(:ids)"), {"ids": all_qids})
            except Exception:  # noqa: BLE001
                pass
    if sim_ids:   # 先删仿真(parent_real_id 自引用),再删真题
        await db.execute(sa.delete(PlatformQuestion).where(PlatformQuestion.id.in_(sim_ids)))
    if real_ids:
        await db.execute(sa.delete(PlatformQuestion).where(PlatformQuestion.id.in_(real_ids)))
    if block_ids:
        await db.execute(sa.delete(Passage).where(Passage.id.in_(block_ids)))
    res = await db.execute(sa.delete(PlatformPaper).where(PlatformPaper.id.in_(paper_ids)))
    # DB 删完后再删 COS 原文件(best-effort,失败不影响删卷)
    from app.services import pdf_upload_service as pus
    for u in cos_urls:
        await pus.delete_cos_url(u)
    return res.rowcount or 0


async def clear_paper_questions(db: AsyncSession, paper_id: uuid.UUID) -> int:
    """清空某卷下的真题(及派生仿真、题组短文、KP 边),**保留试卷本身**。供「重新解析」幂等重跑。"""
    real_ids = list((await db.execute(
        sa.select(PlatformQuestion.id).where(PlatformQuestion.paper_id == paper_id))).scalars().all())
    if not real_ids:
        return 0
    block_ids = list({b for b in (await db.execute(
        sa.select(PlatformQuestion.block_id).where(
            PlatformQuestion.paper_id == paper_id, PlatformQuestion.block_id.isnot(None)))).scalars().all() if b})
    sim_ids = list((await db.execute(
        sa.select(PlatformQuestion.id).where(PlatformQuestion.parent_real_id.in_(real_ids)))).scalars().all())
    all_qids = real_ids + sim_ids
    await db.execute(sa.delete(PlatformQuestionKp).where(PlatformQuestionKp.question_id.in_(all_qids)))
    for tbl, col in (("wrong_record", "question_id"), ("answer_log", "question_id")):
        try:
            await db.execute(sa.text(f"DELETE FROM {tbl} WHERE {col} = ANY(:ids)"), {"ids": all_qids})
        except Exception:  # noqa: BLE001
            pass
    if sim_ids:
        await db.execute(sa.delete(PlatformQuestion).where(PlatformQuestion.id.in_(sim_ids)))
    await db.execute(sa.delete(PlatformQuestion).where(PlatformQuestion.id.in_(real_ids)))
    if block_ids:
        await db.execute(sa.delete(Passage).where(Passage.id.in_(block_ids)))
    await db.flush()
    return len(real_ids)


async def publish_paper(db: AsyncSession, paper_id: uuid.UUID) -> int:
    """整卷发布:试卷下所有真题置 published + 试卷置 published;返回发布题数。"""
    paper = await db.get(PlatformPaper, paper_id)
    if paper is None:
        raise AppError(code=404, message="试卷不存在")
    res = await db.execute(
        sa.update(PlatformQuestion)
        .where(PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real")
        .values(status="published")
    )
    paper.status = "published"
    await db.flush()
    return res.rowcount or 0


async def passages_for(
    db: AsyncSession, block_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """批量取题组短文正文 {passage_id: text}，供列表按 block_id 聚合显示。"""
    ids = list({b for b in block_ids if b})
    if not ids:
        return {}
    rows = (await db.execute(
        sa.select(Passage.id, Passage.text).where(Passage.id.in_(ids))
    )).all()
    return {pid: text for pid, text in rows}


async def attach_node(db: AsyncSession, question_id: uuid.UUID, node_id: uuid.UUID) -> bool:
    """platform_question_kp 挂边(幂等)。返回是否新建。"""
    stmt = (
        pg_insert(PlatformQuestionKp)
        .values(question_id=question_id, node_id=node_id)
        .on_conflict_do_nothing(index_elements=["question_id", "node_id"])
        .returning(PlatformQuestionKp.question_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _node_ids_of(db: AsyncSession, question_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        sa.select(PlatformQuestionKp.node_id).where(PlatformQuestionKp.question_id == question_id)
    )).scalars().all())


async def detach_node(db: AsyncSession, question_id: uuid.UUID, node_id: uuid.UUID) -> None:
    """解挂 platform_question_kp 的一条题↔KP 边。"""
    await db.execute(
        sa.delete(PlatformQuestionKp).where(
            PlatformQuestionKp.question_id == question_id,
            PlatformQuestionKp.node_id == node_id)
    )


async def attach_node_to_section(
    db: AsyncSession, *, paper_id: uuid.UUID, section: str, node_id: uuid.UUID
) -> int:
    """把某试卷某大题下所有真题挂同一个知识点(幂等);返回该段题数。"""
    qids = list((await db.execute(
        sa.select(PlatformQuestion.id).where(
            PlatformQuestion.paper_id == paper_id,
            PlatformQuestion.type == "real",
            PlatformQuestion.section == section)
    )).scalars().all())
    for qid in qids:
        await attach_node(db, qid, node_id)
    return len(qids)


async def kps_of_questions(
    db: AsyncSession, question_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, str | None]]]:
    """批量取每题关联的受控知识点 {question_id: [(node_id, name, code), ...]}。"""
    if not question_ids:
        return {}
    rows = (await db.execute(
        sa.select(PlatformQuestionKp.question_id, KnowledgeNode.id,
                  KnowledgeNode.name, KnowledgeNode.code)
        .join(KnowledgeNode, KnowledgeNode.id == PlatformQuestionKp.node_id)
        .where(PlatformQuestionKp.question_id.in_(question_ids))
        .order_by(KnowledgeNode.code)
    )).all()
    out: dict[uuid.UUID, list[tuple[uuid.UUID, str, str | None]]] = {}
    for qid, nid, name, code in rows:
        out.setdefault(qid, []).append((nid, name, code))
    return out


async def import_real_question(
    db: AsyncSession, *,
    stem: str, answer: str | None = None, options: dict | list | None = None,
    question_type: str | None = None, explanation: str | None = None,
    difficulty: int | None = None, meta: dict | None = None,
    kp_names: list[str] | None = None, stage_hint: str | None = None,
    question_no: str | None = None, status: str = "published",
    block_id: uuid.UUID | None = None, paper_id: uuid.UUID | None = None,
    section: str | None = None,
) -> ImportResult:
    """导入一道真题 → platform_question(type='real'),kp_names 走受控匹配挂 node/落候选。

    命中某 node 后调 deprecate_fallbacks_for_node:该 node 有真题了 → 其 KP 直生备选下架(决策④)。
    block_id:题组短文(passage)外键;paper_id:所属试卷;section:原卷大题名。
    """
    q = PlatformQuestion(
        id=uuid.uuid4(), type="real", question_no=question_no, block_id=block_id,
        paper_id=paper_id, section=section,
        question_type=question_type, stem=stem, options=options, answer=answer,
        explanation=explanation, difficulty=difficulty, meta=meta, status=status,
        **_exam_cols_from_meta(meta),
    )
    db.add(q)
    await db.flush()

    res = ImportResult(question_id=q.id)
    for name in (kp_names or []):
        if not name or not name.strip():
            continue
        m = await match_kp(db, raw_name=name, axis_hint="knowledge",
                           stage_hint=stage_hint, source_type="exam")
        if m.node_id is not None:
            await attach_node(db, q.id, m.node_id)
            res.matched_nodes.append(m.node_id)
            await deprecate_fallbacks_for_node(db, node_id=m.node_id)
        elif m.candidate_id is not None:
            res.candidates.append(m.candidate_id)
    return res


# ── .doc → PDF 异步转换(批量上传后台并发;失败/中断可重试)────────────────
_convert_tasks: set = set()
_convert_sem = None


def _get_convert_sem():
    global _convert_sem
    import asyncio
    if _convert_sem is None:
        _convert_sem = asyncio.Semaphore(4)   # 最多 4 个并发转换
    return _convert_sem


async def _load_doc_bytes(db: AsyncSession, paper) -> tuple[str | None, bytes | None]:
    """取该卷的 .doc 原始字节:优先本地 file_id,否则从 COS 原卷下载(并存本地)。返回 (file_id, bytes)。"""
    from app.services import pdf_upload_service as pus
    m = paper.meta or {}
    fid = m.get("file_id")
    if fid:
        try:
            return fid, pus.read_upload_doc(fid)
        except Exception:  # noqa: BLE001
            pass
    if paper.source_file_url:
        import httpx
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(paper.source_file_url)
            resp.raise_for_status()
            fid = pus.save_upload_doc(resp.content)
            return fid, resp.content
    return None, None


async def convert_paper_doc(db: AsyncSession, *, paper_id: uuid.UUID) -> dict:
    """把某卷的 .doc 用 LibreOffice 转成 PDF;成功后 meta.source→pdf、file_id→新 PDF。

    自行提交:先落 convert_status=converting(可见「转换中」)→ 转换 → 落 converted/failed。
    """
    import asyncio
    from app.services import pdf_upload_service as pus
    paper = await db.get(PlatformPaper, paper_id)
    if paper is None:
        return {"convert_status": "failed", "error": "试卷不存在"}
    m = dict(paper.meta or {})
    if m.get("source") != "doc":
        return {"convert_status": m.get("convert_status") or "converted"}   # 非 doc 无需转换

    fid, doc_bytes = await _load_doc_bytes(db, paper)
    if doc_bytes is None:
        paper.meta = {**m, "convert_status": "failed", "convert_error": "无原始 .doc 文件"}
        await db.commit()
        return {"convert_status": "failed"}
    paper.meta = {**m, "file_id": fid, "convert_status": "converting"}
    await db.commit()

    pdf = await asyncio.to_thread(pus.doc_to_pdf, doc_bytes)
    m2 = dict(paper.meta or {})
    if pdf:
        m2.update(source="pdf", file_id=pus.save_upload(pdf), doc_file_id=fid, convert_status="converted")
        m2.pop("convert_error", None)
        # 落库即 PDF:把转好的 PDF 传 COS,原卷(source_file_url/filename)替换为 PDF
        try:
            pdf_url = await pus.upload_bytes_to_cos(pdf, f"papers/{uuid.uuid4().hex}.pdf", "application/pdf")
        except Exception:  # noqa: BLE001
            pdf_url = None
        if pdf_url:
            m2["doc_file_url"] = paper.source_file_url    # 留存原 .doc 直链备查
            paper.source_file_url = pdf_url
        if paper.source_filename and "." in paper.source_filename:
            paper.source_filename = paper.source_filename.rsplit(".", 1)[0] + ".pdf"
    else:
        m2.update(convert_status="failed",
                  convert_error="未装 LibreOffice(soffice)或转换失败,请装 LibreOffice 后重试")
    paper.meta = m2
    await db.commit()
    return {"convert_status": m2["convert_status"]}


def schedule_doc_conversions(paper_ids: list[uuid.UUID]) -> None:
    """后台并发转换一批 .doc 卷(不阻塞上传响应)。"""
    import asyncio

    async def _one(pid: uuid.UUID) -> None:
        from app.core.database import _async_session_factory
        async with _get_convert_sem():
            try:
                async with _async_session_factory() as s:
                    await convert_paper_doc(s, paper_id=pid)
            except Exception as exc:  # noqa: BLE001
                _log.warning("doc convert bg failed (paper=%s): %s", pid, exc)

    for pid in paper_ids:
        t = asyncio.create_task(_one(pid))
        _convert_tasks.add(t)
        t.add_done_callback(_convert_tasks.discard)


async def parse_paper_questions(db: AsyncSession, *, paper_id: uuid.UUID) -> dict:
    """批量上传后「解析原题目」:读该卷本地文件 → 取文字(扫描件 PDF 走 OCR)→ 拆题 →
    自动入库为**草稿题**(挂 paper_id + 卷面 meta)。标注 paper.parse_status。返回 {imported, status}。
    """
    from app.services import pdf_upload_service as pus

    paper = (await db.execute(sa.select(PlatformPaper).where(PlatformPaper.id == paper_id))).scalar_one_or_none()
    if paper is None:
        raise AppError(code=404, message="试卷不存在")
    m = paper.meta or {}
    file_id, source = m.get("file_id"), m.get("source")
    # 修正历史脏数据:原始文件是 .doc 却被旧逻辑标成 docx/pdf → 作废,按 .doc 重新下载路由
    if (paper.source_filename or "").lower().endswith(".doc") and source != "doc":
        file_id, source = None, None
    if not file_id or source not in ("pdf", "docx", "doc"):
        # 回退:旧占位卷无本地文件 → 从 COS 原卷直链下载后解析
        url = paper.source_file_url
        fn = (paper.source_filename or "")
        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
        if not url or ext not in ("pdf", "doc", "docx"):
            raise AppError(code=400, message="该试卷无可解析的原始文件(仅批量上传的 pdf/word 支持)")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.content
        except Exception as exc:  # noqa: BLE001
            raise AppError(code=502, message=f"下载原卷失败:{exc}")
        if ext == "docx":
            file_id, source = pus.save_upload_docx(data), "docx"
        elif ext == "doc":
            file_id, source = pus.save_upload_doc(data), "doc"
        else:
            file_id, source = pus.save_upload(data), "pdf"
        paper.meta = {**m, "file_id": file_id, "source": source}   # 回填,下次直接用本地

    paper.parse_status = "parsing"
    await db.flush()

    try:
        # 旧版 .doc:先用 LibreOffice 转 PDF,再走 PDF 解析(文字层 / 扫描件 OCR)
        if source == "doc":
            import asyncio
            pdf = await asyncio.to_thread(pus.doc_to_pdf, pus.read_upload_doc(file_id))
            if pdf is None:
                raise RuntimeError("旧版 .doc 无法解析:服务器未装 LibreOffice(soffice),"
                                   "请把文件另存为 .docx 或 PDF 后重新上传")
            file_id, source = pus.save_upload(pdf), "pdf"
            paper.meta = {**(paper.meta or {}), "file_id": file_id, "source": source}
            await db.flush()
        # 与单份「开始抽题」同一套抽题逻辑;扫描件 PDF 自动走视觉 OCR。**不做 KP 匹配。**
        from app.services.real_extract_service import extract_questions
        parsed = await extract_questions(source, file_id, None, scanned_ocr=True)
        if not parsed:
            raise RuntimeError("未拆出题目")

        await clear_paper_questions(db, paper_id)   # 幂等:重新解析先清旧题,避免重复

        # 题组短文:同 block_key 先建一份 passage
        block_pid: dict[str, uuid.UUID] = {}
        for r in parsed:
            bk, pg = r.get("block_key"), r.get("passage")
            if bk and bk not in block_pid and (pg or "").strip():
                try:
                    async with db.begin_nested():
                        block_pid[bk] = await create_passage(db, text=pg.strip())
                except Exception:  # noqa: BLE001
                    pass
        imported = 0
        for r in parsed:
            bk = r.get("block_key")
            try:
                async with db.begin_nested():
                    await import_real_question(              # kp_names 不传 → 暂不出语法知识点
                        db, stem=r["stem"], answer=r.get("answer"),
                        question_type=r.get("question_type"), explanation=r.get("explanation"),
                        meta=m, question_no=r.get("question_no"),
                        status="draft", block_id=block_pid.get(bk) if bk else None,
                        paper_id=paper.id, section=r.get("section"))
                imported += 1
            except Exception:  # noqa: BLE001
                pass
        paper.parse_status = "parsed"
        paper.meta = {k: v for k, v in (paper.meta or {}).items() if k != "parse_error"}  # 清除旧错误
        await db.flush()
        return {"imported": imported, "status": "parsed"}
    except Exception as exc:  # noqa: BLE001
        paper.parse_status = "failed"
        paper.meta = {**(paper.meta or {}), "parse_error": str(exc)[:300]}   # 存失败原因,供列表行内显示
        await db.flush()
        return {"imported": 0, "status": "failed", "error": str(exc)}


async def add_sim(
    db: AsyncSession, *,
    stem: str, parent_real_id: uuid.UUID | None = None, is_fallback: bool = False,
    answer: str | None = None, options: dict | list | None = None,
    question_type: str | None = None, explanation: str | None = None,
    difficulty: int | None = None, status: str = "draft",
) -> PlatformQuestion:
    """低层仿真写入,落地铁律:必须 parent_real_id 或 is_fallback,否则拒绝(应用层先于 DB CHECK)。"""
    if parent_real_id is None and not is_fallback:
        raise AppError(code=400, message="仿真题必须有源:派生真题(parent_real_id)或显式备选(is_fallback)")
    q = PlatformQuestion(
        id=uuid.uuid4(), type="sim", parent_real_id=parent_real_id, is_fallback=is_fallback,
        question_type=question_type, stem=stem, options=options, answer=answer,
        explanation=explanation, difficulty=difficulty, status=status,
    )
    db.add(q)
    await db.flush()
    return q


async def list_platform_questions(
    db: AsyncSession, *, type: str | None = None, status: str | None = None,
    node_id: uuid.UUID | None = None, source_paper_id: uuid.UUID | None = None,
    skip: int = 0, limit: int = 20,
) -> tuple[list[PlatformQuestion], int]:
    """平台题分页查询(运营审核/查看)。可按 type/status/node/来源卷 过滤。

    source_paper_id:仿真题按"母题所属真题卷"过滤(经 parent_real_id→母题→paper),
    并按题型(question_type)+版本排序——供「仿真题审核」按卷展示整卷。
    """
    from sqlalchemy.orm import aliased
    base = sa.select(PlatformQuestion)
    if node_id is not None:
        base = base.join(PlatformQuestionKp,
                         PlatformQuestionKp.question_id == PlatformQuestion.id
                         ).where(PlatformQuestionKp.node_id == node_id)
    if source_paper_id is not None:
        _real = aliased(PlatformQuestion)
        base = base.join(_real, _real.id == PlatformQuestion.parent_real_id
                         ).where(_real.paper_id == source_paper_id)
    if type is not None:
        base = base.where(PlatformQuestion.type == type)
    if status is not None:
        base = base.where(PlatformQuestion.status == status)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    order = ([PlatformQuestion.question_type, PlatformQuestion.sim_version, PlatformQuestion.created_at]
             if source_paper_id is not None else [PlatformQuestion.created_at])
    rows = (await db.execute(
        base.order_by(*order).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def list_sim_papers(db: AsyncSession, *, status: str | None = None) -> list[dict]:
    """仿真题按来源真题卷聚合:返回有仿真的试卷 + 仿真数(供「仿真题审核」按卷列)。"""
    from sqlalchemy.orm import aliased
    _real = aliased(PlatformQuestion)
    q = (sa.select(PlatformPaper.id, PlatformPaper.name, sa.func.count(PlatformQuestion.id))
         .select_from(PlatformQuestion)
         .join(_real, _real.id == PlatformQuestion.parent_real_id)
         .join(PlatformPaper, PlatformPaper.id == _real.paper_id)
         .where(PlatformQuestion.type == "sim"))
    if status is not None:
        q = q.where(PlatformQuestion.status == status)
    q = q.group_by(PlatformPaper.id, PlatformPaper.name).order_by(PlatformPaper.name)
    return [{"paper_id": str(r[0]), "paper_name": r[1], "sim_count": int(r[2])}
            for r in (await db.execute(q)).all()]


async def review_platform_question(
    db: AsyncSession, *, question_id: uuid.UUID, approve: bool
) -> PlatformQuestion:
    """审核平台题:approve→published,reject→retired。"""
    q = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="平台题不存在")
    q.status = "published" if approve else "retired"
    await db.flush()
    return q


async def review_platform_questions_bulk(
    db: AsyncSession, *, question_ids: list[uuid.UUID], approve: bool
) -> int:
    """批量审核仿真题:approve→published / reject→retired。返回更新条数。"""
    if not question_ids:
        return 0
    new_status = "published" if approve else "retired"
    r = await db.execute(
        sa.update(PlatformQuestion)
        .where(PlatformQuestion.id.in_(question_ids), PlatformQuestion.type == "sim")
        .values(status=new_status))
    await db.flush()
    return r.rowcount


def _fine_type(q: PlatformQuestion) -> str:
    """母题真实题型:question_type 偏粗(句子翻译/短文填空/听力 常被存成"单选"),
    按 section 细分,让仿真如实继承母题题型、不混成单选。"""
    sec = q.section or ""
    if "听力" in sec:
        return "听力"
    if "短文填空" in sec:
        return "短文填空"
    if "单词检测" in sec or "词汇检测" in sec:
        return "单词检测"
    if "句子翻译" in sec or "翻译" in sec:
        return "句子翻译"
    if "完形" in sec or "完型" in sec:
        return "完型"
    return q.question_type or "单选"


async def _kp_names(db: AsyncSession, node_ids: list[uuid.UUID]) -> list[str]:
    if not node_ids:
        return []
    return list((await db.execute(
        sa.select(KnowledgeNode.name).where(KnowledgeNode.id.in_(node_ids)))).scalars().all())


async def _next_sim_version(db: AsyncSession, parent_real_ids: list[uuid.UUID]) -> int:
    """该"题位"(母题/短文组的全部母题)已有仿真的最高版本 + 1(按题位累加版本)。"""
    if not parent_real_ids:
        return 1
    mx = (await db.execute(
        sa.select(sa.func.max(PlatformQuestion.sim_version))
        .where(PlatformQuestion.parent_real_id.in_(parent_real_ids)))).scalar()
    return int(mx or 0) + 1


async def _rewrite_variants(real: PlatformQuestion, count: int, kp_names: list[str]) -> list[dict]:
    """单题真题 → count 道仿真变式。考点作为约束传入,**不跑偏母题考点**。dev mock 确定性。"""
    if is_llm_dev_mode():
        return [{
            "stem": f"{real.stem}(变式{i + 1})",
            "options": real.options, "answer": real.answer,
            "explanation": real.explanation,
        } for i in range(count)]
    kp_line = ("本题考点:" + "、".join(kp_names) + "(必须保持,不得更换考点)。\n") if kp_names else ""
    system = (
        "你是英语命题专家。基于给定母题改写出**同考点、同题型、同难度**的新题,"
        "保持考查点不变、情境/数据不同。严格输出 JSON。"
    )
    user = (
        f"{kp_line}母题题干:{real.stem}\n题型:{real.question_type}\n选项:{json.dumps(real.options, ensure_ascii=False)}\n"
        f"答案:{real.answer}\n\n生成 {count} 道仿真题,返回 "
        '{"items":[{"stem":..,"options":..,"answer":..,"explanation":..}, ...]}'
    )
    try:
        resp = await chat_completion(system_prompt=system, user_prompt=user,
                                     max_tokens=2048, response_format={"type": "json_object"})
        items = json.loads(resp.choices[0].message.content or "{}").get("items", [])
        return items[:count]
    except Exception as exc:  # noqa: BLE001
        _log.warning("sim rewrite LLM failed (real=%s): %s", real.id, exc)
        return []


async def generate_sim_from_real(
    db: AsyncSession, *, real_id: uuid.UUID, count: int = 3, status: str = "draft"
) -> list[uuid.UUID]:
    """单题真题派生 count 道仿真(parent_real_id=real_id),继承母题 KP,版本按题位累加。

    短文题组(有 block_id)请走 generate_sim_for_block(整组改写,共享新短文)。
    """
    real = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == real_id)
    )).scalar_one_or_none()
    if real is None or real.type != "real":
        raise AppError(code=404, message="母题真题不存在")
    parent_nodes = await _node_ids_of(db, real_id)
    base = await _next_sim_version(db, [real_id])

    out: list[uuid.UUID] = []
    for i, v in enumerate(await _rewrite_variants(real, count, await _kp_names(db, parent_nodes))):
        if not v.get("stem"):
            continue
        sim = await add_sim(
            db, stem=v["stem"], parent_real_id=real_id, is_fallback=False,
            answer=v.get("answer"), options=v.get("options"),
            question_type=_fine_type(real), explanation=v.get("explanation"),
            difficulty=real.difficulty, status=status,
        )
        sim.sim_version = base + i                                  # 题位累加版本 v1/v2…
        for c in (*_EXAM_COLS, "region_code", "meta", "section"):   # 继承母题可筛选字段
            setattr(sim, c, getattr(real, c))
        for nid in parent_nodes:   # 继承母题 KP(不跑偏)
            await attach_node(db, sim.id, nid)
        out.append(sim.id)
    return out


async def _rewrite_block_variant(passage_text: str, qs: list, kpname_map: dict) -> dict | None:
    """短文题组 → 一个新版本:重写短文 + 与原小题一一对应的新小题(保持各题考点)。"""
    if is_llm_dev_mode():
        return {"passage": f"{passage_text}(仿写)",
                "items": [{"stem": f"{q.stem}(变式)", "options": q.options,
                           "answer": q.answer, "explanation": q.explanation} for q in qs]}
    qlines = []
    for i, q in enumerate(qs):
        kps = "、".join(kpname_map.get(q.id) or []) or "无"
        qlines.append(f"{i+1}. [题型 {q.question_type}|考点 {kps}] {q.stem}"
                      f" 选项:{json.dumps(q.options, ensure_ascii=False)} 答案:{q.answer}")
    system = (
        "你是英语命题专家。基于给定阅读/完形短文及其小题,改写出**一篇新短文 + 配套小题**:\n"
        "1) 新短文话题/情节不同,但体裁、长度、难度相当;\n"
        "2) 每道小题与原题**一一对应**(数量、顺序一致),保持**原考点、原题型不变**,只随新短文改写;\n"
        "3) 不得增删题、不得更换考点。严格输出 JSON。"
    )
    user = (
        f"原短文:\n{passage_text[:4000]}\n\n原小题(共 {len(qs)} 道,按序):\n" + "\n".join(qlines) +
        f'\n\n返回 JSON:{{"passage":"新短文全文","items":[{{"stem":..,"options":..,"answer":..,"explanation":..}}, ...]}};'
        f'items 必须正好 {len(qs)} 条、与原小题顺序一一对应。'
    )
    try:
        resp = await chat_completion(system_prompt=system, user_prompt=user,
                                     max_tokens=4096, response_format={"type": "json_object"})
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        _log.warning("block sim rewrite failed (block=%s): %s", getattr(qs[0], "block_id", "?"), exc)
        return None


async def generate_sim_for_block(
    db: AsyncSession, *, block_id: uuid.UUID, count: int = 3, status: str = "draft"
) -> list[uuid.UUID]:
    """短文题组整组派生:每个版本重写短文(新 Passage)+ 该组全部小题,各题继承母题考点。

    版本按"题组题位"累加(组内所有小题共享同一版本号)。
    """
    qs = list((await db.execute(
        sa.select(PlatformQuestion)
        .where(PlatformQuestion.block_id == block_id, PlatformQuestion.type == "real")
        .order_by(PlatformQuestion.question_no))).scalars().all())
    if not qs:
        return []
    passage_text = (await db.execute(
        sa.select(Passage.text).where(Passage.id == block_id))).scalar() or ""
    kp_map = {q.id: await _node_ids_of(db, q.id) for q in qs}
    kpname_map = {q.id: await _kp_names(db, kp_map[q.id]) for q in qs}
    base = await _next_sim_version(db, [q.id for q in qs])

    out: list[uuid.UUID] = []
    made = 0
    attempts = 0
    max_attempts = count * 2 + 2          # 每个版本可重试(短文组重写偶发小题数对不上)
    while made < count and attempts < max_attempts:
        attempts += 1
        variant = await _rewrite_block_variant(passage_text, qs, kpname_map)
        items = (variant or {}).get("items") or []
        if len(items) < len(qs):          # 数量对不上 → 重试该版本(不计版本、不错位)
            continue
        new_passage_id = await create_passage(
            db, text=(variant.get("passage") or passage_text), kind="reading_text")
        ver = base + made
        made += 1
        for qi, it in zip(qs, items):
            if not it.get("stem"):
                continue
            sim = await add_sim(
                db, stem=it["stem"], parent_real_id=qi.id, is_fallback=False,
                answer=it.get("answer"), options=it.get("options"),
                question_type=_fine_type(qi), explanation=it.get("explanation"),
                difficulty=qi.difficulty, status=status)
            sim.block_id = new_passage_id          # 同版本小题共享新短文
            sim.sim_version = ver
            for c in (*_EXAM_COLS, "region_code", "meta", "section"):
                setattr(sim, c, getattr(qi, c))
            for nid in kp_map[qi.id]:              # 继承各自母题考点(不跑偏)
                await attach_node(db, sim.id, nid)
            out.append(sim.id)
    return out


async def generate_sim_bulk(
    db: AsyncSession, *, question_ids: list[uuid.UUID], count: int = 3, status: str = "draft"
) -> int:
    """题组感知的批量派生:选中的题里凡属短文题组(block_id)→ 整组改写;单题 → 逐题改写。

    选中题组里任一题即重写**整组**。每个题组/单题失败互不影响(嵌套事务隔离)。
    """
    qs = list((await db.execute(
        sa.select(PlatformQuestion)
        .where(PlatformQuestion.id.in_(question_ids), PlatformQuestion.type == "real"))).scalars().all())
    blocks: list[uuid.UUID] = []
    standalone: list[uuid.UUID] = []
    seen: set = set()
    for q in qs:
        if q.block_id:
            if q.block_id not in seen:
                seen.add(q.block_id); blocks.append(q.block_id)
        else:
            standalone.append(q.id)
    total = 0
    for bid in blocks:
        try:
            async with db.begin_nested():
                total += len(await generate_sim_for_block(db, block_id=bid, count=count, status=status))
        except Exception as exc:  # noqa: BLE001
            _log.warning("gen_sim block %s failed: %s", bid, exc)
    for qid in standalone:
        try:
            async with db.begin_nested():
                total += len(await generate_sim_from_real(db, real_id=qid, count=count, status=status))
        except Exception as exc:  # noqa: BLE001
            _log.warning("gen_sim real %s failed: %s", qid, exc)
    return total


async def has_real_for_node(db: AsyncSession, node_id: uuid.UUID) -> bool:
    """该 node 是否已有真题母题(决定能否启用真题派生 / 是否该下架备选)。"""
    row = (await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id, PlatformQuestion.type == "real")
        .limit(1)
    )).first()
    return row is not None


async def generate_fallback_sim(
    db: AsyncSession, *, node_id: uuid.UUID, count: int = 3, status: str = "draft"
) -> list[uuid.UUID]:
    """KP 直生备选(决策④):某 node 暂无真题母题 → 生成 is_fallback=true 备选,挂该 node。

    若该 node 已有真题 → 不生成备选(应走真题派生),返回空。
    """
    if await has_real_for_node(db, node_id):
        return []
    node_name = (await db.execute(
        sa.select(KnowledgeNode.name).where(KnowledgeNode.id == node_id)
    )).scalar_one_or_none()
    out: list[uuid.UUID] = []
    for i in range(count):
        sim = await add_sim(
            db, stem=f"[备选] {node_name or 'KP'} 练习题{i + 1}", is_fallback=True,
            question_type="单选", status=status,
        )
        await attach_node(db, sim.id, node_id)
        out.append(sim.id)
    return out


async def deprecate_fallbacks_for_node(db: AsyncSession, *, node_id: uuid.UUID) -> int:
    """某 node 有真题母题后,把该 node 上的 KP 直生备选(is_fallback,未下架)置 deprecated_at。

    返回下架数量。R2.1 提供;真正有 fallback 数据在 R2.3。
    """
    rows = (await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id,
               PlatformQuestion.type == "sim",
               PlatformQuestion.is_fallback.is_(True),
               PlatformQuestion.deprecated_at.is_(None))
    )).scalars().all()
    if not rows:
        return 0
    await db.execute(
        sa.update(PlatformQuestion)
        .where(PlatformQuestion.id.in_(rows))
        .values(deprecated_at=sa.func.now(), status="retired")
    )
    return len(rows)
