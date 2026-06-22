"""教材内容生成异步任务(方案 A)。

分单元存下 → 后台逐单元生成,**每单元独立 session/commit**(成一个落一个,不全有或全无)+
**失败自动重试**,进度实时写 curriculum_gen_job → 前端轮询。关窗口不影响;后端重启可续跑。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d11_v2_curriculum import CurriculumGenJob

_log = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3          # 1 次 + 2 次重试(根治 LLM 偶发"返回格式异常")
_tasks: set[asyncio.Task] = set()   # 持有引用防 GC


async def create_job(
    db: AsyncSession, *, source: str, file_id: str | None, textbook_version: str,
    grade: str, semester: str, content_status: str, segments: list[dict],
) -> CurriculumGenJob:
    """建任务(running)并存待生成单元。调用方 commit 后再 schedule。"""
    job = CurriculumGenJob(
        id=uuid.uuid4(), source=source, file_id=file_id,
        textbook_version=textbook_version, grade=grade, semester=semester,
        content_status=content_status, status="running",
        total=len(segments), done=0, failed=0, segments=segments, results=[],
    )
    db.add(job)
    await db.flush()
    return job


def schedule(job_id: uuid.UUID) -> None:
    """fire-and-forget 后台执行(独立于请求生命周期)。"""
    t = asyncio.create_task(_run_job(job_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _gen_one(seg: dict, *, file_id: str | None, textbook_version: str,
                   grade: str, semester: str, content_status: str) -> dict:
    """生成单个单元:LLM → persist(独立 commit)→ 对齐(独立 best-effort)。带重试。"""
    from app.services import (
        pdf_upload_service as pus, curriculum_ai_service as ai,
        curriculum_service as cs, curriculum_kp_service as kp,
    )
    uno = seg["unit_no"]
    last_err = ""
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            unit_text = pus.get_unit_text(file_id, seg["start_page"], seg["end_page"]) if file_id else ""
            # 骨架版:只出 考点名 + 词，不生成六维讲解(大幅提速)。
            # 六维讲解延后/按需，由「生成内容」(generate_unit_content) 用已存的 source_text 单独补。
            unit = await ai.generate_unit_from_text(
                textbook_version=textbook_version, grade=grade, semester=semester,
                unit_no=uno, unit_text=unit_text, detected_title=seg.get("detected_title"),
                with_contents=False)
            # 核心落库:独立 session,成功即 commit
            async with _async_session_factory() as s:
                cu = await cs.persist_unit(s, ai_unit=unit, content_status=content_status)
                if unit_text:
                    cu.source_text = unit_text   # 存原文,供单个"生成内容"重生成 + 重新析短文
                await s.flush()
                cu_id = cu.id
                await s.commit()
            # 图谱对齐(派生 vocab_node)best-effort,独立 session,失败不影响本单元
            try:
                async with _async_session_factory() as s2:
                    await kp.extract_for_ai_unit(s2, unit_id=cu_id, ai_unit=unit, source="upload_extract")
                    await s2.commit()
            except Exception as exc2:  # noqa: BLE001
                _log.warning("extract_for_ai_unit failed (unit=%s): %s", uno, exc2)
            # 析出单元短文(听力脚本/阅读短文/写作范文)best-effort 落库
            try:
                passages = await ai.extract_unit_passages(unit_text)
                if passages:
                    async with _async_session_factory() as s3:
                        await cs.persist_unit_passages(s3, unit_id=cu_id, passages=passages)
                        await s3.commit()
            except Exception as exc3:  # noqa: BLE001
                _log.warning("extract_unit_passages failed (unit=%s): %s", uno, exc3)
            # 拆单元独立 PDF → COS,供列表查看原版(文字版/扫描版都按原始页拆)
            if file_id:
                try:
                    from app.models.d4_knowledge import CurriculumUnit
                    pdf_bytes = pus.split_unit_pdf(file_id, seg["start_page"], seg["end_page"])
                    url = await pus.upload_pdf_to_cos(pdf_bytes, f"curriculum/units/{cu_id}.pdf")
                    if url:
                        async with _async_session_factory() as s4:
                            u = await s4.get(CurriculumUnit, cu_id)
                            if u is not None:
                                u.unit_pdf_url = url
                            await s4.commit()
                except Exception as exc4:  # noqa: BLE001
                    _log.warning("split/upload unit pdf failed (unit=%s): %s", uno, exc4)
            return {"unit_no": uno, "unit_title": unit.unit_title,
                    "kp_count": len(unit.knowledge_points),
                    "word_count": len(unit.words), "status": "ok"}
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            _log.warning("gen unit %s attempt failed: %s", uno, exc)
    return {"unit_no": uno, "unit_title": seg.get("detected_title") or f"Unit {uno}",
            "kp_count": 0, "word_count": 0, "status": "error", "error": last_err}


async def _save_result(job_id: uuid.UUID, result: dict) -> None:
    async with _async_session_factory() as s:
        job = await s.get(CurriculumGenJob, job_id)
        if job is None:
            return
        res = [r for r in (job.results or []) if r.get("unit_no") != result["unit_no"]]
        res.append(result)
        res.sort(key=lambda r: r["unit_no"])
        job.results = res
        job.done = sum(1 for r in res if r["status"] == "ok")
        job.failed = sum(1 for r in res if r["status"] == "error")
        await s.commit()


async def _run_job(job_id: uuid.UUID) -> None:
    try:
        async with _async_session_factory() as s:
            job = await s.get(CurriculumGenJob, job_id)
            if job is None:
                return
            segs = list(job.segments or [])
            ctx = dict(file_id=job.file_id, textbook_version=job.textbook_version,
                       grade=job.grade, semester=job.semester, content_status=job.content_status)
            done_unos = {r["unit_no"] for r in (job.results or []) if r.get("status") == "ok"}

        for seg in segs:
            if seg["unit_no"] in done_unos:    # 续跑:已成功单元跳过
                continue
            result = await _gen_one(seg, **ctx)
            await _save_result(job_id, result)

        async with _async_session_factory() as s:
            job = await s.get(CurriculumGenJob, job_id)
            if job is not None:
                job.status = "failed" if (job.done == 0 and job.failed > 0) else "done"
                await s.commit()
    except Exception as exc:  # noqa: BLE001
        _log.exception("gen job %s crashed: %s", job_id, exc)


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> CurriculumGenJob | None:
    return await db.get(CurriculumGenJob, job_id)


async def retry_job(db: AsyncSession, job_id: uuid.UUID) -> bool:
    """重试:重新跑该任务(_run_job 自动跳过已成功单元、只重跑失败的)。

    适用文字版与扫描版(扫描件 OCR sidecar 仍在磁盘,extract_pages 透明复用)。
    """
    job = await db.get(CurriculumGenJob, job_id)
    if job is None:
        return False
    if job.status == "running":
        return True
    job.status = "running"
    await db.commit()
    t = asyncio.create_task(_run_job(job_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return True


async def list_jobs(
    db: AsyncSession, *, status: str | None = None, textbook_version: str | None = None,
    grade: str | None = None, semester: str | None = None, limit: int = 20,
) -> list[CurriculumGenJob]:
    stmt = select(CurriculumGenJob)
    if status:
        stmt = stmt.where(CurriculumGenJob.status == status)
    if textbook_version:
        stmt = stmt.where(CurriculumGenJob.textbook_version == textbook_version)
    if grade:
        stmt = stmt.where(CurriculumGenJob.grade == grade)
    if semester:
        stmt = stmt.where(CurriculumGenJob.semester == semester)
    stmt = stmt.order_by(CurriculumGenJob.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def resume_running_jobs() -> int:
    """启动钩子:重新调度仍处 running 的任务(persist 幂等,跳过已成功单元)。返回续跑数。"""
    try:
        async with _async_session_factory() as s:
            ids = (await s.execute(
                select(CurriculumGenJob.id).where(CurriculumGenJob.status == "running")
            )).scalars().all()
        for jid in ids:
            schedule(jid)
        if ids:
            _log.info("resumed %d running gen job(s)", len(ids))
        return len(ids)
    except Exception as exc:  # noqa: BLE001
        _log.warning("resume_running_jobs failed: %s", exc)
        return 0
