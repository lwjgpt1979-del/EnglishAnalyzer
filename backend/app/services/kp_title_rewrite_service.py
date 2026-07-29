"""语法点展示标题整理(方案 B2):不改 name,把短标题写入 description 首行。

学生端展示优先读 description 首行(≤40 字);匹配/归类仍用 knowledge_nodes.name。
运营后台批量:suggest 出草稿 → 人工确认 apply 写 description(AI,付费)。
规则批量:rule_rewrite_title → apply_rule_batch(零 LLM,确定性)。
付费调用按 (name|description) md5 全局缓存 kp_title_rewrite_cache。
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode, KpTitleRewriteCache
from app.services.llm_provider import complete_json, fast_model

_log = logging.getLogger(__name__)

_TITLE_MAX = 40  # 展示名首行上限;超长视为旧散文说明,回退 name
_DETAIL_MAX = 80
_COLON_RE = re.compile(r"[:：]")
# 像完整例句: 大写开头 + 较长 + 含空格(非纯语法公式)
_EXAMPLE_RE = re.compile(
    r"^(I|He|She|They|We|You|It|The|My|His|Her|This|That|There|Where|What|How|When|If|As|No|Not|So|Such|"
    r"Although|Because|Since|While|Whenever|Wherever|Who|Which|Some|Many|Every|Each|Go|She|He)\b",
    re.I,
)


def display_label(name: str, description: str | None) -> str:
    """学生/列表展示名:description 首行短标题优先,否则 name。"""
    if not description:
        return name
    first = description.strip().split("\n", 1)[0].strip()
    if not first or len(first) > _TITLE_MAX:
        return name
    return first


def compose_description(title: str, detail: str | None = None) -> str:
    """落库 description:首行短标题 + 可选说明行。"""
    t = (title or "").strip()[:_TITLE_MAX]
    d = (detail or "").strip()
    return f"{t}\n{d}" if d else t


def needs_rewrite(name: str, description: str | None) -> bool:
    """是否仍缺合格展示标题(description 首行短且不同于 name)。"""
    if not description or not description.strip():
        return True
    first = description.strip().split("\n", 1)[0].strip()
    if not first or len(first) > _TITLE_MAX or first == name.strip():
        return True
    return False


def infer_title_source(name: str, description: str | None) -> str:
    """展示标题来源: pending(未整理) | rule(规则) | ai(AI 补洞/批量)。"""
    label = display_label(name, description)
    if label == (name or "").strip():
        return "pending"
    first = (description or "").strip().split("\n", 1)[0].strip()
    if " · " in first:
        return "ai"
    return "rule"


def kp_display_fields(name: str, description: str | None) -> dict:
    """Admin 树/列表用:展示标题 + 来源标签。"""
    return {
        "display_label": display_label(name, description),
        "title_source": infer_title_source(name, description),
    }


def node_display_label(node: KnowledgeNode) -> str:
    """KnowledgeNode → 学生端展示名。"""
    return display_label(node.name, node.description)


async def display_labels_for_nodes(
    db: AsyncSession, node_ids: list[uuid.UUID],
) -> dict[str, str]:
    """批量 node_id(str) → 展示名;供错题列表等 overlay。"""
    if not node_ids:
        return {}
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.description)
        .where(KnowledgeNode.id.in_(node_ids))
    )).all()
    return {str(r[0]): display_label(r[1], r[2]) for r in rows}


def _looks_like_example(segment: str) -> bool:
    """判断冒号分段是否像例句(而非语法公式/模式)。"""
    s = segment.strip()
    if not s or len(s) < 18:
        return False
    # 语法公式/模板(非完整例句)
    if re.search(r"\b(sb\.?|sth\.?|\.\.\.|\+|\=|/|\||→|no matter)", s, re.I):
        return False
    if re.search(
        r"(从句|句型|结构|引导|倒装|虚拟|定语|状语|宾语|主语|表语|同位语|比较|互换|转换|公式|规则|用法|搭配|部分|表)",
        s,
    ):
        return False
    if _EXAMPLE_RE.match(s) and " " in s:
        return True
    if len(s) > 42 and s[0].isupper() and " " in s and "." in s:
        return True
    return False


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(re.findall(r"[\u4e00-\u9fff]", text)) / len(text)


def rule_rewrite_title(name: str) -> tuple[str, str]:
    """规则整理展示标题(零 LLM):从 name 抽短标题 + 可选例句 detail。不改 name。

    规则:
    1) 按 : / ： 切段,去掉像例句的段;
    2) 无冒号时尝试「中文标签-英文例句」形 (- 分隔);
    3) 首段为中文短标签且后有语法公式 → 「标签 · 公式」;
    4) 否则取首个非例句段;仍过长则截断至 _TITLE_MAX;
    5) detail 取首个例句段(≤80字),无则空。
    """
    raw = (name or "").strip()
    if not raw:
        return "", ""
    if len(raw) <= _TITLE_MAX and _COLON_RE.search(raw) is None and "-" not in raw:
        return raw, ""

    parts = [p.strip() for p in _COLON_RE.split(raw) if p.strip()]
    dash_title, dash_detail = "", ""
    if not parts or (len(parts) == 1 and _COLON_RE.search(raw) is None):
        m = re.match(r"^(.+?)-([A-Za-z\(].+)$", raw)
        if m:
            left, right = m.group(1).strip(), m.group(2).strip()
            if len(left) <= _TITLE_MAX and ( _looks_like_example(right) or len(right) > 12):
                dash_title, dash_detail = left[:_TITLE_MAX], right[:_DETAIL_MAX]
        if dash_title:
            return dash_title, dash_detail
        if len(raw) > _TITLE_MAX and _COLON_RE.search(raw) is None:
            return raw[:_TITLE_MAX], ""

    if not parts:
        parts = [raw]

    examples = [p for p in parts if _looks_like_example(p)]
    body = [p for p in parts if not _looks_like_example(p)] or [parts[0]]

    if len(body) >= 2 and _cjk_ratio(body[0]) >= 0.25 and len(body[0]) <= 22:
        title = f"{body[0]} · {body[1]}"
    elif len(body) >= 2 and len(body[0]) <= 12 and len(body[1]) <= 28:
        title = f"{body[0]} · {body[1]}"
    else:
        title = body[0]

    title = re.sub(r"\s+", " ", title).strip()[:_TITLE_MAX]
    if not title:
        title = parts[0][: _TITLE_MAX]

    detail = ""
    if examples:
        detail = examples[0][: _DETAIL_MAX]

    return title, detail


def _input_md5(name: str, description: str | None) -> str:
    raw = f"{(name or '').strip()}|{(description or '').strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


async def _suggest_one(db: AsyncSession, *, name: str, description: str | None) -> dict:
    """单条建议(先查缓存,未命中再调 LLM)。返回 {title, detail, cached}。"""
    md5 = _input_md5(name, description)
    hit = await db.get(KpTitleRewriteCache, md5)
    if hit is not None:
        return {"title": hit.title, "detail": hit.detail or "", "cached": True}

    system = (
        "你是初中英语语法编辑。把粗糙的语法点名称整理成学生可读的短标题。\n"
        "要求:\n"
        "1) title:中文短标题,≤16字,形如「大类 · 要点」(如「陈述句 · 助动词结构」),不要塞整句英文例句;\n"
        "2) detail:一句中文说明+可附英文短例句,总长≤80字;\n"
        "3) 不要改动语法含义,不要发明考点;\n"
        "严格输出 JSON:{\"title\":\"...\",\"detail\":\"...\"}"
    )
    user = f"原名称:{name}\n现有描述:{(description or '').strip() or '(空)'}\n返回 JSON:"
    data = await complete_json(
        system_prompt=system, user_prompt=user, max_tokens=512,
        model=fast_model(), feature="kp_title_rewrite",
        validate=lambda x: isinstance(x, dict) and bool(str(x.get("title") or "").strip()),
    )
    if not data:
        # 兜底:去掉冒号后例句,截断
        base = name.split(":", 1)[0].split("：", 1)[0].strip() or name
        title, detail = base[:_TITLE_MAX], ""
    else:
        title = str(data.get("title") or "").strip()[:_TITLE_MAX]
        detail = str(data.get("detail") or "").strip()[:200]
    # 同 (name|description) 可能对应多个节点;并发批跑时用 upsert 避免 UniqueViolation
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    await db.execute(
        pg_insert(KpTitleRewriteCache)
        .values(input_md5=md5, title=title, detail=detail or None)
        .on_conflict_do_update(
            index_elements=[KpTitleRewriteCache.input_md5],
            set_={"title": title, "detail": detail or None},
        )
    )
    await db.flush()
    return {"title": title, "detail": detail, "cached": False}


async def suggest_batch(db: AsyncSession, *, node_ids: list[uuid.UUID]) -> list[dict]:
    """批量生成展示标题草稿(不写节点)。"""
    if not node_ids:
        return []
    if len(node_ids) > 50:
        raise AppError(code=400, message="单次最多 50 个节点")
    rows = (await db.execute(
        sa.select(KnowledgeNode).where(KnowledgeNode.id.in_(node_ids)))).scalars().all()
    by_id = {n.id: n for n in rows}
    out = []
    for nid in node_ids:
        n = by_id.get(nid)
        if n is None:
            continue
        sug = await _suggest_one(db, name=n.name, description=n.description)
        out.append({
            "id": str(n.id), "name": n.name, "description": n.description,
            "suggested_title": sug["title"], "suggested_detail": sug["detail"],
            "cached": sug["cached"],
            "current_label": display_label(n.name, n.description),
        })
    return out


async def apply_batch(db: AsyncSession, *, items: list[dict]) -> dict:
    """确认写入:把 title(+detail) 写入 description 首行约定;不改 name。

    items: [{id, title, detail?}]
    """
    if not items:
        return {"updated": 0}
    if len(items) > 50:
        raise AppError(code=400, message="单次最多 50 个节点")
    updated = 0
    for it in items:
        try:
            nid = uuid.UUID(str(it.get("id")))
        except (ValueError, TypeError):
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        n = await db.get(KnowledgeNode, nid)
        if n is None:
            continue
        detail = str(it.get("detail") or "").strip() or None
        n.description = compose_description(title, detail)
        updated += 1
    await db.flush()
    from app.services.kp_candidate_service import invalidate_node_tree_cache
    invalidate_node_tree_cache()
    return {"updated": updated}


async def apply_rule_batch(
    db: AsyncSession,
    *,
    node_ids: list[uuid.UUID] | None = None,
    only_active: bool = True,
    overwrite: bool = False,
) -> dict:
    """规则批量写入 description(零 LLM)。默认只处理仍缺展示标题的节点。

    overwrite=True 时强制按 name 重算并覆盖已有 description。
    """
    stmt = sa.select(KnowledgeNode)
    if only_active:
        stmt = stmt.where(KnowledgeNode.status == "active")
    if node_ids:
        stmt = stmt.where(KnowledgeNode.id.in_(node_ids))
    rows = (await db.execute(stmt)).scalars().all()

    updated = 0
    skipped = 0
    for n in rows:
        if not overwrite and not needs_rewrite(n.name, n.description):
            skipped += 1
            continue
        title, detail = rule_rewrite_title(n.name)
        if not title:
            skipped += 1
            continue
        n.description = compose_description(title, detail or None)
        updated += 1
    await db.flush()
    from app.services.kp_candidate_service import invalidate_node_tree_cache
    invalidate_node_tree_cache()
    return {"updated": updated, "skipped": skipped, "total": len(rows)}


def _is_hard_name(name: str) -> bool:
    """规则难处理的 name: 偏长或中英混杂。"""
    n = (name or "").strip()
    if len(n) > 22:
        return True
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", n))
    has_lat = bool(re.search(r"[A-Za-z]", n))
    return has_cjk and has_lat


async def count_pending(
    db: AsyncSession,
    *,
    only_active: bool = True,
    hard_only: bool = False,
) -> int:
    """仍缺合格展示标题的节点数。"""
    stmt = sa.select(KnowledgeNode)
    if only_active:
        stmt = stmt.where(KnowledgeNode.status == "active")
    rows = (await db.execute(stmt)).scalars().all()
    n = 0
    for row in rows:
        if not needs_rewrite(row.name, row.description):
            continue
        if hard_only and not _is_hard_name(row.name):
            continue
        n += 1
    return n


async def apply_ai_for_pending(
    db: AsyncSession,
    *,
    only_active: bool = True,
    hard_only: bool = False,
    limit: int | None = None,
) -> dict:
    """规则优先 + AI 补洞:仅对仍缺展示标题的节点 suggest→apply(命中缓存不二次付费)。

    hard_only=True 时只处理偏长/中英混杂(name 规则难压短)的子集。
    """
    stmt = sa.select(KnowledgeNode)
    if only_active:
        stmt = stmt.where(KnowledgeNode.status == "active")
    rows = (await db.execute(stmt)).scalars().all()
    pending: list[KnowledgeNode] = []
    for row in rows:
        if not needs_rewrite(row.name, row.description):
            continue
        if hard_only and not _is_hard_name(row.name):
            continue
        pending.append(row)
    if limit is not None:
        pending = pending[: max(0, limit)]

    pending_ids = [n.id for n in pending]
    updated = 0
    cached_hits = 0
    llm_calls = 0
    batch_size = 50
    for i in range(0, len(pending_ids), batch_size):
        chunk = pending_ids[i: i + batch_size]
        items = await suggest_batch(db, node_ids=chunk)
        await db.commit()
        cached_hits += sum(1 for it in items if it.get("cached"))
        llm_calls += sum(1 for it in items if not it.get("cached"))
        apply_items = [
            {
                "id": it["id"],
                "title": it["suggested_title"],
                "detail": it.get("suggested_detail") or "",
            }
            for it in items
            if it.get("suggested_title")
        ]
        r = await apply_batch(db, items=apply_items)
        updated += int(r.get("updated") or 0)
        await db.commit()

    from app.services.kp_candidate_service import invalidate_node_tree_cache
    invalidate_node_tree_cache()
    return {
        "pending": len(pending_ids),
        "updated": updated,
        "cached": cached_hits,
        "llm": llm_calls,
        "hard_only": hard_only,
    }
