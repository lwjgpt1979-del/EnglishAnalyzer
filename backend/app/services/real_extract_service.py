"""真题抽题异步任务(TK2):上传 PDF/图片 → 后台 OCR/拆题 → parsed 待校对。

复用 ocr_service.run_ocr(图片) / pdf_upload_service.extract_pages(文本PDF) + paper_split_service
拆题;异步秒回 + 轮询(同教材流)。抽出的题供前端校对后再 bulk 导入(TK1)。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d16_question_domain import RealExtractJob

_log = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_tasks: set[asyncio.Task] = set()


async def create_job(
    db: AsyncSession, *, source: str, file_id: str | None = None,
    image_urls: list[str] | None = None,
) -> RealExtractJob:
    job = RealExtractJob(
        id=uuid.uuid4(), source=source, file_id=file_id,
        image_urls=image_urls, status="running", parsed=[],
    )
    db.add(job)
    await db.flush()
    return job


def schedule(job_id: uuid.UUID) -> None:
    t = asyncio.create_task(_run_extract(job_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _build_ocr(source: str, file_id: str | None, image_urls: list[str] | None):
    """组装 OcrResult(印刷体=卷面文本,无手写)。PDF 走 pdfplumber 文本;图片走 run_ocr。"""
    from app.services.ocr_service import OcrResult, run_ocr
    from app.services import pdf_upload_service as pus
    if source == "pdf":
        pages = pus.extract_pages(file_id)
        printed = "\n".join(p for p in pages if p).strip()
        return OcrResult(printed_text=printed, handwritten_text="")
    if source == "docx":
        return OcrResult(printed_text=pus.extract_docx_text(file_id), handwritten_text="")
    # image:逐图 OCR,合并印刷体
    parts: list[str] = []
    for url in (image_urls or []):
        ocr = await run_ocr(url)
        if ocr.printed_text:
            parts.append(ocr.printed_text)
    return OcrResult(printed_text="\n".join(parts).strip(), handwritten_text="")


async def _run_extract(job_id: uuid.UUID) -> None:
    from app.services.paper_split_service import (
        split_paper_questions, split_paper_text_structural,
    )
    try:
        async with _async_session_factory() as s:
            job = await s.get(RealExtractJob, job_id)
            if job is None:
                return
            source, file_id, image_urls = job.source, job.file_id, list(job.image_urls or [])

        last_err = ""
        parsed: list[dict] | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                ocr = await _build_ocr(source, file_id, image_urls)
                if not (ocr.printed_text or "").strip():
                    raise RuntimeError("未提取到文本(扫描版 PDF 请改用图片上传走 OCR)")
                # 文字版 docx/PDF:确定性结构拆题(忠实卷面、不臆造答案);
                # 拆不出(非标准卷式)再兜底走 LLM。图片走 OCR + LLM 拆题。
                rows = []
                if source in ("docx", "pdf"):
                    rows = split_paper_text_structural(ocr.printed_text or "")
                if not rows:
                    rows = await split_paper_questions(ocr)
                parsed = [{
                    "question_no": r.question_no, "question_type": r.question_type,
                    "stem": r.stem, "answer": r.correct_answer, "explanation": r.explanation,
                    "passage": getattr(r, "passage", None),
                    "block_key": getattr(r, "block_key", None),
                    "section": getattr(r, "section", None),
                } for r in rows if (r.stem or "").strip()]
                break
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                _log.warning("real extract attempt failed (job=%s): %s", job_id, exc)

        async with _async_session_factory() as s:
            job = await s.get(RealExtractJob, job_id)
            if job is None:
                return
            if parsed is not None:
                job.parsed = parsed
                job.status = "done"
            else:
                job.error = last_err
                job.status = "failed"
            await s.commit()
    except Exception as exc:  # noqa: BLE001
        _log.exception("real extract job %s crashed: %s", job_id, exc)


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> RealExtractJob | None:
    return await db.get(RealExtractJob, job_id)


async def resume_running_jobs() -> int:
    try:
        async with _async_session_factory() as s:
            ids = (await s.execute(
                select(RealExtractJob.id).where(RealExtractJob.status == "running")
            )).scalars().all()
        for jid in ids:
            schedule(jid)
        return len(ids)
    except Exception as exc:  # noqa: BLE001
        _log.warning("real extract resume failed: %s", exc)
        return 0
