"""长难句 学生端 API（L2）:列长难句 / 取解析(主干分层/译文/句法点跳 R6 资源)。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    LongSentenceItem, LongSentenceListOut, LongSentenceDetailOut, LongSentenceNodeRef,
    VerifyTypesOut, VerifyQuestionOut, VerifySubmitIn, VerifySubmitOut,
    ComprehensionProbe, ComprehensionOut, ComprehensionSubmitIn,
    ComprehensionProbeResult, ComprehensionResultOut,
    TranslateCheckIn, TranslateCheckOut, TranslateDim,
    TransferItem, TransferOut, TransferSubmitIn, TransferResultOut,
)
from app.services import long_sentence_service as lss
from app.services import tts_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/long-sentences", tags=["long-sentences"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


async def _record_ls_comprehension(db: AsyncSession, student_id: uuid.UUID,
                                   ls_id: uuid.UUID, passed) -> None:
    """理解探针(释义/短翻译)passed 即句级「≥半数」聚合信号 → 落该句「理解」维练习衍生。
    未过=记薄弱(错次+1、连对归0);过=推进连对(达2清除)。"""
    if passed is None:
        return
    from app.services import wrong_center_service as wcs
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or not getattr(ls, "text", None):
        return
    await wcs.record_ls_practice(
        db, student_id=student_id, sentence=ls.text, dim="comprehension",
        correct=bool(passed), ref_id=ls_id)
    await db.commit()


@router.get("", response_model=BaseResponse[LongSentenceListOut])
async def list_long_sentences(
    db: DbDep, current_user: UserDep, node_id: uuid.UUID | None = None, limit: int = 50,
):
    """已发布长难句:平台共享(可按句法 node 过滤)+ 本人个人长难句(student_long_sentence)。"""
    rows = await lss.list_published(db, node_id=node_id, owner_id=current_user.id, limit=limit)
    fav = await lss.favorited_ids(db, user_id=current_user.id, ls_ids=[r.id for r in rows])
    items = [LongSentenceItem(
        id=r.id, text=r.text, source_kind=r.source_kind,
        syntax_points=(r.analysis_json or {}).get("syntax_points", []),
        favorited=r.id in fav,
    ) for r in rows]
    if node_id is None:   # 个人长难句不挂句法 node,不参与 node 过滤
        for s in await lss.list_student_published(db, owner_id=current_user.id, limit=limit):
            items.append(LongSentenceItem(
                id=s.id, text=s.text, source_kind="uploaded",
                syntax_points=(s.analysis_json or {}).get("syntax_points", []), favorited=False))
    return make_ok(LongSentenceListOut(total=len(items), items=items))


@router.post("/study-aids", response_model=BaseResponse[dict])
async def study_aids(
    db: DbDep, current_user: UserDep,
    sentence: Annotated[str, Body(..., embed=True, min_length=1, max_length=600)],
    paper_id: Annotated[uuid.UUID | None, Body(embed=True)] = None,
):
    """长难句学习页交互素材(一次全给):解析 + 成分/语法选择题 + 重点词 + 各项已加入/已练回显。"""
    return make_ok(await lss.sentence_study_aids(
        db, text=sentence, student_id=current_user.id, paper_id=paper_id))


@router.post("/add-grammar", response_model=BaseResponse[dict])
async def add_grammar_target(
    db: DbDep, current_user: UserDep,
    node_id: Annotated[uuid.UUID, Body(..., embed=True)],
    paper_id: Annotated[uuid.UUID | None, Body(embed=True)] = None,
):
    """把一个语法结构(node)加入作业精讲·语法(按来源卷归组)。长难句学习页「查看讲解」时调。"""
    from app.services import learning_plan_service
    n = await learning_plan_service.add_targets(
        db, student_id=current_user.id, node_ids=[node_id],
        source="long_sentence_quiz", source_paper_id=paper_id)
    return make_ok({"added": n})


@router.post("/grammar-answer", response_model=BaseResponse[dict])
async def grammar_answer(
    db: DbDep, current_user: UserDep,
    gp_key: Annotated[str, Body(..., embed=True, max_length=64)],
    label: Annotated[str, Body(..., embed=True, max_length=120)],
    correct: Annotated[bool, Body(..., embed=True)],
    node_id: Annotated[uuid.UUID | None, Body(embed=True)] = None,
    sentence: Annotated[str | None, Body(embed=True)] = None,
    kind: Annotated[str | None, Body(embed=True)] = None,
):
    """记一次成分/语法选择题作答(累计正确率)。传 sentence+kind(component|grammar)则同时落
    「长难句薄弱」练习衍生(错→句·维;对→连对+1达2清除)。返回该语法点 {correct,total}。"""
    from app.services import grammar_quiz_stat_service as gqs, wrong_center_service as wcs
    r = await gqs.record(db, student_id=current_user.id, gp_key=gp_key,
                         label=label, correct=correct, node_id=node_id)
    if sentence and kind in ("component", "grammar"):
        await wcs.record_ls_practice(
            db, student_id=current_user.id, sentence=sentence, dim=kind, correct=correct)
        await db.commit()
    return make_ok(r)


@router.get("/next", response_model=BaseResponse[dict])
async def next_sentence(db: DbDep, current_user: UserDep, exclude: str = ""):
    """自适应推荐下一句:按学生水平 θ(年级估)选难度贴近的、优先薄弱句法点 + 课程对齐 + 个人材料。
    exclude: 逗号分隔的已学 id,避免重复。返回 {item, theta, target, weak_hit}。"""
    ex = []
    for x in (exclude or "").split(","):
        x = x.strip()
        if x:
            try:
                ex.append(uuid.UUID(x))
            except ValueError:
                pass
    r = await lss.recommend_next(db, user=current_user, exclude_ids=ex)
    best = r["best"]
    tier = lss.ls_tier(r["theta"])
    if best is None:
        return make_ok({"item": None, "theta": round(r["theta"]), "target": round(r["target"]),
                        "weak_hit": False, "tier": tier})
    kind, row = best
    item = LongSentenceItem(
        id=row.id, text=row.text,
        source_kind=row.source_kind if kind == "platform" else "uploaded",
        syntax_points=(row.analysis_json or {}).get("syntax_points", []),
        favorited=(row.id in await lss.favorited_ids(db, user_id=current_user.id, ls_ids=[row.id])) if kind == "platform" else False,
        difficulty=row.difficulty,
    )
    return make_ok({"item": item.model_dump(mode="json"), "theta": round(r["theta"]),
                    "target": round(r["target"]), "weak_hit": r["weak_hit"], "tier": tier,
                    "review": r.get("review", False)})


@router.post("/feedback", response_model=BaseResponse[dict])
async def submit_feedback(db: DbDep, current_user: UserDep, rating: str = Body(...),
                          ls_id: str | None = Body(None), is_student: bool = Body(False)):
    """难度反馈:校准 θ + 维护间隔重现。rating: easy|ok|hard;ls_id=刚评价的句子(用于复习排期)。"""
    if rating not in ("easy", "ok", "hard"):
        raise AppError(code=400, message="rating 须为 easy|ok|hard")
    theta = await lss.apply_feedback(db, current_user, rating=rating)
    if ls_id:
        try:
            await lss.record_review(db, current_user, ls_id=uuid.UUID(ls_id), is_student=bool(is_student), rating=rating)
        except ValueError:
            pass
    return make_ok({"theta": round(theta), "target": round(min(95.0, theta + 5)), "tier": lss.ls_tier(theta)})


@router.get("/{ls_id}/comprehension", response_model=BaseResponse[ComprehensionOut])
async def get_comprehension(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """理解检测题面(双探针:点主干 + 释义/意义),不含答案。读完即做,过关才算学会这句。"""
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    probes = lss.comprehension_probes(ls)
    return make_ok(ComprehensionOut(probes=[
        ComprehensionProbe(key=p["key"], type=p["type"], prompt=p["prompt"], options=p["options"])
        for p in probes]))


@router.post("/{ls_id}/comprehension", response_model=BaseResponse[ComprehensionResultOut])
async def submit_comprehension(ls_id: uuid.UUID, body: ComprehensionSubmitIn,
                               db: DbDep, current_user: UserDep):
    """提交理解检测:双探针判分→单句理解分→θ 实测校准→回写句法掌握+间隔重现。
    passed=True 才算「学会这句」;否则进复习盒,稍后再推。"""
    res = await lss.submit_comprehension(db, user=current_user, ls_id=ls_id,
                                         answers=body.answers, self_rating=body.self_rating)
    await _record_ls_comprehension(db, current_user.id, ls_id, res.get("passed"))
    return make_ok(ComprehensionResultOut(
        passed=res["passed"],
        probes=[ComprehensionProbeResult(**p) for p in res["probes"]],
        theta=round(res["theta"], 1), target=round(res["target"], 1), tier=res["tier"]))


@router.post("/{ls_id}/translate-check", response_model=BaseResponse[TranslateCheckOut])
async def submit_translate_check(ls_id: uuid.UUID, body: TranslateCheckIn,
                                 db: DbDep, current_user: UserDep):
    """短翻译产出项(进阶·检验输出):维度 rubric 评分(命题/逻辑/修饰/主干 各 0-2)+ 达标 θ 上调。"""
    res = await lss.submit_translation(db, user=current_user, ls_id=ls_id, answer=body.answer)
    await _record_ls_comprehension(db, current_user.id, ls_id, res.get("passed"))
    return make_ok(TranslateCheckOut(
        dimensions=[TranslateDim(**d) for d in res["dimensions"]],
        total=res["total"], max=res["max"], passed=res["passed"], feedback=res.get("feedback"),
        theta=round(res["theta"], 1), target=round(res["target"], 1), tier=res["tier"]))


@router.get("/{ls_id}/transfer", response_model=BaseResponse[TransferOut])
async def get_transfer(ls_id: uuid.UUID, db: DbDep, current_user: UserDep, exclude: str = ""):
    """迁移挑战:按句法结构检索一句「同结构、新内容」的句子 + 其理解检测题。
    exclude=逗号分隔已学 id。找不到→item 为空。"""
    origin, _ = await lss.get_detail(db, ls_id=ls_id)
    if origin is None or origin.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    ex = []
    for x in (exclude or "").split(","):
        x = x.strip()
        if x:
            try:
                ex.append(uuid.UUID(x))
            except ValueError:
                pass
    found = await lss.find_transfer_sentence(db, origin=origin, user=current_user, exclude_ids=ex)
    if found is None:
        return make_ok(TransferOut(item=None, shared=[], probes=[]))
    t, shared = found
    probes = lss.comprehension_probes(t)
    return make_ok(TransferOut(
        item=TransferItem(id=t.id, text=t.text, difficulty=t.difficulty),
        shared=shared,
        probes=[ComprehensionProbe(key=p["key"], type=p["type"], prompt=p["prompt"], options=p["options"])
                for p in probes]))


@router.post("/transfer-for-text", response_model=BaseResponse[TransferOut])
async def transfer_for_text(
    db: DbDep, current_user: UserDep,
    sentence: Annotated[str, Body(..., embed=True, min_length=1, max_length=600)],
    exclude: Annotated[list[str] | None, Body(embed=True)] = None,
):
    """精读闯关·练同型句:用**任意句子**(不必在已发布池内)的结构,找一句同结构的已发布新句 + 理解探针。
    原句只作结构种子(合成 origin,不落库);判分复用现有 comprehension(迁移句本身是已发布 ls)。"""
    from app.models.d20_long_sentence import LongSentence
    analysis = await lss.analyze_sentence_cached(db, sentence, with_paraphrase=False)
    if not analysis or not analysis.get("syntax_points"):
        return make_ok(TransferOut(item=None, shared=[], probes=[]))
    ex: list[uuid.UUID] = []
    for x in (exclude or []):
        try:
            ex.append(uuid.UUID(str(x)))
        except (ValueError, TypeError):
            pass
    origin = LongSentence(id=uuid.uuid4(), text=sentence, analysis_json=analysis, difficulty=None)
    found = await lss.find_transfer_sentence(db, origin=origin, user=current_user, exclude_ids=ex)
    if found is None:
        return make_ok(TransferOut(item=None, shared=[], probes=[]))
    t, shared = found
    probes = lss.comprehension_probes(t)
    return make_ok(TransferOut(
        item=TransferItem(id=t.id, text=t.text, difficulty=t.difficulty),
        shared=shared,
        probes=[ComprehensionProbe(key=p["key"], type=p["type"], prompt=p["prompt"], options=p["options"])
                for p in probes]))


@router.post("/{ls_id}/transfer-submit", response_model=BaseResponse[TransferResultOut])
async def submit_transfer_api(ls_id: uuid.UUID, body: TransferSubmitIn, db: DbDep, current_user: UserDep):
    """提交迁移句的理解检测:判分→结论(真掌握/疑似记住原题)。原句=ls_id,迁移句=body.transfer_id。"""
    res = await lss.submit_transfer(db, user=current_user, origin_id=ls_id,
                                    transfer_id=body.transfer_id, answers=body.answers)
    return make_ok(TransferResultOut(
        passed=res["passed"], verdict=res["verdict"], shared=res["shared"],
        probes=[ComprehensionProbeResult(**p) for p in res["probes"]],
        theta=round(res["theta"], 1), target=round(res["target"], 1), tier=res["tier"]))


@router.get("/{ls_id}/vocab-hits", response_model=BaseResponse[dict])
async def get_vocab_hits(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """R9.4 生词复现:本句里命中该生词单中「未掌握」的词,供顺势轻测。"""
    from app.services import vocab_probe_service as vps
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    text = ls.text if ls else None
    if not text:
        s = await _student_one(db, ls_id, current_user.id)
        text = s.text if s else None
    hits = await vps.incidental_hits(db, student_id=current_user.id, text=text or "") if text else []
    return make_ok({"hits": hits})


async def _student_one(db, ls_id, owner_id):
    from app.models.d20_long_sentence import StudentLongSentence
    s = await db.get(StudentLongSentence, ls_id)
    if s is not None and s.status == "published" and s.owner_id == owner_id:
        return s
    return None


@router.get("/{ls_id}", response_model=BaseResponse[LongSentenceDetailOut])
async def get_long_sentence(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """长难句解析详情。平台库优先;否则查本人个人长难句。"""
    ls, nodes = await lss.get_detail(db, ls_id=ls_id)
    if ls is not None and ls.status == "published":
        favorited = await lss.is_favorited(db, user_id=current_user.id, ls_id=ls_id)
        return make_ok(LongSentenceDetailOut(
            id=ls.id, text=ls.text, source_kind=ls.source_kind, analysis=ls.analysis_json,
            audio_url=ls.audio_url, favorited=favorited,
            nodes=[LongSentenceNodeRef(**n) for n in nodes]))
    s = await _student_one(db, ls_id, current_user.id)
    if s is not None:
        return make_ok(LongSentenceDetailOut(
            id=s.id, text=s.text, source_kind="uploaded", analysis=s.analysis_json,
            audio_url=None, favorited=False, nodes=[]))
    raise AppError(code=404, message="长难句不存在或未发布")


@router.post("/{ls_id}/favorite", response_model=BaseResponse[dict])
async def favorite(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """收藏长难句(仅平台库支持收藏)。"""
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None:
        return make_ok({"favorited": False})
    on = await lss.set_favorite(db, user_id=current_user.id, ls_id=ls_id, on=True)
    return make_ok({"favorited": on})


@router.delete("/{ls_id}/favorite", response_model=BaseResponse[dict])
async def unfavorite(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """取消收藏长难句。"""
    on = await lss.set_favorite(db, user_id=current_user.id, ls_id=ls_id, on=False)
    return make_ok({"favorited": on})


@router.post("/{ls_id}/audio", response_model=BaseResponse[dict])
async def get_audio(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """听原句:返回句子音频直链。平台句库里有 audio_url 直接返回,否则合成→存 COS→回填;
    个人长难句不回填库,直接返回空 url 让前端走 /tts/speak 流式。"""
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is not None and ls.status == "published":
        if ls.audio_url:
            return make_ok({"url": ls.audio_url})
        speed = await tts_service.speed_for_stage_db(db, "junior")
        url = await tts_service.get_or_create_audio_url(ls.text, speed=speed)
        if url:
            ls.audio_url = url
            await db.commit()
        return make_ok({"url": url or ""})
    s = await _student_one(db, ls_id, current_user.id)
    if s is not None:
        return make_ok({"url": ""})   # 前端回退流式
    raise AppError(code=404, message="长难句不存在或未发布")


@router.get("/{ls_id}/verify-types", response_model=BaseResponse[VerifyTypesOut])
async def get_verify_types(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """该长难句可用的验证题型(后台开放且本期可用),学生自选其一作答。"""
    types = await lss.enabled_verify_types(db)
    return make_ok(VerifyTypesOut(types=types))


@router.get("/{ls_id}/verify", response_model=BaseResponse[VerifyQuestionOut])
async def get_verify_question(ls_id: uuid.UUID, type: str, db: DbDep, current_user: UserDep):
    """取一道验证题(不含答案)。type 须在已开放题型内。"""
    if type not in await lss.enabled_verify_types(db):
        raise AppError(code=400, message="该验证题型未开放")
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    q = lss.build_verify(ls, type)
    if q is None:
        raise AppError(code=400, message="该句无法生成此题型")
    return make_ok(VerifyQuestionOut(type=q["type"], prompt=q["prompt"], options=q["options"]))


@router.post("/{ls_id}/verify", response_model=BaseResponse[VerifySubmitOut])
async def submit_verify_answer(ls_id: uuid.UUID, body: VerifySubmitIn, db: DbDep, current_user: UserDep):
    """提交验证答案:判分 + 回写句法 node + 错题收口 + 达标判掌握。"""
    res = await lss.submit_verify(
        db, student_id=current_user.id, ls_id=ls_id, verify_type=body.type, answer=body.answer)
    await db.commit()
    return make_ok(VerifySubmitOut(**res))
