"""整卷上传×错题归集深化（M4）：知识点归集 + 练同类守卫 tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "uppaper"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_kp_summary_and_practice_guards():
    from app.services import user_paper_service as ups
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        stu, other = uuid.uuid4(), uuid.uuid4()
        paper = uuid.uuid4()
        q_wrong, q_ok, q_nokp = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        kp = uuid.uuid4()
        for u in (stu, other):
            await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                             {"i": u, "o": f"{_TAG}_{u.hex[:6]}"})
        await db.execute(text(
            "INSERT INTO user_uploaded_papers (id,student_id,title,source_image_urls,ocr_status) "
            "VALUES (:i,:s,'卷1','[]'::jsonb,'completed')"), {"i": paper, "s": stu})
        for q, wrong in ((q_wrong, True), (q_ok, False), (q_nokp, True)):
            await db.execute(text(
                "INSERT INTO user_paper_questions (id,user_paper_id,stem,is_wrong) "
                "VALUES (:i,:p,'x',:w)"), {"i": q, "p": paper, "w": wrong})
        await db.execute(text(
            "INSERT INTO knowledge_points (id,code,name,category,applicable_grades,applicable_textbooks) "
            "VALUES (:i,:c,'一般现在时','grammar','{}','{}')"),
            {"i": kp, "c": f"{_TAG}_{kp.hex[:6]}"})
        # 关联：q_wrong 与 q_ok 挂到同一 KP；q_nokp 不挂
        for q in (q_wrong, q_ok):
            await db.execute(text(
                "INSERT INTO user_paper_question_knowledge_points (user_paper_question_id,knowledge_point_id) "
                "VALUES (:q,:k)"), {"q": q, "k": kp})
        await db.flush()
        try:
            # 归集：该 KP 总 2 / 错 1 / 薄弱
            summ = await ups.paper_kp_summary(db, paper_id=paper, student_id=stu)
            assert summ is not None and len(summ["items"]) == 1
            it = summ["items"][0]
            assert it["kp_name"] == "一般现在时" and it["total"] == 2 and it["wrong"] == 1 and it["weak"] is True

            # 非本人 → None
            assert await ups.paper_kp_summary(db, paper_id=paper, student_id=other) is None

            # 练同类：他人题 → 404
            with pytest.raises(AppError) as e1:
                await ups.practice_for_question(db, question_id=q_wrong, student_id=other)
            assert e1.value.code == 404
            # 无关联知识点的题 → 400
            with pytest.raises(AppError) as e2:
                await ups.practice_for_question(db, question_id=q_nokp, student_id=stu)
            assert e2.value.code == 400
        finally:
            await db.execute(text("DELETE FROM user_paper_question_knowledge_points WHERE knowledge_point_id=:k"), {"k": kp})
            await db.execute(text("DELETE FROM user_paper_questions WHERE user_paper_id=:p"), {"p": paper})
            await db.execute(text("DELETE FROM user_uploaded_papers WHERE id=:p"), {"p": paper})
            await db.execute(text("DELETE FROM knowledge_points WHERE id=:k"), {"k": kp})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
