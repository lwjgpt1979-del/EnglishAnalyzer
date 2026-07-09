"""考点讲解(kp_lecture)服务——按考点类型的「教学环节」模板 + 逐段读写/发布。

设计要点(取代 node_resource 六维):
- 讲解结构 = 教学环节 section,不是学科技能;环节随考点类型自适应。
- 考点类型由节点编码前缀推出(cf/jf=语法、rc=阅读、lt=听力、wr=写作)。
- 一考点一套讲解、一环节一行(node_id + section_key 唯一);draft/published 逐段发布。
- 消费侧(学生)只见 published;完整度 = 已发布 section / 该类型模板 section 数。
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d25_kp_lecture import KpLecture

# ── 考点类型 → 讲解模板(精简为 3 个「不重叠」环节:section_key, 标题)──────────────
# 原则:环节尽量少;每段只干一件事、彼此不重复;例句/例题只在一个环节里出现,别到处堆。
LECTURE_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "grammar": [
        ("idea", "一句话搞懂"), ("examples", "看例句"), ("pitfall", "别踩坑"),
    ],
    "reading": [
        ("idea", "什么题"), ("steps", "怎么做"), ("example", "看一题"),
    ],
    "listening": [
        ("idea", "什么题"), ("signals", "抓这些词"), ("example", "看一题"),
    ],
    "writing": [
        ("frame", "怎么搭"), ("sentences", "好句子"), ("model", "看范文"),
    ],
}

TYPE_LABEL = {"grammar": "语法", "reading": "阅读", "listening": "听力", "writing": "写作"}

# 节点编码前缀 → 考点类型(cf 词法 / jf 句法 都归语法)
_PREFIX_TYPE = {"cf": "grammar", "jf": "grammar", "rc": "reading", "lt": "listening", "wr": "writing"}


def kp_type_of(code: str | None) -> str:
    """由节点编码前缀判定考点类型;无法判定 → grammar(语法为最常见兜底)。"""
    c = (code or "").lower()
    for pref, t in _PREFIX_TYPE.items():
        if c.startswith(pref):
            return t
    return "grammar"


def template_for(code: str | None) -> list[dict]:
    """该考点应有的讲解环节模板:[{key, title, order}]。"""
    tpl = LECTURE_TEMPLATES[kp_type_of(code)]
    return [{"key": k, "title": t, "order": i} for i, (k, t) in enumerate(tpl)]


def _title(code: str | None, section_key: str) -> str:
    for k, t in LECTURE_TEMPLATES[kp_type_of(code)]:
        if k == section_key:
            return t
    return section_key


async def list_sections(db: AsyncSession, *, node_id: uuid.UUID, code: str | None,
                        published_only: bool = False) -> dict:
    """某考点的讲解:按模板顺序返回每个 section(含未填的占位),附类型/完整度。

    published_only=True(学生侧):只把已发布的 section 视为「有内容」。
    """
    rows = (await db.execute(select(KpLecture).where(KpLecture.node_id == node_id))).scalars().all()
    by_key = {r.section_key: r for r in rows}
    tpl = template_for(code)
    sections = []
    filled = 0
    for t in tpl:
        r = by_key.get(t["key"])
        has = bool(r and (r.content_md or "").strip()
                   and (not published_only or r.status == "published"))
        if has:
            filled += 1
        sections.append({
            "section_key": t["key"], "title": t["title"], "order": t["order"],
            "content_md": (r.content_md if r else None),
            "media_url": (r.media_url if r else None),
            "status": (r.status if r else "empty"),
            "source": (r.source if r else None),
            "has_content": has,
        })
    kp_type = kp_type_of(code)
    return {
        "kp_type": kp_type, "kp_type_label": TYPE_LABEL[kp_type],
        "total": len(tpl), "filled": filled, "sections": sections,
    }


async def published_sections(db: AsyncSession, *, node_id: uuid.UUID, code: str | None) -> list[dict]:
    """学生端读:按模板顺序返回已发布且有正文的 section。"""
    data = await list_sections(db, node_id=node_id, code=code, published_only=True)
    return [s for s in data["sections"] if s["has_content"]]


async def upsert_section(db: AsyncSession, *, node_id: uuid.UUID, code: str | None,
                         section_key: str, content_md: str | None = None,
                         media_url: str | None = None, source: str = "manual") -> dict:
    """写/改一个讲解环节(按 node+section 幂等 upsert)。仅接受该类型模板内的 section_key。"""
    valid = {t["key"] for t in template_for(code)}
    if section_key not in valid:
        raise ValueError(f"该考点类型无此讲解环节:{section_key}")
    order = next((t["order"] for t in template_for(code) if t["key"] == section_key), 0)
    stmt = (
        pg_insert(KpLecture)
        .values(id=uuid.uuid4(), node_id=node_id, section_key=section_key,
                content_md=content_md, media_url=media_url, source=source, sort_order=order)
        .on_conflict_do_update(
            index_elements=["node_id", "section_key"],
            set_={"content_md": content_md, "media_url": media_url,
                  "source": source, "sort_order": order})
    )
    await db.execute(stmt)
    await db.commit()
    row = (await db.execute(select(KpLecture).where(
        KpLecture.node_id == node_id, KpLecture.section_key == section_key))).scalars().first()
    return {"id": str(row.id), "section_key": row.section_key, "status": row.status,
            "title": _title(code, section_key)}


async def set_status(db: AsyncSession, *, node_id: uuid.UUID, section_key: str, status: str) -> int:
    """发布/下架某讲解环节(published/draft)。"""
    if status not in ("draft", "published"):
        raise ValueError(f"非法状态:{status}")
    r = await db.execute(update(KpLecture).where(
        KpLecture.node_id == node_id, KpLecture.section_key == section_key).values(status=status))
    await db.commit()
    return r.rowcount or 0


async def set_status_all(db: AsyncSession, *, node_id: uuid.UUID, status: str) -> int:
    """整考点一键发布/下架其全部讲解环节。"""
    if status not in ("draft", "published"):
        raise ValueError(f"非法状态:{status}")
    r = await db.execute(update(KpLecture).where(KpLecture.node_id == node_id).values(status=status))
    await db.commit()
    return r.rowcount or 0


async def delete_section(db: AsyncSession, *, node_id: uuid.UUID, section_key: str) -> int:
    r = await db.execute(delete(KpLecture).where(
        KpLecture.node_id == node_id, KpLecture.section_key == section_key))
    await db.commit()
    return r.rowcount or 0


# ── AI 分段生成(草稿;人工确认后发布,符合「AI 只出建议」铁律)──────────────────
_SECTION_GUIDE = {
    # 语法
    "idea": "用一两句话把这个考点说清楚,像跟小朋友聊天。**绝对不要举例句**(例句在下一段)。",
    "examples": "只给 2-3 个最典型的例句,每句英文 + 中文,用 **加粗** 标出考点词。除了例句别写任何解释。",
    "pitfall": "只讲 1-2 个学生最常犯的错,每个用「❌ … → ✅ …」一行对照,要短。",
    # 阅读 / 听力
    "steps": "给 2-3 步解题方法,每步一句话。**不要举整道题**(例题在下一段)。",
    "example": "只讲 1 道典型例题:题目 + 一句话解析。不要写多道题。",
    "signals": "只列听音要抓的关键信号词(几个词 + 一句话说明),别写别的。",
    # 写作
    "frame": "用「开头写…、中间写…、结尾写…」三句话讲清结构,不要举整篇。",
    "sentences": "给 3-4 个能直接套用的好句式,每个配一句英文示例。",
    "model": "给 1 篇简短英文范文(适度长度),不用加解析。",
}


async def generate_section(db: AsyncSession, *, code: str | None, name: str, section_key: str) -> str:
    """AI 生成某讲解环节的正文(Markdown)。面向中小学生、极简、每段只干一件事、彼此不重复。
    dev mock 返回占位;线上调 LLM。仅返回草稿,人工确认后发布。"""
    valid = {t["key"] for t in template_for(code)}
    if section_key not in valid:
        raise ValueError(f"该考点类型无此讲解环节:{section_key}")
    title = _title(code, section_key)
    guide = _SECTION_GUIDE.get(section_key, "编写该环节的讲解正文。")
    from app.services.llm_provider import chat_completion, is_llm_dev_mode
    if is_llm_dev_mode():
        return f"(AI 草稿·{title})考点「{name}」的{title}。{guide}"
    type_label = TYPE_LABEL[kp_type_of(code)]
    sys = ("你是把英语讲得又短又好懂的老师,面向中小学生。只写用户要的这一个环节该有的内容,"
           "极简、口语化、不啰嗦、不和其它环节重复。用简洁 Markdown,不要写大标题。")
    user = (f"考点:{name}({type_label})\n只写「{title}」这一段,要求:{guide}\n"
            "整段务必短(最多 4-5 行),例句一律英文 + 中文。")
    # max_tokens 只是上限(防截断);真正的「短」由提示词控制。deepseek 会先消耗推理 token,给足余量。
    resp = await chat_completion(system_prompt=sys, user_prompt=user, max_tokens=1500, feature="kp_lecture")
    md = (resp.choices[0].message.content or "").strip()
    # 去掉模型爱回显的标题(UI 已有标题,重复多余)
    for pat in (f"**{title}**：", f"**{title}**:", f"**{title}**", f"{title}：", f"{title}:", title):
        if md.startswith(pat):
            md = md[len(pat):].lstrip("：:*  \n")
            break
    return md


async def generate_bulk_missing(db: AsyncSession, *, node_ids: list[uuid.UUID],
                                concurrency: int = 6) -> dict:
    """批量:对多个考点并发 AI 生成各自「还没内容」的讲解环节(均落草稿,人工确认后发布)。

    LLM 生成阶段并发(信号量限流,不占 DB);写库阶段顺序 upsert(避免并发 session)。
    返回 {nodes, sections_missing, generated, failed}。
    """
    import asyncio
    from app.models.d15_knowledge_graph import KnowledgeNode

    nodes = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.code, KnowledgeNode.name)
        .where(KnowledgeNode.id.in_(node_ids)))).all()
    # 收集所有「缺内容」的 (node, section) 任务
    tasks: list[tuple] = []
    for nid, code, name in nodes:
        data = await list_sections(db, node_id=nid, code=code)
        for s in data["sections"]:
            if not s["has_content"]:
                tasks.append((nid, code, name, s["section_key"]))

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _gen(nid, code, name, sk):
        async with sem:                    # generate_section 只调 LLM、不碰 db,可安全并发
            last = "生成为空"
            for attempt in range(2):       # 1 次重试:抗 LLM 偶发空返回/超时
                try:
                    md = await generate_section(db, code=code, name=name, section_key=sk)
                    if (md or "").strip():
                        return (nid, code, sk, md, None)
                except Exception as e:     # noqa: BLE001 单个失败不拖垮整批
                    last = str(e)[:120]
            return (nid, code, sk, None, last)

    results = await asyncio.gather(*[_gen(*t) for t in tasks]) if tasks else []
    generated = failed = 0
    for nid, code, sk, md, err in results:      # 顺序写库(每条各自 commit)
        if err or not (md or "").strip():
            failed += 1
            continue
        await upsert_section(db, node_id=nid, code=code, section_key=sk, content_md=md, source="ai")
        generated += 1
    return {"nodes": len(nodes), "sections_missing": len(tasks),
            "generated": generated, "failed": failed}


async def filled_counts(db: AsyncSession, *, node_ids: list[uuid.UUID],
                        published_only: bool = False) -> dict[uuid.UUID, int]:
    """批量:各 node 已填(published_only 时=已发布)且有正文的 section 数。供总览完整度列。"""
    from sqlalchemy import func
    conds = [KpLecture.node_id.in_(node_ids), KpLecture.content_md.isnot(None), KpLecture.content_md != ""]
    if published_only:
        conds.append(KpLecture.status == "published")
    rows = (await db.execute(
        select(KpLecture.node_id, func.count()).where(*conds).group_by(KpLecture.node_id))).all()
    return {nid: int(c) for nid, c in rows}
