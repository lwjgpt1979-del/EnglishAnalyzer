"""学生查看 / 作答班级试卷（V2 M28）。"""
from __future__ import annotations

import uuid
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]
from app.models.d7_teacher import ClassStudent
from app.schemas.base import BaseResponse, make_ok
from app.schemas.teacher_exam import ClassPaperOut, ClassPaperDetailOut, SimQuestionOut
from app.services import teacher_exam_service

router = APIRouter(prefix="/student", tags=["student-papers"])


@router.get("/classes/{class_id}/papers", response_model=BaseResponse[list[ClassPaperOut]])
async def list_student_class_papers(
    class_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """学生查看所在班级的试卷列表（答案隐藏）。"""
    await get_rls_db(db, str(current_user.id))

    # 验证学生在该班级内
    membership = (await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == class_id,
            ClassStudent.student_id == current_user.id,
        )
    )).scalar_one_or_none()
    if membership is None:
        raise AppError(code=403, message="您不在该班级")

    papers = await teacher_exam_service.list_class_papers(db, class_id=class_id)
    result = []
    for p in papers:
        qcount = await teacher_exam_service.get_paper_question_count(db, paper_id=p.id)
        result.append(ClassPaperOut(
            paper_id=p.id,
            class_id=p.class_id,
            title=p.title,
            textbook_version=p.textbook_version,
            grade=p.grade,
            semester=p.semester,
            description=p.description,
            question_count=qcount,
            status=p.status,
            created_at=p.created_at,
        ))
    return make_ok(result)


@router.get("/papers/{paper_id}", response_model=BaseResponse[ClassPaperDetailOut])
async def get_student_paper_detail(
    paper_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """学生查看试卷题目（答案隐藏，提交后通过 /questions/exam-attempts 获取解析）。"""
    await get_rls_db(db, str(current_user.id))

    paper, questions = await teacher_exam_service.get_paper_with_questions(
        db, paper_id=paper_id,
    )

    # 验证学生在该班级
    membership = (await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == paper.class_id,
            ClassStudent.student_id == current_user.id,
        )
    )).scalar_one_or_none()
    if membership is None:
        raise AppError(code=403, message="您不在该班级")

    return make_ok(ClassPaperDetailOut(
        paper_id=paper.id,
        class_id=paper.class_id,
        title=paper.title,
        textbook_version=paper.textbook_version,
        grade=paper.grade,
        semester=paper.semester,
        description=paper.description,
        question_count=len(questions),
        status=paper.status,
        created_at=paper.created_at,
        # 学生视角：只给 stem/options/difficulty，不给 answer/explanation
        questions=[
            SimQuestionOut(
                id=q.id,
                knowledge_point_id=q.knowledge_point_id,
                question_type=str(q.question_type),
                stem=q.stem,
                options=q.options,
                difficulty=q.difficulty,
                dimension=str(q.dimension) if q.dimension else None,
            )
            for q in questions
        ],
    ))
