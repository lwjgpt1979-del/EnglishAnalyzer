"""听力练习 service（听力跟读模块·精听）。

MVP：精选种子听力素材（对话/短文），音频由前端经 /tts/speak 火山 TTS 实时合成。
后续可接 LLM 按学生薄弱点/教材单元自动生成听力素材。
"""
from __future__ import annotations

from app.core.exceptions import AppError

# 种子听力素材：transcript 用于 TTS 合成 + 回听原文；questions 含答案与解析
_EXERCISES: list[dict] = [
    {
        "id": "lst_dialog_weekend",
        "title": "周末计划（对话）",
        "type": "dialogue",
        "difficulty": 1,
        "transcript": (
            "Anna: Hi Tom, what are you going to do this weekend? "
            "Tom: I'm going to visit my grandparents in the countryside. "
            "Anna: That sounds nice. How will you get there? "
            "Tom: We'll take the train on Saturday morning. "
            "Anna: Will you stay there for the whole weekend? "
            "Tom: Yes, we'll come back on Sunday evening."
        ),
        "questions": [
            {
                "prompt": "What is Tom going to do this weekend?",
                "options": ["Visit his grandparents", "Go to school", "Play football", "Stay at home"],
                "answer_index": 0,
                "explanation": "Tom 说 I'm going to visit my grandparents in the countryside。",
            },
            {
                "prompt": "How will Tom get there?",
                "options": ["By bus", "By train", "By car", "By plane"],
                "answer_index": 1,
                "explanation": "We'll take the train on Saturday morning。",
            },
            {
                "prompt": "When will Tom come back?",
                "options": ["Saturday morning", "Saturday evening", "Sunday morning", "Sunday evening"],
                "answer_index": 3,
                "explanation": "we'll come back on Sunday evening。",
            },
        ],
    },
    {
        "id": "lst_passage_library",
        "title": "我们的图书馆（短文）",
        "type": "monologue",
        "difficulty": 2,
        "transcript": (
            "Our school library is a quiet place for reading. "
            "It opens at eight in the morning and closes at five in the afternoon. "
            "There are thousands of books, including stories, science and history. "
            "Students can borrow three books at a time for two weeks. "
            "Remember to keep the books clean and return them on time."
        ),
        "questions": [
            {
                "prompt": "When does the library close?",
                "options": ["At eight a.m.", "At noon", "At five p.m.", "At eight p.m."],
                "answer_index": 2,
                "explanation": "closes at five in the afternoon。",
            },
            {
                "prompt": "How many books can a student borrow at a time?",
                "options": ["One", "Two", "Three", "Five"],
                "answer_index": 2,
                "explanation": "borrow three books at a time。",
            },
            {
                "prompt": "How long can students keep the books?",
                "options": ["One week", "Two weeks", "One month", "Two months"],
                "answer_index": 1,
                "explanation": "for two weeks。",
            },
        ],
    },
]

_BY_ID = {e["id"]: e for e in _EXERCISES}


def list_exercises() -> list[dict]:
    """列表（不含答案/原文）。"""
    return [
        {
            "id": e["id"],
            "title": e["title"],
            "type": e["type"],
            "difficulty": e["difficulty"],
            "question_count": len(e["questions"]),
        }
        for e in _EXERCISES
    ]


def get_exercise(exercise_id: str) -> dict:
    """详情（含 transcript、题目、答案、解析）。前端控制听前不展示原文/答案。"""
    e = _BY_ID.get(exercise_id)
    if e is None:
        raise AppError(code=404, message="听力素材不存在")
    return e


# ── 精听答题 + 听力错题归集（§6.4）──────────────────────────────────────────────
import uuid as _uuid
import datetime as _dt

from sqlalchemy import and_ as _and, select as _select
from sqlalchemy.ext.asyncio import AsyncSession as _Session

from app.models.d5_learning import ListeningWrongQuestion as _LWQ


async def submit_answers(db: _Session, *, student_id, exercise_id: str,
                         answers: list[int]) -> dict:
    """提交精听答案：判分 + 错题归集（答错入库、重练答对则移出）。"""
    e = _BY_ID.get(exercise_id)
    if e is None:
        raise AppError(code=404, message="听力素材不存在")
    qs = e["questions"]
    now = _dt.datetime.now(_dt.timezone.utc)
    results, correct = [], 0
    for i, q in enumerate(qs):
        chosen = answers[i] if i < len(answers) else -1
        ok = chosen == q["answer_index"]
        if ok:
            correct += 1
        results.append({
            "index": i, "prompt": q["prompt"], "options": q["options"],
            "your_index": chosen, "correct_index": q["answer_index"],
            "is_correct": ok, "explanation": q["explanation"],
        })
        existing = await db.scalar(_select(_LWQ).where(_and(
            _LWQ.student_id == student_id, _LWQ.exercise_id == exercise_id,
            _LWQ.question_index == i)))
        if not ok:
            if existing is None:
                db.add(_LWQ(
                    id=_uuid.uuid4(), student_id=student_id, exercise_id=exercise_id,
                    exercise_title=e["title"], question_index=i, prompt=q["prompt"],
                    options=q["options"], correct_index=q["answer_index"],
                    chosen_index=chosen, explanation=q["explanation"],
                    wrong_count=1, last_wrong_at=now))
            else:
                existing.wrong_count = (existing.wrong_count or 0) + 1
                existing.chosen_index = chosen
                existing.last_wrong_at = now
        elif existing is not None:
            await db.delete(existing)   # 重练答对 → 移出错题库
    await db.flush()
    return {
        "exercise_id": exercise_id, "title": e["title"],
        "correct_count": correct, "total": len(qs),
        "transcript": e["transcript"], "results": results,
    }


async def list_wrong(db: _Session, *, student_id) -> list[dict]:
    """听力错题库：按错误次数 + 最近错误时间排序。"""
    rows = (await db.execute(
        _select(_LWQ).where(_LWQ.student_id == student_id)
        .order_by(_LWQ.wrong_count.desc(), _LWQ.last_wrong_at.desc())
    )).scalars().all()
    return [{
        "id": str(r.id), "exercise_id": r.exercise_id, "exercise_title": r.exercise_title,
        "question_index": r.question_index, "prompt": r.prompt, "options": r.options or [],
        "correct_index": r.correct_index, "explanation": r.explanation,
        "wrong_count": r.wrong_count,
        "last_wrong_at": r.last_wrong_at.isoformat() if r.last_wrong_at else None,
    } for r in rows]
