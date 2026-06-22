"""派生仿真的后台任务(进程内进度跟踪)。

整卷/多题派生要跑大量 LLM 改写(尤其短文组整篇重写,很慢)→ fire-and-forget 后台跑,
前端轮询进度,不再阻塞请求/登录。系统未上线、单进程:进度存内存即可。

按"题位"推进:短文题组算 1 个题位(整组改写)、单题算 1 个题位。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d16_question_domain import PlatformQuestion
from app.services import platform_question_service as pqs

_log = logging.getLogger(__name__)

# job_id -> {total, done, generated, failed, status: pending|running|done|error, error}
_jobs: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()


def get_status(job_id: str) -> dict | None:
    return _jobs.get(job_id)


async def _run(job_id: str, question_ids: list[uuid.UUID], count: int) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    try:
        # 分组:短文题组(block_id)整组 / 单题逐题(同 generate_sim_bulk)
        async with _async_session_factory() as db:
            qs = list((await db.execute(
                sa.select(PlatformQuestion).where(
                    PlatformQuestion.id.in_(question_ids), PlatformQuestion.type == "real")
            )).scalars().all())
        blocks: list = []
        standalone: list = []
        seen: set = set()
        for q in qs:
            if q.block_id:
                if q.block_id not in seen:
                    seen.add(q.block_id); blocks.append(q.block_id)
            else:
                standalone.append(q.id)
        job["total"] = len(blocks) + len(standalone)

        async def _one(coro_factory) -> None:
            try:
                async with _async_session_factory() as db:
                    ids = await coro_factory(db)
                    await db.commit()
                job["generated"] += len(ids)
            except Exception as exc:  # noqa: BLE001
                _log.warning("sim gen job %s slot failed: %s", job_id, exc)
                job["failed"] += 1
            finally:
                job["done"] += 1

        for bid in blocks:
            await _one(lambda db, b=bid: pqs.generate_sim_for_block(db, block_id=b, count=count))
        for qid in standalone:
            await _one(lambda db, q=qid: pqs.generate_sim_from_real(db, real_id=q, count=count))
        job["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        _log.exception("sim gen job %s crashed: %s", job_id, exc)
        job["status"] = "error"
        job["error"] = str(exc)


def start(question_ids: list[uuid.UUID], count: int) -> str:
    """启动后台派生任务,返回 job_id(秒回,前端轮询 get_status)。"""
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"total": 0, "done": 0, "generated": 0, "failed": 0,
                     "status": "pending", "error": ""}
    t = asyncio.create_task(_run(job_id, question_ids, count))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return job_id
