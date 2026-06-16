"""作文 AI 精修 service（D-109）。复用 LLM dev-mock；会员闸门 Pro月3次/ProMax不限。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import AppError
from app.models.d5_learning import Essay
from app.models.d9_system import SystemConfig
from app.services import membership_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_DIMENSIONS = [("内容", 25), ("语言", 25), ("结构", 25), ("词汇", 25)]
_PRO_MONTHLY_LIMIT = 3
_MAX_ROUNDS = 5
_ESSAY_TEMPLATES_KEY = "essay_templates"
_PRO_SAMPLE_LIMIT = 2

_SYSTEM_PROMPT = (
    "你是专业英语作文批改老师。请对学生作文从内容/语言/结构/词汇四个维度各 25 分打分，"
    "逐处指出问题（原文片段、修改建议、类型[语法/表达/词汇]、说明），并给出整体优化版本。"
    "只返回 JSON，键：scores(list of {dimension,score,full})、total(int)、"
    "issues(list of {original,suggestion,type,color,explanation})、polished_text(str)。"
    "颜色规则：语法=red，表达=yellow，词汇=blue。"
)


async def _monthly_count(db: AsyncSession, student_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    month_start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=timezone.utc)
    return (await db.execute(
        select(func.count()).select_from(Essay).where(
            Essay.student_id == student_id,
            Essay.created_at >= month_start,
        )
    )).scalar_one()


async def _grade(*, original_text: str, essay_type: str | None) -> dict:
    if is_llm_dev_mode():
        return {
            "scores": [{"dimension": d, "score": s - 3, "full": s} for d, s in _DIMENSIONS],
            "total": sum(s - 3 for _, s in _DIMENSIONS),
            "issues": [{
                "original": "very good", "suggestion": "excellent", "type": "词汇",
                "color": "blue", "explanation": "将 'very good' 替换为 'excellent' 更符合书面表达。",
            }],
            "polished_text": original_text + "\n\n[AI 优化版 - dev mock]",
        }
    prompt = f"作文题型：{essay_type or '未指定'}\n作文原文：\n{original_text}"
    try:
        resp = await chat_completion(
            system_prompt=_SYSTEM_PROMPT, user_prompt=prompt, max_tokens=2048)
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用，请稍后重试（{exc}）") from exc
    try:
        return json.loads((resp.choices[0].message.content or "").strip())
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI作文批改返回格式异常") from exc


async def polish_essay(
    db: AsyncSession, *, student_id: uuid.UUID, original_text: str,
    title: str | None = None, essay_type: str | None = None,
    wrong_question_id: uuid.UUID | None = None,
) -> Essay:
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=student_id, key="essay.polish",
        message="作文精修为 Pro/ProMax 专属功能（Pro 每月3次），请升级会员")
    # §5.6 内容审核：学生提交作文先过敏感词过滤，命中 block 词直接阻断
    from app.services import content_filter_service
    await content_filter_service.assert_clean(db, original_text)
    result = await _grade(original_text=original_text, essay_type=essay_type)
    essay = Essay(
        id=uuid.uuid4(), student_id=student_id, wrong_question_id=wrong_question_id,
        original_text=original_text, polished_text=result["polished_text"],
        dimensions={
            "scores": result["scores"], "total": result["total"],
            "issues": result["issues"], "title": title, "essay_type": essay_type,
        },
        round_count=1, status="completed",
    )
    db.add(essay)
    await db.flush()
    await entitlement_service.consume(db, user_id=student_id, key="essay.polish")
    return essay


async def repolish_essay(
    db: AsyncSession, *, student_id: uuid.UUID, essay_id: uuid.UUID, revised_text: str,
) -> Essay:
    essay = await get_essay(db, student_id=student_id, essay_id=essay_id)
    if essay is None:
        raise AppError(code=404, message="作文记录不存在")
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=student_id, key="essay.rewrite",
        message="多轮迭代精修为 ProMax 专属功能")
    dim = dict(essay.dimensions or {})
    rounds = list(dim.get("rounds") or [])
    if not rounds:
        rounds = [{
            "text": essay.original_text,
            "scores": dim.get("scores", []), "total": dim.get("total", 0),
            "issues": dim.get("issues", []), "polished_text": essay.polished_text,
        }]
    if len(rounds) >= _MAX_ROUNDS:
        raise AppError(code=403, message=f"已达最多 {_MAX_ROUNDS} 轮精修上限")
    result = await _grade(original_text=revised_text, essay_type=dim.get("essay_type"))
    rounds.append({
        "text": revised_text, "scores": result["scores"], "total": result["total"],
        "issues": result["issues"], "polished_text": result["polished_text"],
    })
    dim["rounds"] = rounds
    dim["scores"] = result["scores"]
    dim["total"] = result["total"]
    dim["issues"] = result["issues"]
    essay.dimensions = dim
    essay.polished_text = result["polished_text"]
    essay.round_count = len(rounds)
    flag_modified(essay, "dimensions")
    await db.flush()
    return essay


# ── 应试训练（E1：审题 + 按档诊断 + 错因本）────────────────────────────────────
_DIAG_DIMS = [("内容", 40), ("语言", 40), ("结构", 20)]


async def list_prompts(
    db: AsyncSession, *, stage: str | None = None, genre: str | None = None, limit: int = 50,
) -> list:
    from app.models.d5_learning import EssayPrompt
    q = select(EssayPrompt)
    if stage:
        q = q.where(EssayPrompt.stage == stage)
    if genre:
        q = q.where(EssayPrompt.genre == genre)
    rows = (await db.execute(q.order_by(EssayPrompt.created_at.desc()).limit(limit))).scalars().all()
    return list(rows)


async def get_prompt(db: AsyncSession, *, prompt_id: uuid.UUID):
    from app.models.d5_learning import EssayPrompt
    return (await db.execute(select(EssayPrompt).where(EssayPrompt.id == prompt_id))).scalar_one_or_none()


async def analyze_prompt(
    db: AsyncSession, *, prompt_id: uuid.UUID | None = None, text: str | None = None,
) -> dict:
    """审题助手：题库题直接返回要点/人称/时态/词数；自定义题用 AI 抽取。"""
    if prompt_id:
        p = await get_prompt(db, prompt_id=prompt_id)
        if p is None:
            raise AppError(code=404, message="题目不存在")
        return {
            "title": p.title, "genre": p.genre, "scenario": p.scenario,
            "required_points": p.required_points or [],
            "person": p.person, "tense": p.tense,
            "word_min": p.word_min, "word_max": p.word_max,
        }
    scenario = (text or "").strip()
    if not scenario:
        raise AppError(code=400, message="请输入作文题目或情景")
    if is_llm_dev_mode():
        return {"title": scenario[:20], "genre": "未指定", "scenario": scenario,
                "required_points": ["要点1", "要点2", "要点3"],
                "person": "第一人称", "tense": "一般现在时", "word_min": 80, "word_max": 120}
    sys = (
        "你是英语写作审题助手。根据给定的作文题目/情景，提取写作要点清单与写作规范。"
        "只返回 JSON，键：genre(体裁,中文)、required_points(必答要点,中文字符串数组)、"
        "person(人称)、tense(主要时态)、word_min(int)、word_max(int)。要点要覆盖题目所有得分点，简洁。"
    )
    try:
        resp = await chat_completion(system_prompt=sys, user_prompt=f"题目/情景：\n{scenario}",
                                     max_tokens=600, response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        raise AppError(code=502, message=f"AI 审题失败：{exc}") from exc
    return {
        "title": scenario[:30], "genre": str(data.get("genre") or "未指定"), "scenario": scenario,
        "required_points": [str(x) for x in (data.get("required_points") or [])],
        "person": data.get("person"), "tense": data.get("tense"),
        "word_min": data.get("word_min"), "word_max": data.get("word_max"),
    }


def _diag_system(stage: str) -> str:
    level = "高考" if stage == "senior" else ("中考" if stage == "junior" else "小学")
    return (
        f"你是资深{level}英语书面表达阅卷老师。请严格对照评分标准为学生作文打分，目标是帮助学生在考试中提分。"
        "从三个维度评分：内容(满分40，要点是否齐全、是否切题)、语言(满分40，语法/词汇/句式准确与丰富)、"
        "结构(满分20，逻辑与衔接)。每个维度给档次(优秀/良好/合格/待提高)。"
        "【关键】(1) 逐条核对给定的必答要点，标出每个要点是否答到; "
        "(2) 给每个维度一条具体的“升档建议”(差一句什么样的句子/改什么就能上一档); "
        "(3) 逐处指出错误并归类(类型限定：时态/主谓一致/中式表达/拼写/搭配/用词/标点)。"
        "只返回 JSON，键：scores(list of {dimension,score,full,band})、total(int)、total_full(int)、"
        "overall_band(str)、missing_points(list of {point,covered:boolean})、"
        "upgrade_tips(list of {dimension,tip})、"
        "issues(list of {original,suggestion,type,explanation})、model_better(str:可选的更好范例段落)。"
    )


def _mock_diagnose(required_points: list) -> dict:
    return {
        "scores": [{"dimension": d, "score": f - 8, "full": f, "band": "合格"} for d, f in _DIAG_DIMS],
        "total": sum(f - 8 for _, f in _DIAG_DIMS), "total_full": 100, "overall_band": "合格",
        "missing_points": [{"point": str(p), "covered": i % 2 == 0} for i, p in enumerate(required_points or ["要点1"])],
        "upgrade_tips": [{"dimension": d, "tip": f"{d}：再补一个高级句式即可升档（dev-mock）"} for d, _ in _DIAG_DIMS],
        "issues": [{"original": "I very like", "suggestion": "I like ... very much",
                    "type": "中式表达", "explanation": "very 不能直接修饰动词。"}],
        "model_better": "",
    }


async def diagnose_essay(
    db: AsyncSession, *, student_id: uuid.UUID, draft_text: str,
    prompt_id: uuid.UUID | None = None, prompt_text: str | None = None,
    stage: str = "junior", timed_seconds: int | None = None,
) -> Essay:
    """按档诊断：权益门禁(essay.diagnose, Pro月3/ProMax不限)。漏点检测 + 升档建议 + 错因沉淀。"""
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=student_id, key="essay.diagnose",
        message="作文诊断为 Pro/ProMax 专属功能，请升级会员")

    info = await analyze_prompt(db, prompt_id=prompt_id, text=prompt_text)
    required = info.get("required_points") or []

    if is_llm_dev_mode():
        data = _mock_diagnose(required)
    else:
        usr = (f"作文体裁：{info.get('genre')}\n题目/情景：{info.get('scenario')}\n"
               f"必答要点：{json.dumps(required, ensure_ascii=False)}\n"
               f"要求人称：{info.get('person')}，时态：{info.get('tense')}，"
               f"词数：{info.get('word_min')}-{info.get('word_max')}\n\n学生作文：\n{draft_text}")
        try:
            resp = await chat_completion(system_prompt=_diag_system(stage), user_prompt=usr,
                                         max_tokens=2048, response_format={"type": "json_object"})
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001
            raise AppError(code=502, message=f"AI 诊断失败：{exc}") from exc

    essay = Essay(
        id=uuid.uuid4(), student_id=student_id, original_text=draft_text,
        polished_text=data.get("model_better") or "",
        dimensions={
            "kind": "exam_diagnose", "title": info.get("title"), "genre": info.get("genre"),
            "stage": stage, "prompt_id": str(prompt_id) if prompt_id else None,
            "required_points": required, "timed_seconds": timed_seconds,
            "scores": data.get("scores", []), "total": data.get("total", 0),
            "total_full": data.get("total_full", 100), "overall_band": data.get("overall_band", ""),
            "missing_points": data.get("missing_points", []),
            "upgrade_tips": data.get("upgrade_tips", []),
            "issues": data.get("issues", []),
        },
        round_count=1, status="completed",
    )
    db.add(essay)
    await db.flush()
    from app.models.d5_learning import EssayErrorLog
    for it in (data.get("issues") or []):
        if isinstance(it, dict) and it.get("type"):
            db.add(EssayErrorLog(
                id=uuid.uuid4(), student_id=student_id, essay_id=essay.id,
                type=str(it.get("type"))[:24], original=str(it.get("original") or "")[:500],
                suggestion=str(it.get("suggestion") or "")[:500]))
    await db.flush()
    await entitlement_service.consume(db, user_id=student_id, key="essay.diagnose")
    return essay


async def error_log_summary(db: AsyncSession, *, student_id: uuid.UUID, limit: int = 60) -> dict:
    """写作错因本：按类型聚合 + 最近明细。"""
    from app.models.d5_learning import EssayErrorLog
    rows = (await db.execute(
        select(EssayErrorLog).where(EssayErrorLog.student_id == student_id)
        .order_by(EssayErrorLog.created_at.desc()).limit(limit)
    )).scalars().all()
    from collections import Counter
    cnt: Counter = Counter(r.type for r in rows)
    return {
        "by_type": [{"type": t, "count": c} for t, c in cnt.most_common()],
        "items": [{"type": r.type, "original": r.original, "suggestion": r.suggestion,
                   "created_at": r.created_at.isoformat()} for r in rows],
    }


async def get_essay(db: AsyncSession, *, student_id: uuid.UUID, essay_id: uuid.UUID) -> Essay | None:
    return (await db.execute(
        select(Essay).where(Essay.id == essay_id, Essay.student_id == student_id)
    )).scalar_one_or_none()


async def list_essays(db: AsyncSession, *, student_id: uuid.UUID) -> list[Essay]:
    return list((await db.execute(
        select(Essay).where(Essay.student_id == student_id).order_by(Essay.created_at.desc())
    )).scalars().all())


_TEMPLATES_BY_TYPE = {
    "话题作文": {
        "template": "开头：亮明观点（In my opinion, ...）。中间：2-3 个理由 + 例证（Firstly... Secondly... For example...）。结尾：总结升华（In conclusion, ...）。",
        "samples": [
            "Many students think... I believe... Firstly,... Secondly,... In conclusion,...",
            "With the development of technology,... On the one hand,... On the other hand,...",
            "It is often said that... From my perspective,... Therefore,...",
        ],
    },
    "书信作文": {
        "template": "称呼（Dear ...）→ 自我介绍/写信目的 → 主体（分点说明）→ 结尾礼貌用语（Looking forward to your reply）→ 落款（Yours, XXX）。",
        "samples": [
            "Dear Tom, I'm writing to tell you about... Looking forward to your reply. Yours, Li Hua",
            "Dear Sir or Madam, I am writing to apply for... I would appreciate it if... Yours sincerely, ...",
            "Dear friend, How is everything going? I'd like to share... Best wishes, ...",
        ],
    },
    "图片作文": {
        "template": "描述图片内容（The picture shows...）→ 分析现象/原因 → 表达观点或建议（We should...）。",
        "samples": [
            "The picture shows... This reminds us that... We should...",
            "As is shown in the picture,... The reason is that... Therefore,...",
            "Looking at the picture, we can see... It tells us... In my view,...",
        ],
    },
}

_DEFAULT_TEMPLATE = {
    "template": "三段式：开头点题 → 主体分点论述 + 例证 → 结尾总结。多用连接词（Firstly/However/In conclusion），避免中式表达。",
    "samples": [
        "In my opinion,... Firstly,... Secondly,... In conclusion,...",
        "There is no doubt that... For one thing,... For another,... Therefore,...",
        "As far as I am concerned,... On the one hand,... On the other hand,...",
    ],
}


def get_templates(essay_type: str | None) -> dict:
    return _TEMPLATES_BY_TYPE.get(essay_type or "", _DEFAULT_TEMPLATE)


async def get_configured_templates(
    db: AsyncSession, essay_type: str | None, tier: str | None = None,
) -> dict:
    """读 system_configs.essay_templates；命中题型→用之，否则 _default，再否则回落内置。
    tier 非 promax 且非 None → 范文 samples 截断至 _PRO_SAMPLE_LIMIT（档位差异化，D-112）。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    data: dict | None = None
    if cfg is not None and isinstance(cfg.value, dict):
        conf = cfg.value
        if essay_type and essay_type in conf:
            data = conf[essay_type]
        elif "_default" in conf:
            data = conf["_default"]
    if data is None:
        data = get_templates(essay_type)
    if tier is not None and tier != "promax":
        return {**data, "samples": list(data.get("samples", []))[:_PRO_SAMPLE_LIMIT]}
    return data


async def get_all_templates_config(db: AsyncSession) -> dict:
    """admin 读：当前完整配置；未配则返回内置（含 _default）。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is not None and isinstance(cfg.value, dict):
        return cfg.value
    return {**_TEMPLATES_BY_TYPE, "_default": _DEFAULT_TEMPLATE}


async def set_all_templates_config(db: AsyncSession, *, value: dict, admin_id: uuid.UUID) -> dict:
    """admin 写：upsert system_configs.essay_templates。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        cfg = SystemConfig(id=uuid.uuid4(), key=_ESSAY_TEMPLATES_KEY, value=value,
                           description="作文精修模板/范文（Module 5A）", updated_by=admin_id)
        db.add(cfg)
    else:
        cfg.value = value
        cfg.updated_by = admin_id
    await db.flush()
    return cfg.value


async def get_progress(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    rows = await list_essays(db, student_id=student_id)  # 倒序
    essays = list(reversed(rows))  # 时间正序
    total_essays = len(essays)
    totals = [(e.dimensions or {}).get("total", 0) for e in essays]
    avg_total = round(sum(totals) / total_essays, 1) if total_essays else 0
    trend = [{"date": e.created_at.date().isoformat(), "total": (e.dimensions or {}).get("total", 0)} for e in essays]
    dim_sum: dict[str, list[int]] = {}
    for e in essays:
        for s in (e.dimensions or {}).get("scores", []):
            dim_sum.setdefault(s["dimension"], []).append(s["score"])
    dimension_avg = [{"dimension": d, "avg": round(sum(v) / len(v), 1)} for d, v in dim_sum.items()]
    return {
        "total_essays": total_essays,
        "avg_total": avg_total,
        "trend": trend,
        "dimension_avg": dimension_avg,
    }
