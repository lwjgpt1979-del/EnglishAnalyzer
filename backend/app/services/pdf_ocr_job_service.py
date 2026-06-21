"""扫描件 PDF 的 OCR 后台任务(进程内进度跟踪)。

OCR 一整本(上百页)要几分钟 → fire-and-forget 后台跑,前端轮询进度。
完成后写 {file_id}.ocr.json(由 pdf_upload_service.extract_pages 自动启用),
并基于 OCR 文字重新检测单元,放进 job.segments 供前端直接用。
系统未上线、单进程:进度存内存即可。
"""
from __future__ import annotations

import asyncio
import logging

from app.services import pdf_upload_service as pus

_log = logging.getLogger(__name__)

# file_id -> {total, done, status: pending|running|done|error, error, segments}
_jobs: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()


def get_status(file_id: str) -> dict | None:
    return _jobs.get(file_id)


async def _run(file_id: str) -> None:
    job = _jobs[file_id]
    job["status"] = "running"
    try:
        def _progress(done: int, total: int) -> None:
            job["done"] = done
            job["total"] = total
        await pus.ocr_pages_to_sidecar(file_id, on_progress=_progress)
        # OCR 完成 → 用 OCR 文字重新检测单元
        pages = pus.extract_pages(file_id)
        segs = pus.auto_detect_units(pages) or []
        job["segments"] = segs
        job["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        _log.error("PDF OCR job failed (%s): %s", file_id, exc)
        job["status"] = "error"
        job["error"] = str(exc)


def start_ocr(file_id: str) -> dict:
    """启动(或复用)某 PDF 的 OCR 后台任务。已 OCR 过则直接返回 done。"""
    if pus.ocr_text_available(file_id):
        pages = pus.extract_pages(file_id)
        segs = pus.auto_detect_units(pages) or []
        _jobs[file_id] = {"total": len(pages), "done": len(pages), "status": "done",
                          "error": "", "segments": segs}
        return _jobs[file_id]
    cur = _jobs.get(file_id)
    if cur and cur.get("status") in ("pending", "running"):
        return cur
    _jobs[file_id] = {"total": 0, "done": 0, "status": "pending", "error": "", "segments": []}
    t = asyncio.create_task(_run(file_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return _jobs[file_id]
