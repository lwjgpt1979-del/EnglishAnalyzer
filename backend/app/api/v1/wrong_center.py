"""R3 错题中心/复习 API(KP-First,基于 wrong_record)。

学生侧:今日复习队列 + 提交复习评分(SM-2)。数据载体为 wrong_record(切换自旧 wrong_questions)。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    WrongReviewItem, WrongReviewQueueOut, WrongReviewSubmitIn, WrongReviewSubmitOut,
)
from app.services import wrong_center_service, wrong_review_service

router = APIRouter(prefix="/wrong-center", tags=["wrong-center"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/list", response_model=BaseResponse[dict])
async def list_center(
    db: DbDep, current_user: UserDep,
    kind: str | None = Query(None, description="grammar|vocab 副筛选;空=全部"),
    status: str | None = Query(None, description="pending|reviewing|mastered;空=全部"),
    source_label: str | None = Query(None, description="来源 tab:作业|长难句|平台;空=全部真实错题"),
    kp_name: str | None = Query(None, description="展开某考点组时过滤"),
    source_id: uuid.UUID | None = Query(None, description="展开某批次组时过滤"),
    skip: int = 0, limit: int = 20,
):
    """「我的错题」统一列表:只读 wrong_record。来源 tab + 语法/词汇副筛选 + 折叠展开 + 三态 + 分页。默认只列真实错题。"""
    items, total = await wrong_center_service.list_center(
        db, student_id=current_user.id, kind=kind, status=status,
        source_label=source_label, kp_name=kp_name, source_id=source_id,
        is_original=True, skip=skip, limit=limit)
    return make_ok({"items": items, "total": total})


@router.get("/counts", response_model=BaseResponse[dict])
async def lifecycle_counts(
    db: DbDep, current_user: UserDep,
    kind: str | None = Query(None, description="grammar|vocab;空=全部"),
    source_label: str | None = Query(None, description="来源 tab;空=全部真实错题"),
):
    """状态 chip 计数(全部/待巩固/巩固中/已掌握),随 kind/来源 变(仅真实错题)。"""
    counts = await wrong_center_service.lifecycle_counts(
        db, student_id=current_user.id, kind=kind, source_label=source_label, is_original=True)
    return make_ok(counts)


@router.get("/grouped", response_model=BaseResponse[dict])
async def grouped(
    db: DbDep, current_user: UserDep,
    view: str = Query("kp", description="kp=按考点 | batch=按批次"),
    source_label: str | None = Query(None, description="来源 tab;空=全部真实错题"),
    kind: str | None = Query(None, description="grammar|vocab 副筛选"),
    status: str | None = Query(None, description="pending|reviewing|mastered 状态筛选(未/中/已巩固)"),
):
    """类目内聚合(真实错题):view=kp 按考点、view=batch 按批次;status 按 SM-2 生命周期筛。供折叠卡+时间分段。"""
    if view == "batch":
        groups = await wrong_center_service.group_by_batch(
            db, student_id=current_user.id, source_label=source_label, kind=kind, status=status)
    else:
        groups = await wrong_center_service.group_by_kp(
            db, student_id=current_user.id, source_label=source_label, kind=kind, status=status)
    return make_ok({"view": view, "groups": groups})


@router.get("/consolidation", response_model=BaseResponse[dict])
async def consolidation(db: DbDep, current_user: UserDep):
    """「练习巩固」tab:练习衍生薄弱项(is_original=false),按 (词·维) 聚合。"""
    items = await wrong_center_service.list_practice_consolidation(db, student_id=current_user.id)
    return make_ok({"items": items, "total": len(items)})


@router.get("/ls-consolidation", response_model=BaseResponse[dict])
async def ls_consolidation(db: DbDep, current_user: UserDep):
    """「长难句薄弱」tab:长难句探针答错的练习衍生句卡(按句·维聚合;成分/理解=整句维)。"""
    items = await wrong_center_service.list_ls_consolidation(db, student_id=current_user.id)
    return make_ok({"items": items, "total": len(items)})


@router.get("/component-understanding", response_model=BaseResponse[dict])
async def component_understanding(db: DbDep, current_user: UserDep):
    """「句子成分理解」块(方案B):精读闯关细分错误按三技能(抓主干/辨修饰/理关系)聚合,下钻到角色·句。"""
    skills = await wrong_center_service.component_understanding(db, student_id=current_user.id)
    return make_ok({"skills": skills})


@router.get("/ls-diagnostics", response_model=BaseResponse[dict])
async def ls_diagnostics(db: DbDep, current_user: UserDep):
    """长难句时间线诊断(变体2):按句聚合成分/合成/语法/重点词四类错误 + 状态 + 时间桶,供时间线句卡+展开四分区。"""
    items = await wrong_center_service.ls_sentence_diagnostics(db, student_id=current_user.id)
    return make_ok({"items": items})


@router.post("/practice/{wrong_record_id}", response_model=BaseResponse[dict])
async def practice_wrong(wrong_record_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """错题「练同类仿真题」(统一入口,按 wrong_record 派发)。"""
    r = await wrong_center_service.practice_for_wrong(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id)
    await db.commit()
    kp_name = r["knowledge_point"]
    # generate 返回 AiQuestion ORM 对象,手动序列化(含 answer/explanation 供前端判分即时反馈)
    return make_ok({
        "knowledge_point": kp_name,
        "questions": [
            {
                "id": str(q.id),
                "knowledge_point_name": kp_name,
                "question_type": str(q.question_type),
                "difficulty": q.difficulty,
                "stem": (q.content or {}).get("stem", ""),
                "options": (q.content or {}).get("options"),
                "answer": (q.content or {}).get("answer"),
                "explanation": (q.content or {}).get("explanation"),
            } for q in r["questions"]
        ],
    })


@router.post("/practice-result/{wrong_record_id}", response_model=BaseResponse[dict])
async def practice_result(
    wrong_record_id: uuid.UUID, body: dict, db: DbDep, current_user: UserDep,
):
    """练同类一轮做完回写成绩:记 practice_count/correct;语法据正确率推进 SM-2。
    body: {total, correct}"""
    r = await wrong_center_service.record_practice_result(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id,
        total=int(body.get("total", 0)), correct=int(body.get("correct", 0)),
        advance_review=bool(body.get("advance_review", False)))
    await db.commit()
    return make_ok(r)


@router.get("/vocab-sim/{wrong_record_id}", response_model=BaseResponse[dict])
async def vocab_sim(wrong_record_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """词汇错题「学这个词」:富词卡(配图/短语/发音)+ 仿真练习 5 题(纯选择,全局缓存复用)。"""
    r = await wrong_center_service.vocab_sim_payload(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id)
    await db.commit()
    return make_ok(r)


@router.get("/word-net/{word_id}", response_model=BaseResponse[dict])
async def word_net(word_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """以词为中心的错题网(切换中心用):该词全局考点(dims,含关系词供辐射图)
    + 主错题(该词是正确答案)+ 次错题(该词只是干扰项)。查看即生成 + 幂等索引。"""
    from app.services import wrong_word_net_service
    r = await wrong_word_net_service.word_wrong_net(
        db, student_id=current_user.id, word_id=word_id)
    return make_ok(r)


@router.get("/{wrong_record_id}/word-net", response_model=BaseResponse[dict])
async def word_net_of_record(wrong_record_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """从一道错题进入错题网:中心 = 该题正确答案词。返回该词考点 + 主/次错题。"""
    from app.services import wrong_word_net_service
    r = await wrong_word_net_service.word_net_for_record(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id)
    return make_ok(r)


@router.post("/vocab-sim-result/{wrong_record_id}", response_model=BaseResponse[dict])
async def vocab_sim_result(wrong_record_id: uuid.UUID, body: dict, db: DbDep, current_user: UserDep):
    """仿真练习一轮结算:5 题全对 → 判掌握、进已掌握。body: {total, correct}"""
    r = await wrong_center_service.submit_vocab_sim(
        db, student_id=current_user.id, wrong_record_id=wrong_record_id,
        total=int(body.get("total", 0)), correct=int(body.get("correct", 0)))
    await db.commit()
    return make_ok(r)


@router.get("/review-queue", response_model=BaseResponse[WrongReviewQueueOut])
async def review_queue(db: DbDep, current_user: UserDep):
    """今日待复习错题队列(KP-First / wrong_record)。"""
    rows = await wrong_review_service.get_due_queue(db, student_id=current_user.id)
    items = [WrongReviewItem(
        id=r.id, q_scope=r.q_scope, question_id=r.question_id, node_id=r.node_id,
        review_count=r.review_count, next_review_at=r.next_review_at,
    ) for r in rows]
    return make_ok(WrongReviewQueueOut(due_count=len(items), items=items))


@router.post("/review", response_model=BaseResponse[WrongReviewSubmitOut])
async def submit_review(body: WrongReviewSubmitIn, db: DbDep, current_user: UserDep):
    """提交复习评分 → SM-2 调度;达标判掌握。"""
    wr = await wrong_review_service.submit_review(
        db, student_id=current_user.id, wrong_record_id=body.wrong_record_id, quality=body.quality,
    )
    await db.commit()
    return make_ok(WrongReviewSubmitOut(
        status=wr.status, review_count=wr.review_count, next_review_at=wr.next_review_at,
    ))
