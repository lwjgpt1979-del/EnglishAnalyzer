"""定时任务运行记录 + 失败告警 + 看板(解决 cron 哑火无人知)。

- TASKS 注册表:所有 crontab 任务(app/tasks/*)的键、中文名、期望间隔(小时);
  看板据此列出全部任务——**即使从没跑过也显示**,便于发现「该跑没跑」的哑火任务。
- run(task, fn):任务代码零侵入包一层。开始写 running 行,成功写 success+result,
  失败写 failed+error 并**告警全权超管**(站内通知)。记账用独立会话,任务事务回滚也不影响留痕。
- overview:每任务最近一次 + 是否 stale(超过期望间隔的 1.5 倍没成功 / 从没跑过)。
"""
from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d9_system import Notification, TaskRun

# 任务注册表:key → (中文名, 期望间隔小时)。新增 crontab 任务时在此登记。
TASKS: dict[str, tuple[str, int]] = {
    "checkin_reminders": ("学习签到提醒", 24),
    "refund_sla_alerts": ("退款 SLA 超时告警", 24),
    "weekly_reports": ("学习周报推送", 168),
    "expiry_alerts": ("会员到期提醒", 24),
    "vocab_probes_backfill": ("词汇探针预生成", 24),
    "grammar_probes_backfill": ("语法探针预生成", 24),
    "map_crawl": ("地图获客按区县采集", 24),
    "kp_mcq_autofix": ("考点题AI审校修正(低峰)", 24),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _start(task: str) -> uuid.UUID:
    rid = uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(TaskRun(id=rid, task=task, status="running", started_at=_now()))
        await s.commit()
    return rid


async def _finish(rid: uuid.UUID, task: str, status: str, *,
                  result: dict | None = None, error: str | None = None) -> None:
    async with _async_session_factory() as s:
        row = await s.get(TaskRun, rid)
        if row is None:                       # 兜底:_start 没落上也补一行
            row = TaskRun(id=rid, task=task, started_at=_now())
            s.add(row)
        row.status = status
        row.finished_at = _now()
        row.duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
        # result 可能含非 JSON 值,尽量存;存不下就转字符串摘要
        if result is not None:
            try:
                import json
                json.dumps(result)
                row.result = result
            except Exception:  # noqa: BLE001
                row.result = {"_repr": str(result)[:2000]}
        row.error = error
        await s.commit()


async def _alert_super_admins(task: str, error: str) -> None:
    """任务失败 → 给全权超管发站内告警(admin_modules IS NULL)。失败不影响主流程。"""
    try:
        label = TASKS.get(task, (task, 0))[0]
        async with _async_session_factory() as s:
            # 只发给能登录的真运营超管(有 username);openid-only 账号发了也看不到
            admins = (await s.execute(sa.select(User.id).where(
                User.role == "platform_admin", User.is_active.is_(True),
                User.admin_modules.is_(None), User.username.is_not(None)))).scalars().all()
            for uid in admins:
                s.add(Notification(
                    id=uuid.uuid4(), user_id=uid, type="system", channel="system",
                    title=f"⚠️ 定时任务失败:{label}",
                    content=f"任务「{label}」({task})本次运行失败,请检查。\n{error[:300]}",
                    meta={"kind": "task_failed", "task": task},
                    expires_at=_now() + timedelta(days=14)))
            await s.commit()
    except Exception:  # noqa: BLE001
        pass


async def run(task: str, fn: Callable[[AsyncSession], Awaitable[dict | None]]) -> dict | None:
    """包裹一次任务运行:落 running→success/failed,失败告警。fn 接收工作会话,返回汇总 dict。

    工作会话与记账会话分离:即使 fn 里事务回滚,运行留痕/告警照样落库。
    """
    rid = await _start(task)
    try:
        async with _async_session_factory() as s:
            result = await fn(s)
        await _finish(rid, task, "success", result=result if isinstance(result, dict) else None)
        return result
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        await _finish(rid, task, "failed", error=err)
        await _alert_super_admins(task, f"{type(e).__name__}: {e}")
        raise


# ──────────────── 看板查询 ────────────────
def _stale(task: str, last_success_at: datetime | None) -> bool:
    """从没成功过、或最近一次成功超过期望间隔的 1.5 倍 → 视为哑火/异常。"""
    cadence_h = TASKS.get(task, ("", 24))[1]
    if last_success_at is None:
        return True
    return _now() - last_success_at > timedelta(hours=cadence_h * 1.5)


async def overview(db: AsyncSession) -> dict:
    """每个已登记任务的最近一次运行 + 最近一次成功 + 是否哑火/失败。"""
    # 每任务最近一次运行
    last_run_sq = sa.select(
        TaskRun.task, sa.func.max(TaskRun.started_at).label("mx")
    ).group_by(TaskRun.task).subquery()
    last_rows = (await db.execute(
        sa.select(TaskRun).join(
            last_run_sq,
            sa.and_(TaskRun.task == last_run_sq.c.task,
                    TaskRun.started_at == last_run_sq.c.mx)))).scalars().all()
    last_by = {r.task: r for r in last_rows}
    # 每任务最近一次成功时间
    succ_rows = (await db.execute(
        sa.select(TaskRun.task, sa.func.max(TaskRun.started_at))
        .where(TaskRun.status == "success").group_by(TaskRun.task))).all()
    succ_by = {t: at for t, at in succ_rows}

    items = []
    ok = stale = failing = 0
    for task, (label, cadence_h) in TASKS.items():
        r = last_by.get(task)
        last_success_at = succ_by.get(task)
        is_stale = _stale(task, last_success_at)
        last_status = r.status if r else "never"
        if last_status == "failed":
            failing += 1
        elif is_stale:
            stale += 1
        else:
            ok += 1
        items.append({
            "task": task, "label": label, "cadence_hours": cadence_h,
            "last_status": last_status,
            "last_run_at": r.started_at.isoformat() if r else None,
            "last_result": r.result if r else None,
            "last_error": (r.error[:500] if r and r.error else None),
            "duration_ms": r.duration_ms if r else None,
            "last_success_at": last_success_at.isoformat() if last_success_at else None,
            "stale": is_stale,
        })
    # 未登记但库里有记录的任务(防遗漏)
    known = set(TASKS)
    extra = (await db.execute(
        sa.select(TaskRun.task).where(TaskRun.task.not_in(known)).distinct())).scalars().all()
    for task in extra:
        r = last_by.get(task) or (await db.execute(
            sa.select(TaskRun).where(TaskRun.task == task)
            .order_by(TaskRun.started_at.desc()).limit(1))).scalar_one_or_none()
        if r:
            items.append({"task": task, "label": task + "(未登记)", "cadence_hours": None,
                          "last_status": r.status,
                          "last_run_at": r.started_at.isoformat(),
                          "last_result": r.result, "last_error": (r.error[:500] if r.error else None),
                          "duration_ms": r.duration_ms, "last_success_at": None, "stale": False})
    return {"summary": {"ok": ok, "stale": stale, "failing": failing, "total": len(TASKS)},
            "items": items}


async def list_runs(db: AsyncSession, *, task: str | None = None,
                    status: str | None = None, skip: int = 0, limit: int = 50) -> dict:
    conds = []
    if task:
        conds.append(TaskRun.task == task)
    if status:
        conds.append(TaskRun.status == status)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(TaskRun).where(*conds))).scalar() or 0
    rows = (await db.execute(
        sa.select(TaskRun).where(*conds)
        .order_by(TaskRun.started_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [{
        "id": str(r.id), "task": r.task, "label": TASKS.get(r.task, (r.task, 0))[0],
        "status": r.status, "result": r.result, "error": (r.error[:1000] if r.error else None),
        "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_ms": r.duration_ms,
    } for r in rows]}
