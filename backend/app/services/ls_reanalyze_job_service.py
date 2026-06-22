"""重新解析长难句的后台任务(进程内进度跟踪)。

旧长难句 analysis_json 是简单结构;重新跑 analyze_sentence 刷成新结构(分段/结构/成分/
词汇/语法点),供小程序「长难句学习」UI 用。批量要跑多次 LLM → 后台跑,前端轮询进度。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d20_long_sentence import LongSentence
from app.services import long_sentence_service as lss

_log = logging.getLogger(__name__)

# job_id -> {total, done, failed, status, error, publish}
_jobs: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()


def get_status(job_id: str) -> dict | None:
    return _jobs.get(job_id)


async def _run(job_id: str, only_status: str | None, limit: int, publish: bool) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    try:
        async with _async_session_factory() as db:
            q = sa.select(LongSentence.id).order_by(LongSentence.created_at)
            if only_status:
                q = q.where(LongSentence.status == only_status)
            ids = list((await db.execute(q.limit(limit))).scalars().all())
        job["total"] = len(ids)
        for ls_id in ids:
            try:
                async with _async_session_factory() as db:
                    await lss.reanalyze_one(db, ls_id=ls_id, publish=publish)
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                _log.warning("reanalyze ls %s failed: %s", ls_id, exc)
                job["failed"] += 1
            finally:
                job["done"] += 1
        job["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        _log.exception("ls reanalyze job %s crashed: %s", job_id, exc)
        job["status"] = "error"
        job["error"] = str(exc)


def start(*, only_status: str | None = None, limit: int = 200, publish: bool = False) -> str:
    """启动重新解析后台任务,返回 job_id。only_status 限状态;publish=True 顺带发布。"""
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"total": 0, "done": 0, "failed": 0, "status": "pending", "error": "", "publish": publish}
    t = asyncio.create_task(_run(job_id, only_status, limit, publish))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return job_id
