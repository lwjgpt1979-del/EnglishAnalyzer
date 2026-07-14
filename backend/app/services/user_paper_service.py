"""整卷上传 service（D-089 / M4）：建卷 / 列表 / 详情 / 后台 OCR 拆题管线。

后台管线沿用 ocr.py 已验证的「BackgroundTasks + 独立 async_session_factory」模式：
管线内部开独立 session 提交，避免与请求 session 串扰。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.schemas.user_papers import (
    UserPaperDetailOut,
    UserPaperOut,
    UserPaperQuestionOut,
)


def _is_wrong(student_answer: str | None, correct_answer: str | None) -> bool:
    """学生答案与正确答案都存在且归一化后不同 → 判错；否则 False（无法判定不算错）。"""
    if not student_answer or not correct_answer:
        return False
    return student_answer.strip().lower() != correct_answer.strip().lower()


def _section_type(label: str | None) -> str | None:
    """由原卷大题名推板块类型键(供前端图标/分组;识别不到留 None)。"""
    l = label or ""
    if "完形" in l or "完型" in l:
        return "cloze"
    if "阅读" in l or "任务型" in l:
        return "reading"
    if "单项" in l or "单选" in l or "选择" in l:
        return "mcq"
    if "书面" in l or "作文" in l or "写作" in l:
        return "writing"
    if "词汇" in l or "首字母" in l or "短文填空" in l or "填空" in l:
        return "fill"
    if "听力" in l:
        return "listening"
    return None


# 原卷没识别到大题头时,按「题型 + 有无短文」推一个建议大题名(前端标「建议」,学生可改)
_SUGGEST_BY_TYPE = {
    "单选": "单项选择", "阅读": "阅读理解", "完型": "完形填空",
    "填空": "词汇/短文填空", "写作": "书面表达", "判断": "判断", "连线": "连线",
}


def _suggest_section_label(question_type: str | None, has_passage: bool) -> str:
    if has_passage:
        return "阅读理解"                      # 有短文优先判阅读
    return _SUGGEST_BY_TYPE.get(question_type or "", "其它")


def _label_of(pq) -> tuple[str, bool]:
    """返回(大题名, 是否 AI 建议)。原卷有大题名→用它(非建议);否则按题型推(建议)。"""
    raw = (pq.section or "").strip()
    if raw:
        return raw, False
    return _suggest_section_label(pq.question_type, bool(pq.passage or pq.block_key)), True


async def _images_hash(source_image_urls: list[str]) -> str | None:
    """按顺序抓图片字节 → 合并 md5(同一张图重复上传去重)。任一抓取失败 → None(不拦截,照常解析)。"""
    import hashlib
    import httpx
    from app.services import upload_service
    h = hashlib.md5()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for url in source_image_urls:
                r = await client.get(upload_service.make_fetch_url(url))
                r.raise_for_status()
                h.update(r.content)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


async def _extract_paper_name(printed_text: str) -> str:
    """从作业文字里提取一个简短标题名(印在卷上的标题/年级科目/单元测验名);提不出返回空。
    关推理(结构化抽取,规格明确);失败返回空,交由调用方走「年月日作业X」兜底。"""
    text = (printed_text or "").strip()
    if not text:
        return ""
    from app.services.llm_provider import chat_completion, fast_model
    sys = ("你从一份英语作业/试卷的文字里提取它的**标题名称**——如印在卷子上的标题、"
           "年级+科目、单元测验名等。只输出这个简短名称(中文优先,≤12字),"
           "没有明显标题就输出空字符串。不要解释、不要标点包裹。")
    user = f"作业文字(节选):\n{text[:800]}\n\n输出标题名称(没有则留空):"
    try:
        resp = await chat_completion(system_prompt=sys, user_prompt=user, max_tokens=40,
                                     model=fast_model(), disable_thinking=True, feature="paper_title")
        name = (resp.choices[0].message.content or "").strip().strip('“”"\'　 ')
    except Exception:  # noqa: BLE001
        return ""
    if not name or len(name) > 20 or name in ("空", "无", "None", "none", "N/A"):
        return ""
    return name


async def _gen_paper_title(db: AsyncSession, paper: UserUploadedPaper, printed_text: str) -> str:
    """自动作业标题:能解析出名字 → 「名字 年月日」;否则「年月日作业X」(X=该生当天第几份)。
    年月日 = 上传日期(按 Asia/Shanghai)。"""
    import datetime as _dt
    from datetime import timezone as _tz
    from zoneinfo import ZoneInfo
    sh = ZoneInfo("Asia/Shanghai")
    created = paper.created_at or _dt.datetime.now(_tz.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=_tz.utc)
    local = created.astimezone(sh)
    date_s = local.strftime("%Y-%m-%d")
    name = await _extract_paper_name(printed_text)
    if name:
        return f"{name} {date_s}"
    # 兜底:年月日作业X —— X=该生当天(本地)截至本份的第几份
    day_start_utc = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(_tz.utc)
    cnt = (await db.execute(select(func.count(UserUploadedPaper.id)).where(
        UserUploadedPaper.student_id == paper.student_id,
        UserUploadedPaper.created_at >= day_start_utc,
        UserUploadedPaper.created_at <= paper.created_at))).scalar_one()
    return f"{date_s}作业{int(cnt) or 1}"


async def rename_paper(db: AsyncSession, *, paper_id: uuid.UUID,
                       student_id: uuid.UUID, title: str) -> str | None:
    """重命名作业标题(仅本人)。返回新标题;无权/不存在返回 None。"""
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    paper.title = title
    await db.commit()
    return title


async def create_paper(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    source_image_urls: list[str],
    title: str | None,
) -> tuple[UserUploadedPaper, bool]:
    """创建整卷记录，ocr_status=pending。返回 (paper, reused)。

    去重(问题1):同一学生上传**内容相同**的图片(md5 一致)时,直接复用已有卷,
    不重复解析——reused=True,调用方跳过扣费与后台管线。"""
    img_hash = await _images_hash(source_image_urls)
    if img_hash:
        existing = (await db.execute(
            select(UserUploadedPaper).where(
                UserUploadedPaper.student_id == student_id,
                UserUploadedPaper.image_hash == img_hash,
                UserUploadedPaper.ocr_status.in_(["completed", "processing", "pending"]))
            .order_by(UserUploadedPaper.created_at.desc()).limit(1))).scalar_one_or_none()
        if existing is not None:
            return existing, True

    paper = UserUploadedPaper(
        student_id=student_id,
        title=title,
        source_image_urls=source_image_urls,
        image_hash=img_hash,
        ocr_status="pending",
    )
    db.add(paper)
    await db.flush()
    await db.refresh(paper)
    return paper, False


async def run_paper_pipeline(paper_id: uuid.UUID) -> None:
    """后台任务：整卷图片 → 豆包Vision拆题 → DeepSeek KP归类 → 落库 + 台账写入（M40）。

    用独立 session（async_session_factory），与触发请求的 session 解耦。
    """
    from app.core.database import async_session_factory as _async_session_factory
    from app.services.ocr_service import OcrResult, run_ocr
    from app.services.paper_split_service import split_paper_questions
    from app.services.kp_classifier_service import classify_kps
    from app.services.kp_mastery_service import upsert_mastery

    async with _async_session_factory() as db:
        paper: UserUploadedPaper | None = await db.get(UserUploadedPaper, paper_id)
        if paper is None:
            return

        paper.ocr_status = "processing"
        await db.commit()

        try:
            # Step 1: 豆包Vision看图拆题——多张图**并发** OCR(各自独立 LLM 调用,不碰 db),显著提速
            import asyncio
            ocr_results = await asyncio.gather(*[run_ocr(url) for url in paper.source_image_urls])
            printed_parts = [o.printed_text for o in ocr_results if o.printed_text]
            handwritten_parts = [o.handwritten_text for o in ocr_results if o.handwritten_text]

            merged = OcrResult(
                printed_text="\n".join(printed_parts),
                handwritten_text="\n".join(handwritten_parts),
            )
            parsed = await split_paper_questions(merged)

            # Step 2: DeepSeek 批量归类 KP（M40 新增）——归类是增强,失败不拖垮整卷(题目照常入库)
            try:
                kp_map: dict[str, str] = await classify_kps(parsed)
            except Exception:  # noqa: BLE001
                kp_map = {}

            # Step 2.4: 去重——每个 distinct kp_key 只受控匹配一次(含 LLM),避免 N 题×每题一次 LLM(慢因)。
            # 未命中且是语法名的,在此一次性建个人语法节点(幂等)。
            from app.services.kp_match_service import match_kp
            from app.services import grammar_progress_service
            match_cache: dict[str, uuid.UUID | None] = {}
            for _key in {v for v in kp_map.values() if v}:
                try:
                    _m = await match_kp(db, raw_name=_key, axis_hint="knowledge",
                                        source_type="uploaded_student")
                    match_cache[_key] = _m.node_id
                    if _m.node_id is None:
                        await grammar_progress_service.add_personal_if_grammar(
                            db, student_id=paper.student_id, name=_key, source="upload_paper")
                except Exception:  # noqa: BLE001
                    match_cache[_key] = None

            # Step 2.5: 还原原卷「大题/板块」结构——按 section 首次出现顺序建 user_paper_sections
            from app.models.d13_v2_user_papers import UserPaperSection
            sec_id_by_label: dict[str, uuid.UUID] = {}
            _sec_ord = 0
            for pq in parsed:
                label, suggested = _label_of(pq)
                if label not in sec_id_by_label:
                    sec = UserPaperSection(
                        user_paper_id=paper.id, label=label,
                        section_type=_section_type(label), is_suggested=suggested, sort_order=_sec_ord)
                    db.add(sec)
                    await db.flush()
                    sec_id_by_label[label] = sec.id
                    _sec_ord += 1

            # Step 3: 落库题目(带大题/语篇/顺序)+ 题目↔node 关联(KP-First)+ 补写掌握账
            for _i, pq in enumerate(parsed):
                is_wrong = _is_wrong(pq.student_answer, pq.correct_answer)
                q = UserPaperQuestion(
                    user_paper_id=paper.id,
                    section_id=sec_id_by_label.get(_label_of(pq)[0]),
                    passage=pq.passage,
                    block_key=pq.block_key,
                    sort_order=_i,
                    question_no=pq.question_no,
                    question_type=pq.question_type,
                    stem=pq.stem,
                    student_answer=pq.student_answer,
                    correct_answer=pq.correct_answer,
                    explanation=pq.explanation,
                    is_wrong=is_wrong,
                )
                db.add(q)
                await db.flush()   # 取 q.id 以建关联

                # 知识点(KP-First):归类名 → match_kp 命中 node(未命中落候选 pending),
                # 把 node 挂到题上(q.node_id)+ 掌握账补写(student_kp/node)+ 错题收口 wrong_record
                qno = pq.question_no or ""
                kp_key = kp_map.get(qno)
                if kp_key:
                    node_id = match_cache.get(kp_key)   # Step 2.4 已受控匹配,直接复用(不再逐题 LLM)
                    # 掌握账:传入已解析 node_id,免 upsert_mastery 内部再匹配
                    await upsert_mastery(
                        db,
                        student_id=paper.student_id,
                        kp_key=kp_key,
                        kp_id=node_id,
                        is_correct=not is_wrong,
                        source="paper_upload",
                    )
                    q.node_id = node_id   # 命中→挂 node;未命中→NULL(候选/个人节点已在 Step 2.4 处理)
                    # 整卷错题收口进 wrong_record(失败不阻断整卷管线)
                    if is_wrong:
                        try:
                            from app.services import wrong_center_service
                            await wrong_center_service.record_wrong(
                                db, student_id=paper.student_id, q_scope="uploaded",
                                question_id=q.id, node_id=node_id)
                        except Exception:  # noqa: BLE001
                            pass

            # P2：整卷题干里命中词典的生词 → 该生词力通候选池（best-effort）
            try:
                from app.services import vocabulary_service
                stems_text = " ".join((pq.stem or "") for pq in parsed)
                await vocabulary_service.add_source_candidates(
                    db, student_id=paper.student_id, text=stems_text, source="paper")
            except Exception:  # noqa: BLE001
                pass

            # 标题:用户没填 → 自动生成「名字 年月日」;解析不出名字 → 「年月日作业X」(best-effort)
            if not (paper.title or "").strip():
                try:
                    paper.title = await _gen_paper_title(db, paper, merged.printed_text)
                except Exception:  # noqa: BLE001
                    pass

            paper.ocr_status = "completed"
        except Exception:
            paper.ocr_status = "failed"

        await db.commit()


async def _question_count(db: AsyncSession, paper_id: uuid.UUID) -> int:
    return int(
        (await db.execute(
            select(func.count(UserPaperQuestion.id)).where(
                UserPaperQuestion.user_paper_id == paper_id
            )
        )).scalar_one()
    )


async def list_papers(
    db: AsyncSession, *, student_id: uuid.UUID, limit: int = 50
) -> list[UserPaperOut]:
    """列出某学生的全部整卷（倒序），含每卷题目数。"""
    rows = (await db.execute(
        select(UserUploadedPaper)
        .where(UserUploadedPaper.student_id == student_id)
        .order_by(UserUploadedPaper.created_at.desc())
        .limit(limit)
    )).scalars().all()

    out: list[UserPaperOut] = []
    for p in rows:
        out.append(
            UserPaperOut(
                id=p.id,
                title=p.title,
                source_image_urls=list(p.source_image_urls or []),
                ocr_status=p.ocr_status,
                question_count=await _question_count(db, p.id),
                created_at=p.created_at,
            )
        )
    return out


async def get_paper_detail(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> UserPaperDetailOut | None:
    """整卷详情（含题目列表）。非本人持有 → None。"""
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None

    from app.models.d13_v2_user_papers import UserPaperSection
    from app.schemas.user_papers import UserPaperSectionOut

    qs = (await db.execute(
        select(UserPaperQuestion)
        .where(UserPaperQuestion.user_paper_id == paper_id)
        .order_by(UserPaperQuestion.sort_order.asc(), UserPaperQuestion.created_at.asc())
    )).scalars().all()
    secs = (await db.execute(
        select(UserPaperSection)
        .where(UserPaperSection.user_paper_id == paper_id)
        .order_by(UserPaperSection.sort_order.asc())
    )).scalars().all()

    def _q_out(q):
        return UserPaperQuestionOut(
            id=q.id, question_no=q.question_no, question_type=q.question_type, stem=q.stem,
            student_answer=q.student_answer, correct_answer=q.correct_answer,
            explanation=q.explanation, is_wrong=q.is_wrong,
            passage=q.passage, block_key=q.block_key,
        )

    questions = [_q_out(q) for q in qs]            # 扁平列表(兼容旧展示)
    # 按大题分组;历史数据(section_id 为空)归到「未分组」保证不丢题
    by_sec: dict = {}
    for q in qs:
        by_sec.setdefault(q.section_id, []).append(q)
    sections = [
        UserPaperSectionOut(id=s.id, label=s.label, section_type=s.section_type,
                            is_suggested=s.is_suggested,
                            questions=[_q_out(q) for q in by_sec.get(s.id, [])])
        for s in secs
    ]
    if by_sec.get(None):                           # 无 section 的历史题兜底
        import uuid as _uuid
        sections.append(UserPaperSectionOut(
            id=_uuid.uuid4(), label="未分组", section_type=None,
            questions=[_q_out(q) for q in by_sec[None]]))

    return UserPaperDetailOut(
        id=paper.id,
        title=paper.title,
        source_image_urls=list(paper.source_image_urls or []),
        ocr_status=paper.ocr_status,
        question_count=len(questions),
        created_at=paper.created_at,
        sections=sections,
        questions=questions,
    )


async def paper_grammar_status(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> dict | None:
    """P1:本卷考的语法点(题目已挂 node)对照学生掌握度 → 已学 / 薄弱 / 未学。

    未学(new)=该语法点没练过记录;薄弱(weak)=练过但掌握度 < 0.7;已学(learned)=≥ 0.7。
    语法点掌握度优先用四维派生(与知识点页一致),无四维记录回退加权口径。非本人 → None。
    """
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp
    from app.services.kp_lecture_service import kp_type_of
    from app.services.kp_mastery_service import weighted_mastery, grammar_overrides

    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None

    # 本卷题目挂到的知识节点(去重)→ 只取语法点(cf/jf)
    rows = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
        .join(UserPaperQuestion, UserPaperQuestion.node_id == KnowledgeNode.id)
        .where(UserPaperQuestion.user_paper_id == paper_id)
        .distinct())).all()
    grammar = [(nid, name, code) for nid, name, code in rows if kp_type_of(code) == "grammar"]
    if not grammar:
        return {"learned": [], "weak": [], "new": [], "total": 0}

    ov = await grammar_overrides(db, student_id=student_id,
                                 nodes_with_code=[(nid, code) for nid, _n, code in grammar])
    sk_map = {sk.node_id: sk for sk in (await db.execute(
        select(StudentKp).where(StudentKp.student_id == student_id,
                                StudentKp.node_id.in_([nid for nid, _n, _c in grammar])))).scalars().all()}

    buckets = {"learned": [], "weak": [], "new": []}
    for nid, name, code in grammar:
        if nid in ov:
            mastery, events = ov[nid]
        elif nid in sk_map:
            sk = sk_map[nid]
            mastery, events = weighted_mastery(sk.fa_correct, sk.fa_wrong,
                                               sk.corrected_count, sk.redo_wrong_count)
        else:
            mastery, events = None, 0
        status = "new" if (not events or mastery is None) else ("learned" if mastery >= 0.7 else "weak")
        buckets[status].append({
            "node_id": str(nid), "name": name, "code": code,
            "mastery": mastery, "events": events,
        })

    # 先修增强:未学语法点若有先修(NodeRelation prereq),标注先修是否已学,提示「先补先修」。
    # 约定方向:边 (from=目标, relation='prereq', to=先修) —— 学 from 需先会 to。
    if buckets["new"]:
        await _attach_prereqs(db, student_id=student_id, items=buckets["new"])

    return {**buckets, "total": len(grammar)}


async def _attach_prereqs(db: AsyncSession, *, student_id: uuid.UUID, items: list[dict]) -> None:
    """给本卷未学语法点挂「先修」:教材序里排在它之前、同顶层大类、且也没学的点(教材进度驱动)。

    顺序天然来自教材(grade→semester→unit_no),不依赖手搓/AI 的 prereq 边;
    先修全部取自未学池,故都是未学(learned=False)——即「先补先修」。未设进度则静默不挂。"""
    from app.services import grammar_progress_service as gp
    tree = await gp.personal_grammar_tree(db, student_id=student_id)
    if not tree["has_progress"]:
        return
    # 未学池按 code→(rank) 建索引,顺带给本卷未学项补上自身 rank
    rank_by_code = {n["code"]: n["rank"] for n in tree["unlearned"] if n.get("code")}
    for it in items:
        code = it.get("code")
        r = rank_by_code.get(code)
        if r is None:                      # 该点不在当前进度未学池(超前/已学)→ 不挂先修
            continue
        top = code.split("-")[0]
        # unlearned 已按教材序排;顺序过滤即先修(教材序更早、同顶层大类、也没学)
        pre = [{"node_id": n["node_id"], "name": n["name"], "learned": False}
               for n in tree["unlearned"]
               if n.get("code") and n["code"].split("-")[0] == top
               and n["rank"] < r and n["code"] != code]
        if pre:
            it["prereq"] = pre[:3]


async def add_paper_grammar_to_plan(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> dict | None:
    """P4 闭环:把本卷「未学 + 薄弱」语法点一键加入学习目标 → 今日计划带出「去学/去练」。
    复用 paper_grammar_status 分桶;已学的不加。非本人 → None。"""
    from app.services import learning_plan_service
    status = await paper_grammar_status(db, paper_id=paper_id, student_id=student_id)
    if status is None:
        return None
    node_ids = [uuid.UUID(x["node_id"]) for x in (status["new"] + status["weak"])]
    added = await learning_plan_service.add_targets(
        db, student_id=student_id, node_ids=node_ids, source="paper_upload",
        source_paper_id=paper_id)
    return {"added": added, "selected": len(node_ids),
            "new": len(status["new"]), "weak": len(status["weak"])}


# ── P2 生词 / P3 长难句:从本卷原文拆,复用词力通 / 长难句服务 ──────────────────
# 常见功能词/高频词,抽生词时滤掉(避免 the/is 这类混进候选)。
_VOCAB_STOP = frozenset("""
the and for are but not you all any can had her was one our out day get has him his how man new now
old see two way who did its let put say she too use dad mom the this that these those with have from they
will would could should about there their what when where which while your yours been being does were what
into than then them been over more most some such only very much many just like also each here does
""".split())


async def _paper_texts(db: AsyncSession, paper_id: uuid.UUID) -> tuple[list[str], list[str]]:
    """本卷原文素材:去重短文(passages)+ 题干(stems),供抽生词/拆长难句。"""
    prows = (await db.execute(
        select(UserPaperQuestion.block_key, UserPaperQuestion.passage)
        .where(UserPaperQuestion.user_paper_id == paper_id,
               UserPaperQuestion.passage.isnot(None)))).all()
    passages = list({(bk or p): p for bk, p in prows if p}.values())   # 同篇按 block_key 去重
    stems = [s for (s,) in (await db.execute(
        select(UserPaperQuestion.stem)
        .where(UserPaperQuestion.user_paper_id == paper_id,
               UserPaperQuestion.stem.isnot(None)))).all()]
    return passages, stems


async def paper_vocab_candidates(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> dict | None:
    """P2:从本卷原文+题干抽词 → 词典命中 → 只留『生词(未学/接收度<0.6)』供挑选加入词力通优先学。
    复用 vocab_pin_service._words_from_text 抽词、词力通 pin 走 /vocabulary/pins。非本人 → None。"""
    from app.models.d5_learning import VocabularyWord, VocabularyLearning, StudentVocabCandidate
    from app.services.vocab_pin_service import _words_from_text

    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    passages, stems = await _paper_texts(db, paper_id)
    words = [w for w in _words_from_text(" ".join(passages + stems))
             if len(w) >= 3 and w not in _VOCAB_STOP]
    if not words:
        return {"words": []}
    hit = {w.word.lower(): w for w in (await db.execute(
        select(VocabularyWord).where(func.lower(VocabularyWord.word).in_(words)))).scalars().all()}
    # 缺词审核:原文里出现但词库没有的词 → 落审核队列(best-effort,失败不影响生词返回)
    missing = [w for w in words if w not in hit]
    if missing:
        try:
            from app.services import vocab_intensive_service
            await vocab_intensive_service.report_missing_words(db, words=missing, source="paper")
        except Exception:  # noqa: BLE001
            pass
    if not hit:
        return {"words": []}
    ids = [w.id for w in hit.values()]
    recep = {r.word_id: r.mastery_recep for r in (await db.execute(
        select(VocabularyLearning).where(VocabularyLearning.student_id == student_id,
                                         VocabularyLearning.word_id.in_(ids)))).scalars().all()}
    pinned = set((await db.execute(
        select(StudentVocabCandidate.word_id).where(
            StudentVocabCandidate.student_id == student_id,
            StudentVocabCandidate.priority > 0,
            StudentVocabCandidate.word_id.in_(ids)))).scalars().all())
    out, added = [], set()
    for w in words:                                      # 保持原文出现顺序
        vw = hit.get(w)
        if vw is None or vw.id in added:
            continue
        rc = recep.get(vw.id)
        if rc is not None and float(rc) >= 0.6:          # 接收度够 → 已掌握,不算生词
            continue
        added.add(vw.id)
        out.append({"word_id": str(vw.id), "word": vw.word, "phonetic": vw.phonetic,
                    "recep": float(rc) if rc is not None else None, "pinned": vw.id in pinned})
    return {"words": out[:40]}


async def paper_long_sentences(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> dict | None:
    """P3:从本卷短文拆长难句(复用 long_sentence_service 切句 + 长句判定),供逐句解析。非本人 → None。"""
    from app.services import long_sentence_service as ls
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    passages, _ = await _paper_texts(db, paper_id)
    seen, out = set(), []
    for p in passages:
        for s in ls.split_sentences(p):
            key = (s or "").strip()
            if key and key not in seen and ls.is_long_sentence(s):
                seen.add(key)
                out.append(key)
    return {"sentences": out[:15]}


async def analyze_paper_sentence(db: AsyncSession, sentence: str) -> dict:
    """P3:按需解析一句长难句(带暂存,命中缓存不重复调 LLM)。"""
    from app.services import long_sentence_service as ls
    return await ls.analyze_sentence_cached(db, sentence)


async def update_section(
    db: AsyncSession, *, section_id: uuid.UUID, student_id: uuid.UUID, label: str
) -> bool:
    """学生修改大题分类:改 label + 重推 section_type + 置 is_suggested=false(已人工确认)。
    校验该大题所属试卷属于本人;成功返回 True,越权/不存在返回 False。"""
    from app.models.d13_v2_user_papers import UserPaperSection
    sec = await db.get(UserPaperSection, section_id)
    if sec is None:
        return False
    paper = await db.get(UserUploadedPaper, sec.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return False
    sec.label = label.strip()
    sec.section_type = _section_type(sec.label)
    sec.is_suggested = False
    await db.commit()
    return True


async def paper_kp_summary(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> dict | None:
    """本卷错题按知识点归集（M4 深化）：每个涉及知识点的 总题/错题 数 + 薄弱标。

    非本人持有 → None。薄弱（weak）= 该 KP 本卷有错题，优先排前。
    """
    from app.models.d15_knowledge_graph import KnowledgeNode

    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None

    # R8 Phase4:按 node 归集(题上 node_id,未命中的题不计入 KP 汇总)
    rows = (await db.execute(
        select(
            KnowledgeNode.id, KnowledgeNode.name,
            func.count(UserPaperQuestion.id),
            func.count().filter(UserPaperQuestion.is_wrong.is_(True)),
        )
        .select_from(UserPaperQuestion)
        .join(KnowledgeNode, KnowledgeNode.id == UserPaperQuestion.node_id)
        .where(UserPaperQuestion.user_paper_id == paper_id)
        .group_by(KnowledgeNode.id, KnowledgeNode.name)
    )).all()

    items = [
        {"kp_id": str(node_id), "kp_name": name, "total": int(total),
         "wrong": int(wrong), "weak": int(wrong) > 0}
        for node_id, name, total, wrong in rows
    ]
    items.sort(key=lambda x: (not x["weak"], -x["wrong"], x["kp_name"]))
    return {"paper_id": str(paper_id), "items": items}


async def practice_for_question(
    db: AsyncSession, *, question_id: uuid.UUID, student_id: uuid.UUID,
    count: int = 5, difficulty: int = 3,
):
    """错题「练同类」：取该题知识点，生成同类仿真练习（M4 深化）。

    校验题目归属（题→卷→学生）；无关联知识点 → AppError。
    """
    from app.core.exceptions import AppError
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.services import practice_service

    # 校验归属
    owned = await db.scalar(
        select(func.count()).select_from(UserPaperQuestion)
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(UserPaperQuestion.id == question_id,
               UserUploadedPaper.student_id == student_id))
    if not owned:
        raise AppError(code=404, message="题目不存在或无权访问")

    kp_name = await db.scalar(
        select(KnowledgeNode.name)
        .join(UserPaperQuestion, UserPaperQuestion.node_id == KnowledgeNode.id)
        .where(UserPaperQuestion.id == question_id).limit(1))
    if not kp_name:
        raise AppError(code=400, message="该题暂无关联知识点，无法生成同类练习")

    questions = await practice_service.generate_practice_questions(
        db, student_id=student_id, knowledge_point=kp_name, count=count, difficulty=difficulty)
    return {"knowledge_point": kp_name, "questions": questions}
