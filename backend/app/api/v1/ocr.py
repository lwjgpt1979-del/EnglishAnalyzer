"""OCR 相关 API。

POST  /wrong-questions/{id}/ocr        触发 OCR（幂等，completed 不重复触发）
GET   /wrong-questions/{id}/ocr        查询最新 OCR 任务状态
PATCH /wrong-questions/{id}/text       手动确认/覆盖 OCR 识别文字
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.models.d3_wrong_questions import OcrTask, WrongQuestion
from app.schemas.base import BaseResponse, make_ok
from app.schemas.ocr import ConfirmOcrTextRequest, OcrStatusOut
from app.schemas.wrong_questions import WrongQuestionOut
from app.services import wrong_question_service

router = APIRouter(prefix="/wrong-questions", tags=["ocr"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


async def _run_ocr_pipeline(wq_id: uuid.UUID) -> None:
    """后台任务：执行 OCR + DeepSeek 解析，写回 WrongQuestion。"""
    from app.core.database import async_session_factory as _async_session_factory
    from app.services.ocr_service import run_ocr
    from app.services.ocr_parser_service import parse_ocr_result
    from datetime import datetime, timezone

    async with _async_session_factory() as db:
        wq: WrongQuestion | None = await db.get(WrongQuestion, wq_id)
        if wq is None:
            return

        # 创建 OcrTask 记录，状态设为 processing
        ocr_task = OcrTask(
            wrong_question_id=wq_id,
            status="processing",
            provider="aliyun_print",  # 主引擎标识
        )
        db.add(ocr_task)
        wq.ocr_status = "processing"  # type: ignore[assignment]
        await db.commit()

        try:
            ocr_result = await run_ocr(wq.source_image_url)
            parsed = await parse_ocr_result(ocr_result)

            # 写回结构化字段
            wq.question_text = parsed.question_text
            wq.student_answer = parsed.student_answer
            wq.correct_answer = parsed.correct_answer
            if parsed.question_type and wq.question_type is None:
                wq.question_type = parsed.question_type  # type: ignore[assignment]
            wq.ocr_status = "completed"  # type: ignore[assignment]

            # R7:单题拍照错题 → 统一接入(classify→match_kp→uploaded_question + wrong_record);
            # 防御式,失败不阻断 OCR 主流程(闭 R3 单题收口遗留)
            try:
                from app.services.kp_classifier_service import classify_kps
                from app.services.paper_split_service import ParsedPaperQuestion
                from app.services import ingest_service
                pq = ParsedPaperQuestion(
                    question_no="1", question_type=str(wq.question_type) if wq.question_type else None,
                    stem=parsed.question_text or "", student_answer=parsed.student_answer or "",
                    correct_answer=parsed.correct_answer or "", explanation=None)
                kp_map = await classify_kps([pq])
                item = ingest_service.IngestItem(
                    question_no="1", question_type=pq.question_type, stem=parsed.question_text,
                    student_answer=parsed.student_answer, correct_answer=parsed.correct_answer,
                    is_wrong=True, kp_name=kp_map.get("1"))
                await ingest_service.ingest_parsed(
                    db, owner_scope="student", owner_id=wq.student_id, items=[item],
                    source_type="uploaded_student")
            except Exception:  # noqa: BLE001
                pass

            # 更新 OcrTask 记录
            ocr_task.status = "completed"  # type: ignore[assignment]
            ocr_task.raw_result = {  # type: ignore[assignment]
                "printed_text": ocr_result.printed_text,
                "handwritten_text": ocr_result.handwritten_text,
            }
            ocr_task.completed_at = datetime.now(timezone.utc)

        except Exception as exc:
            wq.ocr_status = "failed"  # type: ignore[assignment]
            ocr_task.status = "failed"  # type: ignore[assignment]
            ocr_task.error_message = str(exc)

        await db.commit()


@router.post("/{wq_id}/ocr", response_model=BaseResponse[WrongQuestionOut])
async def trigger_ocr(
    wq_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """触发 OCR 识别（幂等：completed 状态不重新触发）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    if wq.ocr_status == "completed":
        return make_ok(WrongQuestionOut.model_validate(wq))
    if wq.ocr_status in ("processing", "pending"):
        raise AppError(code=409, message="OCR 识别正在进行中，请稍后查询状态")

    # 标记 pending
    wq.ocr_status = "pending"  # type: ignore[assignment]
    await db.commit()
    await db.refresh(wq)

    # 异步后台执行
    background_tasks.add_task(_run_ocr_pipeline, wq_id)

    return make_ok(WrongQuestionOut.model_validate(wq))


@router.get("/{wq_id}/ocr", response_model=BaseResponse[OcrStatusOut])
async def get_ocr_status(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查询最新 OCR 任务状态。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")

    # 查最新 OcrTask
    result = await db.execute(
        select(OcrTask)
        .where(OcrTask.wrong_question_id == wq_id)
        .order_by(OcrTask.created_at.desc())
        .limit(1)
    )
    task = result.scalar_one_or_none()

    return make_ok(
        OcrStatusOut(
            wrong_question_id=wq_id,
            ocr_status=wq.ocr_status,
            printed_text=task.raw_result.get("printed_text") if task and task.raw_result else None,
            handwritten_text=task.raw_result.get("handwritten_text") if task and task.raw_result else None,
            error_message=task.error_message if task else None,
            updated_at=task.updated_at if task else None,
        )
    )


@router.patch("/{wq_id}/text", response_model=BaseResponse[WrongQuestionOut])
async def confirm_ocr_text(
    wq_id: uuid.UUID,
    body: ConfirmOcrTextRequest,
    db: DbDep,
    current_user: UserDep,
):
    """手动确认/覆盖 OCR 识别结果（用户可修正识别错误）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")

    # §5.5 手动修正率：仅当用户实际改动过识别结果才计为「修正」
    def _changed(new, old) -> bool:
        return new is not None and (new or "").strip() != ((old or "") if old is not None else "").strip()
    corrected = (
        _changed(body.question_text, wq.question_text)
        or _changed(body.student_answer, wq.student_answer)
        or _changed(body.correct_answer, wq.correct_answer)
        or (body.question_type is not None and body.question_type != wq.question_type)
    )

    if body.question_text is not None:
        wq.question_text = body.question_text
    if body.student_answer is not None:
        wq.student_answer = body.student_answer
    if body.correct_answer is not None:
        wq.correct_answer = body.correct_answer
    if body.question_type is not None:
        wq.question_type = body.question_type  # type: ignore[assignment]

    if corrected:
        wq.ocr_corrected = True
    # 手动修正后强制标记为 completed
    wq.ocr_status = "completed"  # type: ignore[assignment]

    await db.commit()
    await db.refresh(wq)
    return make_ok(WrongQuestionOut.model_validate(wq))
