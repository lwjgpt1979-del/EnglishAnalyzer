"""按省/市/年份批量:解析 + 一键采纳 → 写入 option_vocab_ready(进选项词统计)。

进程内 job 加速轮询 + DB 落库可查历史;断点续跑靠扫描 pending(ready 跳过)。
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import _async_session_factory
from app.models.d16_question_domain import (
    OptionVocabPipelineJob,
    PlatformPaper,
    PlatformQuestion,
)
from app.services import question_analysis_service as qas
from app.services.question_analysis_service import (
    _section_is_word_fill,
    stem_looks_word_fill,
)

_log = logging.getLogger(__name__)

# 与原型勾选项一致
PIPELINE_TYPE_KEYS = (
    "grammar_mc",   # 单项选择
    "cloze",        # 完形填空
    "passage_fill", # 短文填空
    "vocab_use",    # 词汇运用
    "verb_fill",    # 动词填空
)
PIPELINE_TYPE_LABELS = {
    "grammar_mc": "单项选择",
    "cloze": "完形填空",
    "passage_fill": "短文填空",
    "vocab_use": "词汇运用",
    "verb_fill": "动词填空",
}

_jobs: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()

_SUGGEST_CHUNK = 30
_PERSIST_EVERY = 5  # 每累计 N 次进度变更刷一次库


def pipeline_type_of(q: PlatformQuestion) -> str | None:
    """判定题是否属于管道题型;不属于则 None。"""
    qt = q.question_type or ""
    sec = q.section or ""
    if qt == "完型" or "完形" in sec or "完型" in sec:
        return "cloze"
    if qt == "填空" and re.search(r"短文|缺词", sec):
        return "passage_fill"
    # 词形填空类
    is_wf = False
    if stem_looks_word_fill(q.stem or ""):
        is_wf = True
    elif qt == "填空" and not re.search(r"短文|完成句子|翻译|句型转换|缺词|完形|完型", sec):
        is_wf = _section_is_word_fill(sec)
    if is_wf:
        if "动词" in sec:
            return "verb_fill"
        return "vocab_use"
    if (
        qt == "单选"
        and "阅读" not in sec
        and "听力" not in sec
        and not stem_looks_word_fill(q.stem or "")
        and not _section_is_word_fill(sec)
    ):
        return "grammar_mc"
    return None


def _is_ready(q: PlatformQuestion) -> bool:
    meta = q.meta if isinstance(q.meta, dict) else {}
    ana = meta.get("analysis")
    return isinstance(ana, dict) and ana.get("option_vocab_ready") is True


def _strip_confirm_fields(ana: dict) -> dict:
    skip = {"confirmed_at", "confirmed_by", "option_vocab_ready", "logic_display", "validation_skipped"}
    return {k: v for k, v in ana.items() if k not in skip}


def _job_public(job_id: str, job: dict) -> dict:
    return {
        "job_id": job_id,
        "status": job.get("status") or "pending",
        "total": int(job.get("total") or 0),
        "done": int(job.get("done") or 0),
        "failed": int(job.get("failed") or 0),
        "adopted": int(job.get("adopted") or 0),
        "suggested": int(job.get("suggested") or 0),
        "error": job.get("error") or "",
        "logs": list(job.get("logs") or []),
        "concurrency": job.get("concurrency"),
        "auto_adopt": job.get("auto_adopt"),
        "force_suggest": job.get("force_suggest"),
        "region_code": job.get("region_code"),
        "region_name": job.get("region_name"),
        "year": job.get("year"),
        "types": list(job.get("types") or []),
        "paper_ids": list(job.get("paper_ids") or []),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "finished_at": job.get("finished_at"),
    }


def _row_to_public(row: OptionVocabPipelineJob) -> dict:
    return {
        "job_id": row.id,
        "status": row.status or "pending",
        "total": int(row.total or 0),
        "done": int(row.done or 0),
        "failed": int(row.failed or 0),
        "adopted": int(row.adopted or 0),
        "suggested": int(row.suggested or 0),
        "error": row.error or "",
        "logs": list(row.logs or []) if isinstance(row.logs, list) else [],
        "concurrency": row.concurrency,
        "auto_adopt": row.auto_adopt,
        "force_suggest": row.force_suggest,
        "region_code": row.region_code,
        "region_name": row.region_name,
        "year": row.year,
        "types": list(row.types or []) if isinstance(row.types, list) else [],
        "paper_ids": list(row.paper_ids or []) if isinstance(row.paper_ids, list) else [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _append_log(job: dict, line: str) -> None:
    logs = job.setdefault("logs", [])
    logs.append(line)
    if len(logs) > 400:
        del logs[: len(logs) - 400]
    job["_dirty"] = True


async def _persist_job(job_id: str, job: dict, *, force: bool = False) -> None:
    """把内存 job 刷到 DB;force 或 dirty 时写。"""
    if not force and not job.get("_dirty"):
        return
    now = datetime.now(timezone.utc)
    job["updated_at"] = now.isoformat()
    finished = None
    if job.get("status") in ("done", "error"):
        finished = job.get("finished_at") or now.isoformat()
        job["finished_at"] = finished
    try:
        async with _async_session_factory() as db:
            row = await db.get(OptionVocabPipelineJob, job_id)
            if row is None:
                row = OptionVocabPipelineJob(id=job_id)
                db.add(row)
            row.status = job.get("status") or "pending"
            row.region_code = job.get("region_code")
            row.region_name = job.get("region_name")
            row.year = job.get("year")
            row.types = list(job.get("types") or [])
            row.paper_ids = list(job.get("paper_ids") or [])
            row.total = int(job.get("total") or 0)
            row.done = int(job.get("done") or 0)
            row.failed = int(job.get("failed") or 0)
            row.adopted = int(job.get("adopted") or 0)
            row.suggested = int(job.get("suggested") or 0)
            row.concurrency = int(job.get("concurrency") or 6)
            row.auto_adopt = bool(job.get("auto_adopt", True))
            row.force_suggest = bool(job.get("force_suggest", False))
            row.error = job.get("error") or None
            row.logs = list(job.get("logs") or [])
            flag_modified(row, "logs")
            flag_modified(row, "types")
            flag_modified(row, "paper_ids")
            if job.get("admin_id"):
                try:
                    row.admin_id = uuid.UUID(str(job["admin_id"]))
                except ValueError:
                    pass
            row.updated_at = now
            if finished:
                try:
                    row.finished_at = datetime.fromisoformat(finished.replace("Z", "+00:00"))
                except ValueError:
                    row.finished_at = now
            await db.commit()
        job["_dirty"] = False
        job["_persist_n"] = 0
    except Exception:  # noqa: BLE001
        _log.exception("persist pipeline job %s failed", job_id)


def _mark_progress(job: dict) -> None:
    job["_dirty"] = True
    job["_persist_n"] = int(job.get("_persist_n") or 0) + 1


async def _maybe_persist(job_id: str, job: dict, *, force: bool = False) -> None:
    if force or int(job.get("_persist_n") or 0) >= _PERSIST_EVERY:
        await _persist_job(job_id, job, force=True)


async def scan(
    db: AsyncSession,
    *,
    region_code: str,
    year: int | None,
    types: list[str],
) -> dict:
    """扫描范围内卷与待入统计题量。"""
    type_set = {t for t in types if t in PIPELINE_TYPE_KEYS}
    if not type_set:
        type_set = set(PIPELINE_TYPE_KEYS)
    if not (region_code or "").strip():
        return {
            "region_code": region_code, "year": year, "types": sorted(type_set),
            "paper_count": 0, "pending_total": 0, "ready_total": 0, "papers": [],
        }

    conds = [
        PlatformPaper.region_code.isnot(None),
        PlatformPaper.region_code.like(f"{region_code.strip()}%"),
    ]
    if year is not None:
        conds.append(PlatformPaper.year == int(year))

    papers = list((await db.execute(
        sa.select(PlatformPaper).where(*conds).order_by(
            PlatformPaper.year.desc().nullslast(), PlatformPaper.created_at.desc())
    )).scalars().all())

    out_papers: list[dict] = []
    pending_total = 0
    ready_total = 0
    for p in papers:
        qs = list((await db.execute(
            sa.select(PlatformQuestion).where(
                PlatformQuestion.paper_id == p.id,
                PlatformQuestion.type == "real",
            )
        )).scalars().all())
        by_type_pending: dict[str, int] = {}
        by_type_ready: dict[str, int] = {}
        pending_n = 0
        ready_n = 0
        pending_ids: list[str] = []
        for q in qs:
            pt = pipeline_type_of(q)
            if pt is None or pt not in type_set:
                continue
            if _is_ready(q):
                ready_n += 1
                by_type_ready[pt] = by_type_ready.get(pt, 0) + 1
            else:
                pending_n += 1
                by_type_pending[pt] = by_type_pending.get(pt, 0) + 1
                pending_ids.append(str(q.id))
        pending_total += pending_n
        ready_total += ready_n
        out_papers.append({
            "paper_id": str(p.id),
            "name": p.name,
            "year": p.year,
            "region_code": p.region_code,
            "region_name": p.region_name,
            "exam_type": p.exam_type,
            "status": p.status,
            "pending_count": pending_n,
            "ready_count": ready_n,
            "pending_by_type": {PIPELINE_TYPE_LABELS.get(k, k): v for k, v in by_type_pending.items() if v},
            "ready_by_type": {PIPELINE_TYPE_LABELS.get(k, k): v for k, v in by_type_ready.items() if v},
            "pending_question_ids": pending_ids,
        })

    return {
        "region_code": region_code,
        "year": year,
        "types": sorted(type_set),
        "paper_count": len(out_papers),
        "pending_total": pending_total,
        "ready_total": ready_total,
        "papers": out_papers,
    }


async def get_job(job_id: str) -> dict | None:
    """优先内存;否则读库。库里 running 但不在内存 → 标进程中断。"""
    mem = _jobs.get(job_id)
    if mem is not None:
        return _job_public(job_id, mem)

    async with _async_session_factory() as db:
        row = await db.get(OptionVocabPipelineJob, job_id)
        if row is None:
            return None
        if row.status in ("pending", "running"):
            row.status = "error"
            row.error = (row.error or "") or "进程中断(服务重启后任务未继续)"
            row.finished_at = datetime.now(timezone.utc)
            _append_line = list(row.logs or []) if isinstance(row.logs, list) else []
            _append_line.append("任务异常: 进程中断 — 请同范围扫描后继续跑批")
            row.logs = _append_line[-400:]
            flag_modified(row, "logs")
            await db.commit()
            await db.refresh(row)
        return _row_to_public(row)


async def list_jobs(*, limit: int = 20) -> list[dict]:
    """最近跑批;进行中若在本进程则合并实时进度。"""
    lim = max(1, min(50, int(limit or 20)))
    async with _async_session_factory() as db:
        rows = list((await db.execute(
            sa.select(OptionVocabPipelineJob)
            .order_by(OptionVocabPipelineJob.created_at.desc())
            .limit(lim)
        )).scalars().all())
        out: list[dict] = []
        dirty = False
        for row in rows:
            mem = _jobs.get(row.id)
            if mem is not None:
                out.append(_job_public(row.id, mem))
                continue
            if row.status in ("pending", "running"):
                row.status = "error"
                row.error = (row.error or "") or "进程中断(服务重启后任务未继续)"
                row.finished_at = datetime.now(timezone.utc)
                logs = list(row.logs or []) if isinstance(row.logs, list) else []
                logs.append("任务异常: 进程中断 — 请同范围扫描后继续跑批")
                row.logs = logs[-400:]
                flag_modified(row, "logs")
                dirty = True
            out.append(_row_to_public(row))
        if dirty:
            await db.commit()
        return out


async def _run_job(
    job_id: str,
    *,
    paper_ids: list[uuid.UUID],
    types: list[str],
    concurrency: int,
    auto_adopt: bool,
    force_suggest: bool,
    admin_id: uuid.UUID,
) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    job["_dirty"] = True
    await _persist_job(job_id, job, force=True)
    type_set = {t for t in types if t in PIPELINE_TYPE_KEYS} or set(PIPELINE_TYPE_KEYS)
    conc = max(2, min(12, int(concurrency or 6)))
    try:
        async with _async_session_factory() as db:
            qs = list((await db.execute(
                sa.select(PlatformQuestion).where(
                    PlatformQuestion.paper_id.in_(paper_ids),
                    PlatformQuestion.type == "real",
                )
            )).scalars().all())

        pending: list[PlatformQuestion] = []
        for q in qs:
            pt = pipeline_type_of(q)
            if pt is None or pt not in type_set:
                continue
            if _is_ready(q):
                continue
            pending.append(q)

        job["total"] = len(pending)
        job["concurrency"] = conc
        _append_log(job, f"待处理 {len(pending)} 题 · 并发≈{conc} · 自动采纳={auto_adopt}")
        await _persist_job(job_id, job, force=True)

        reconfirm: list[PlatformQuestion] = []
        need_suggest: list[PlatformQuestion] = []
        for q in pending:
            meta = q.meta if isinstance(q.meta, dict) else {}
            ana = meta.get("analysis")
            if isinstance(ana, dict) and ana.get("confirmed_at") and not force_suggest:
                reconfirm.append(q)
            else:
                need_suggest.append(q)

        # 1) 已确认但未 ready:再走一次 confirm 写全字段(无 LLM)
        for q in reconfirm:
            try:
                async with _async_session_factory() as db:
                    q2 = await db.get(PlatformQuestion, q.id)
                    if q2 is None:
                        job["failed"] += 1
                        continue
                    ana = ((q2.meta or {}).get("analysis") or {})
                    if not isinstance(ana, dict):
                        job["failed"] += 1
                        continue
                    if auto_adopt:
                        await qas.confirm_analysis(
                            db, question_id=q2.id,
                            analysis=_strip_confirm_fields(ana), admin_id=admin_id)
                        await db.commit()
                        job["adopted"] += 1
                        _append_log(job, f"再采纳 {q2.question_no or q2.id} → ready 回写")
                    else:
                        job["suggested"] += 1
            except Exception as exc:  # noqa: BLE001
                job["failed"] += 1
                _append_log(job, f"再采纳失败 {q.id}: {exc}")
            finally:
                job["done"] += 1
                _mark_progress(job)
                await _maybe_persist(job_id, job)

        # 2) 需 LLM:按块 suggest,通过项 confirm
        chunk_size = min(_SUGGEST_CHUNK, max(conc, 6))
        for i in range(0, len(need_suggest), chunk_size):
            chunk = need_suggest[i: i + chunk_size]
            ids = [q.id for q in chunk]
            try:
                async with _async_session_factory() as db:
                    force = force_suggest
                    if not force:
                        for qid in ids:
                            qrow = await db.get(PlatformQuestion, qid)
                            if qrow is None:
                                continue
                            draft = ((qrow.meta or {}).get("analysis_draft") or {})
                            if isinstance(draft, dict) and (draft.get("errors") or []):
                                force = True
                                break
                    old_conc = qas._LLM_CONCURRENCY
                    qas._LLM_CONCURRENCY = conc
                    try:
                        items = await qas.suggest_analysis(db, question_ids=ids, force=force)
                    finally:
                        qas._LLM_CONCURRENCY = old_conc
                    await db.commit()

                    adopt_items: list[dict] = []
                    for it in items:
                        qid = it.get("question_id")
                        ana = it.get("analysis")
                        errs = it.get("errors") or []
                        if ana and not errs:
                            job["suggested"] += 1
                            if auto_adopt:
                                adopt_items.append({
                                    "question_id": qid,
                                    "analysis": _strip_confirm_fields(dict(ana)),
                                })
                        else:
                            job["failed"] += 1
                            _append_log(
                                job,
                                f"解析未过 {qid}: {(errs or ['无分析'])[0][:80]}",
                            )

                    if auto_adopt and adopt_items:
                        for j in range(0, len(adopt_items), 40):
                            sub = adopt_items[j: j + 40]
                            res = await qas.confirm_analysis_batch(
                                db, items=sub, admin_id=admin_id)
                            await db.commit()
                            job["adopted"] += len(res.get("confirmed") or [])
                            for f in res.get("failed") or []:
                                job["failed"] += 1
                                _append_log(
                                    job,
                                    f"采纳失败 {f.get('question_id')}: {f.get('error', '')[:80]}",
                                )
                            _append_log(
                                job,
                                f"块采纳 +{len(res.get('confirmed') or [])} "
                                f"失败 {len(res.get('failed') or [])}",
                            )
            except Exception as exc:  # noqa: BLE001
                _log.warning("pipeline chunk failed: %s", exc)
                job["failed"] += len(chunk)
                _append_log(job, f"块失败: {exc}")
            finally:
                job["done"] = min(job["total"], job["done"] + len(chunk))
                _mark_progress(job)
                await _persist_job(job_id, job, force=True)

        job["status"] = "done"
        _append_log(
            job,
            f"完成 total={job['total']} adopted={job['adopted']} "
            f"suggested={job['suggested']} failed={job['failed']}",
        )
        await _persist_job(job_id, job, force=True)
    except Exception as exc:  # noqa: BLE001
        _log.exception("option-vocab pipeline %s crashed", job_id)
        job["status"] = "error"
        job["error"] = str(exc)
        _append_log(job, f"任务异常: {exc}")
        await _persist_job(job_id, job, force=True)


async def start_run(
    *,
    paper_ids: list[uuid.UUID],
    types: list[str],
    concurrency: int,
    auto_adopt: bool,
    force_suggest: bool,
    admin_id: uuid.UUID,
    region_code: str | None = None,
    region_name: str | None = None,
    year: int | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    type_list = [t for t in types if t in PIPELINE_TYPE_KEYS] or list(PIPELINE_TYPE_KEYS)
    now = datetime.now(timezone.utc).isoformat()
    _jobs[job_id] = {
        "status": "pending",
        "total": 0,
        "done": 0,
        "failed": 0,
        "adopted": 0,
        "suggested": 0,
        "error": "",
        "logs": [],
        "concurrency": concurrency,
        "auto_adopt": auto_adopt,
        "force_suggest": force_suggest,
        "region_code": region_code,
        "region_name": region_name,
        "year": year,
        "types": type_list,
        "paper_ids": [str(x) for x in paper_ids],
        "admin_id": str(admin_id),
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "_dirty": True,
        "_persist_n": 0,
    }
    await _persist_job(job_id, _jobs[job_id], force=True)
    t = asyncio.create_task(_run_job(
        job_id,
        paper_ids=paper_ids,
        types=type_list,
        concurrency=concurrency,
        auto_adopt=auto_adopt,
        force_suggest=force_suggest,
        admin_id=admin_id,
    ))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return job_id
