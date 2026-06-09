"""AI 练习模块业务逻辑。

功能：
- get_or_create_knowledge_point: 按 name 找或建 KnowledgePoint（满足 ai_questions FK）
- generate_practice_questions: 调 DeepSeek 生成单选题，写入 ai_questions（dev mock）
- get_question: 按 id 取题（含答案，内部用）
- submit_answer: 服务端判分，写入 practice_records
- get_practice_history: 学生练习记录分页
- get_practice_stats: 练习统计（总数/正确数/正确率/按知识点）

约定：
- content JSONB = {"stem", "options": [...], "answer", "explanation"}
- 判分 is_correct = (answer.strip() == content["answer"].strip())
- dev 模式（deepseek_api_key 以 'sk-placeholder' 开头）返回固定 mock 题
"""
from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import KnowledgePoint
from app.models.d6_ai_questions import AiQuestion, PracticeRecord
from app.services import diagnosis_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_SYSTEM_PROMPT = (
    "你是专业的英语出题老师，擅长围绕指定知识点生成高质量单选练习题。"
    "请严格按 JSON 数组格式输出，不要任何额外文字或 markdown 代码块。"
)

_USER_PROMPT_TEMPLATE = """请围绕英语知识点"{knowledge_point}"，生成 {count} 道难度为 {difficulty}（1最易5最难）的单选题。

每题必须包含 4 个选项，answer 为正确选项的完整文本（与 options 中某项完全一致）。

请仅返回 JSON 数组（不要任何 markdown 代码块或额外文字）：
[
  {{
    "stem": "题干（含空格用 ___ 表示）",
    "options": ["选项A", "选项B", "选项C", "选项D"],
    "answer": "正确选项的完整文本",
    "explanation": "解析（1-2句，说明为什么）"
  }}
]"""




def _slugify_code(name: str) -> str:
    """从知识点名生成稳定唯一 code 前缀（非 ASCII 用 hex 兜底）。"""
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    if not ascii_part:
        ascii_part = "kp"
    return ascii_part[:40]


async def get_or_create_knowledge_point(
    db: AsyncSession,
    *,
    name: str,
    category: str = "grammar",
) -> KnowledgePoint:
    """按 name 查找知识点；不存在则创建（默认 category=grammar）。"""
    result = await db.execute(select(KnowledgePoint).where(KnowledgePoint.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    code = f"auto_{_slugify_code(name)}_{uuid.uuid4().hex[:8]}"
    kp = KnowledgePoint(
        id=uuid.uuid4(),
        code=code,
        name=name,
        category=category,  # type: ignore[arg-type]
        description=None,
        applicable_grades=[],
        applicable_textbooks=[],
        sort_order=0,
    )
    db.add(kp)
    await db.flush()
    return kp


def _dev_mock_questions(knowledge_point: str, count: int) -> list[dict]:
    """dev 模式返回固定 mock 题（围绕知识点变体）。"""
    base = [
        {
            "stem": f"[{knowledge_point}] She ___ to school every day.",
            "options": ["go", "goes", "going", "gone"],
            "answer": "goes",
            "explanation": "主语 She 第三人称单数，动词用 goes。",
        },
        {
            "stem": f"[{knowledge_point}] They ___ very happy today.",
            "options": ["is", "am", "are", "be"],
            "answer": "are",
            "explanation": "复数主语 They 用 are。",
        },
        {
            "stem": f"[{knowledge_point}] I ___ a middle school student.",
            "options": ["is", "am", "are", "be"],
            "answer": "am",
            "explanation": "第一人称单数 I 用 am。",
        },
    ]
    out: list[dict] = []
    for i in range(count):
        out.append(base[i % len(base)])
    return out


async def generate_practice_questions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    knowledge_point: str | None,
    count: int,
    difficulty: int,
) -> list[AiQuestion]:
    """生成并落库练习题。

    - knowledge_point 为空 → 取学生最薄弱知识点（无则 AppError 400）
    - dev 模式 → 固定 mock；否则调 DeepSeek
    - DeepSeek 错误 → AppError(502)；JSON 解析失败 → AppError(500)
    """
    kp_name = knowledge_point
    if not kp_name:
        # M43：优先从 student_kp_mastery 台账读弱项
        from app.services.adaptive_question_service import _get_weak_kp_names_from_mastery
        mastery_weak = await _get_weak_kp_names_from_mastery(db, student_id=student_id, top_n=1)
        if mastery_weak:
            kp_name = mastery_weak[0]
        else:
            # fallback：旧 diagnosis_service 逻辑
            report = await diagnosis_service.get_diagnosis_report(db, student_id=student_id)
            if not report.top_weak_knowledge_points:
                raise AppError(code=400, message="暂无薄弱知识点，请先完成练习或上传错题")
            kp_name = report.top_weak_knowledge_points[0].knowledge_point

    kp = await get_or_create_knowledge_point(db, name=kp_name)

    if is_llm_dev_mode():
        raw_questions = _dev_mock_questions(kp_name, count)
    else:
        prompt = _USER_PROMPT_TEMPLATE.format(
            knowledge_point=kp_name, count=count, difficulty=difficulty
        )
        try:
            response = await chat_completion(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=2048,
            )
        except Exception as exc:  # noqa: BLE001
            raise AppError(code=502, message=f"AI出题服务暂时不可用，请稍后重试（{exc}）") from exc

        raw_text = (response.choices[0].message.content or "").strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw_text).strip()
        try:
            raw_questions = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AppError(code=500, message="AI出题返回格式异常") from exc
        if not isinstance(raw_questions, list) or not raw_questions:
            raise AppError(code=500, message="AI出题返回内容为空")

    now = datetime.now(timezone.utc)
    created: list[AiQuestion] = []
    for rq in raw_questions[:count]:
        if not all(k in rq for k in ("stem", "options", "answer", "explanation")):
            continue
        q = AiQuestion(
            id=uuid.uuid4(),
            knowledge_point_id=kp.id,
            unit_id=None,
            question_type="单选",  # type: ignore[arg-type]
            difficulty=difficulty,
            content={
                "stem": rq["stem"],
                "options": rq["options"],
                "answer": rq["answer"],
                "explanation": rq["explanation"],
            },
            is_active=True,
            generated_at=now,
            usage_count=0,
        )
        db.add(q)
        created.append(q)

    if not created:
        raise AppError(code=500, message="AI出题返回内容无有效题目")

    await db.flush()
    return created


async def get_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
) -> AiQuestion | None:
    """按 id 取题（含答案，内部判分/下发用）。"""
    result = await db.execute(select(AiQuestion).where(AiQuestion.id == question_id))
    return result.scalar_one_or_none()


async def submit_answer(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    question_id: uuid.UUID,
    answer: str,
    time_spent_sec: int | None = None,
) -> PracticeRecord:
    """服务端判分并写入 practice_records。题不存在 → AppError(404)。"""
    question = await get_question(db, question_id=question_id)
    if question is None:
        raise AppError(code=404, message="题目不存在")

    correct_answer = str(question.content.get("answer", "")).strip()
    is_correct = answer.strip() == correct_answer

    record = PracticeRecord(
        id=uuid.uuid4(),
        student_id=student_id,
        question_id=question_id,
        trigger_type="module8_free",  # type: ignore[arg-type]
        student_answer={"answer": answer},
        is_correct=is_correct,
        wrong_question_id=None,
        practiced_at=datetime.now(timezone.utc),
        time_spent_sec=time_spent_sec,
    )
    db.add(record)
    question.usage_count = (question.usage_count or 0) + 1
    await db.flush()

    # M39: 更新个人知识点掌握台账
    from app.services import kp_mastery_service
    kp_name = str(question.content.get("knowledge_point", "")) or None
    kp_desc: str | None = None
    if not kp_name:
        kp_result = await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == question.knowledge_point_id)
        )
        kp_obj = kp_result.scalar_one_or_none()
        if kp_obj:
            kp_name = kp_obj.name
            kp_desc = kp_obj.description
    if kp_name:
        await kp_mastery_service.upsert_mastery(
            db,
            student_id=student_id,
            kp_key=kp_name,
            kp_id=question.knowledge_point_id,
            is_correct=is_correct,
            source="practice",
            kp_description=kp_desc,
        )

    return record


async def get_practice_history(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[PracticeRecord], int]:
    """分页返回学生练习记录（按时间倒序）+ 总数。"""
    count_result = await db.execute(
        select(func.count())
        .select_from(PracticeRecord)
        .where(PracticeRecord.student_id == student_id)
    )
    total = int(count_result.scalar_one())

    result = await db.execute(
        select(PracticeRecord)
        .where(PracticeRecord.student_id == student_id)
        .order_by(PracticeRecord.practiced_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def get_practice_stats(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> dict:
    """聚合练习统计：总数、正确数、正确率、按知识点细分。"""
    result = await db.execute(
        select(
            PracticeRecord.is_correct,
            KnowledgePoint.name,
        )
        .join(AiQuestion, AiQuestion.id == PracticeRecord.question_id)
        .join(KnowledgePoint, KnowledgePoint.id == AiQuestion.knowledge_point_id)
        .where(PracticeRecord.student_id == student_id)
    )
    rows = result.all()

    total_practiced = len(rows)
    total_correct = sum(1 for r in rows if r.is_correct)
    correct_rate = round(total_correct / total_practiced, 4) if total_practiced > 0 else 0.0

    by_kp: dict[str, dict[str, int]] = defaultdict(lambda: {"practiced": 0, "correct": 0})
    for r in rows:
        by_kp[r.name]["practiced"] += 1
        if r.is_correct:
            by_kp[r.name]["correct"] += 1

    return {
        "total_practiced": total_practiced,
        "total_correct": total_correct,
        "correct_rate": correct_rate,
        "by_knowledge_point": dict(by_kp),
    }
