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


# 分段拆题:整卷单次 LLM 输出会超 max_tokens 被截断 → 按大题切段、过大再按字数切,分段并发拆再合并
_SEG_KEYWORDS = ("听力", "单项选择", "单项填空", "完形填空", "完型填空", "阅读理解", "任务型阅读",
                 "词汇运用", "词语运用", "首字母", "短文填空", "补全对话", "书面表达", "连词成句", "看图")
_MAX_SEG_CHARS = 6000       # 每段输入上限:控制单次 LLM 输出不超 max_tokens
_SEG_CONCURRENCY = 4


def _segment_paper_text(text: str) -> list[str]:
    """按「大题标题行」切段;每段过大(>_MAX_SEG_CHARS)再按行累积切小。无标题则整卷按字数切。"""
    lines = text.split("\n")
    heads = [i for i, ln in enumerate(lines)
             if len(ln.strip()) <= 40 and any(k in ln for k in _SEG_KEYWORDS)]
    if heads:
        bounds = sorted(set([0] + heads + [len(lines)]))
        raw = ["\n".join(lines[a:b]).strip() for a, b in zip(bounds, bounds[1:])]
        raw = [s for s in raw if s]
    else:
        raw = [text]
    out: list[str] = []
    for seg in raw:
        if len(seg) <= _MAX_SEG_CHARS:
            out.append(seg)
            continue
        buf: list[str] = []
        cur = 0
        for ln in seg.split("\n"):
            if cur + len(ln) > _MAX_SEG_CHARS and buf:
                out.append("\n".join(buf))
                buf, cur = [], 0
            buf.append(ln)
            cur += len(ln) + 1
        if buf:
            out.append("\n".join(buf))
    return out or [text]


async def _llm_split_segmented(printed: str):
    """分段并发调 LLM 拆题,按段序合并。段内失败只丢该段(不重试、不连累其余)。"""
    from app.services.paper_split_service import split_paper_questions
    from app.services.ocr_service import OcrResult
    segs = _segment_paper_text(printed)
    sem = asyncio.Semaphore(_SEG_CONCURRENCY)

    async def _one(seg: str):
        async with sem:
            try:
                return await split_paper_questions(OcrResult(printed_text=seg, handwritten_text=""))
            except Exception as exc:  # noqa: BLE001
                _log.warning("segment split failed (%d chars): %s", len(seg), exc)
                return []

    results = await asyncio.gather(*[_one(s) for s in segs])
    merged = []
    for lst in results:
        merged.extend(lst)
    return merged


async def extract_questions(
    source: str, file_id: str | None, image_urls: list[str] | None,
    *, scanned_ocr: bool = False,
) -> list[dict]:
    """抽题核心(单份「开始抽题」与批量「解析原题目」共用):取文字 → 拆题 → parsed dict 列表。

    文字版 docx/PDF 走确定性结构拆题(忠实卷面、不臆造答案),拆不出兜底 **分段并发 LLM**;图片走 OCR+LLM。
    scanned_ocr=True:PDF 无文字层(扫描件)时渲染成图走视觉 OCR(批量解析用);否则报错让改图片上传。
    **失败不重试**(格式/截断类重试也没用),快速失败。**不做任何知识点(KP)匹配。**
    """
    from app.services.paper_split_service import split_paper_text_structural
    ocr = await _build_ocr(source, file_id, image_urls)
    printed = (ocr.printed_text or "").strip()
    if not printed and scanned_ocr and source == "pdf" and file_id:
        from app.services import pdf_upload_service as pus
        printed = (await pus.ocr_pdf_bytes(pus.read_upload_pdf(file_id))).strip()
    if not printed:
        raise RuntimeError("未提取到文本(扫描版 PDF 请改用图片上传走 OCR)")
    rows = []
    if source in ("docx", "pdf"):
        rows = split_paper_text_structural(printed)      # 确定性,秒级
    if not rows:
        rows = await _llm_split_segmented(printed)        # 分段并发 LLM 兜底
    return [{
        "question_no": r.question_no, "question_type": r.question_type,
        "stem": r.stem, "answer": r.correct_answer, "explanation": r.explanation,
        "passage": getattr(r, "passage", None),
        "block_key": getattr(r, "block_key", None),
        "section": getattr(r, "section", None),
    } for r in rows if (r.stem or "").strip()]


async def _run_extract(job_id: uuid.UUID) -> None:
    try:
        async with _async_session_factory() as s:
            job = await s.get(RealExtractJob, job_id)
            if job is None:
                return
            source, file_id, image_urls = job.source, job.file_id, list(job.image_urls or [])

        last_err = ""
        parsed: list[dict] | None = None
        try:
            parsed = await extract_questions(source, file_id, image_urls)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)

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
