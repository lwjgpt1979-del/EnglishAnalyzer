"""单元长难句·理解向(D1+A):一次 LLM 抽取或合成≤8 句。

贴本单元语法(gp)+tier(易/中/难)梯度;用词相对简单;不挂知识图谱。
规则闸入库二次保险。付费结果按「原文 md5 + 年级 + 语法范围」全局缓存(v6)。
截断(length)不升档重试,立刻走限量合成兜底。
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError

_log = logging.getLogger(__name__)

_SYNTH_MIN = 5
_SYNTH_MAX = 8
_EXTRACT_MAX = 8
# v6: 方案A 限量≤8句 + 截断不升档;仍不补译文
_CACHE_VER = "v6"

_TIER_LABEL = {1: "易", 2: "中", 3: "难"}


def _clamp_tier(v: Any) -> int:
    try:
        t = int(v)
    except (TypeError, ValueError):
        return 2
    return 1 if t < 1 else (3 if t > 3 else t)


def _match_grammar_point(gp: str, grammar_names: list[str]) -> str:
    """把模型给的语法点收敛到本单元名单(子串互含);名单空则原样截断。"""
    g = (gp or "").strip()
    if not grammar_names:
        return g[:120]
    if not g:
        return (grammar_names[0] or "")[:120]
    for name in grammar_names:
        n = (name or "").strip()
        if not n:
            continue
        if n == g or n in g or g in n:
            return n[:120]
    return g[:120]


def _sort_by_gradient(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 tier 升序,同档按 spaCy difficulty 升序 → 易→难梯度。"""
    return sorted(
        items,
        key=lambda x: (int(x.get("tier") or 2), int(x.get("difficulty") or 0), x.get("text") or ""),
    )

# 语法讲解/练习指令口吻(非整句叙述)
_META_RE = re.compile(
    r"(?i)\b("
    r"ask and answer|using the verbs?|simple present( tense)?|"
    r"complete the|fill in|look at the|match the|rewrite the|"
    r"choose the|translate the|conjugate|grammar tip|"
    r"like this\s*:|as follows|for example\s*:|"
    r"do not\s*=|does not\s*=|did not\s*=|can not\s*=|cannot\s*="
    r")\b|"
    r"\bwe use\b.+\bwith\b|"  # We use … with … 语法说明
    r"_{3,}|\(\s*am\s*,\s*are\s*,\s*is\s*\)"  # 填空 / 选项列举
)
# 斜杠多选主语/动词范式: He/She/It 、 I/you/we/they 、 do/does
_SLASH_PARADIGM_RE = re.compile(
    r"(?i)\b("
    r"i|you|he|she|it|we|they|do|does|did|am|is|are|was|were|"
    r"my|your|his|her|its|our|their"
    r")\s*/\s*("
    r"i|you|he|she|it|we|they|do|does|did|am|is|are|was|were|"
    r"my|your|his|her|its|our|their"
    r")\b"
)
# 常见粘连: Theydo / likesport / Wedo
_GLUED_RE = re.compile(
    r"(?i)\b("
    r"theydo|theydon'?t|wedo|wedon'?t|youdo|youdon'?t|"
    r"hedoes|shedoes|itdoes|hedoesn'?t|shedoesn'?t|"
    r"likesport|likesports|playsport|playsports|"
    r"donot|doesnot|didnot"
    r")\b"
)
# 词中驼峰粘连 TheyDo / likeSport
_CAMEL_GLUE_RE = re.compile(r"[a-z][A-Z]")


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def is_valid_natural_sentence(text: str) -> bool:
    """方案 A:规则拒识——只要合法、可独立理解的自然英文句。

    拒:斜杠范式、等号对照、单词粘连、语法讲解/练习指令碎片等。
    """
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) < 12:
        return False
    # 字母过少(几乎无英文)
    letters = re.findall(r"[A-Za-z]", s)
    if len(letters) < 8:
        return False
    # 斜杠过多或人称/动词斜杠范式
    if s.count("/") >= 2:
        return False
    if _SLASH_PARADIGM_RE.search(s):
        return False
    # 等号对照(do not = don't)
    if "=" in s:
        return False
    if _GLUED_RE.search(s) or _CAMEL_GLUE_RE.search(s):
        return False
    if _META_RE.search(s):
        return False
    # 目录/单元元行
    if re.match(r"(?i)^(here are|unit\s*\d|第.+单元|grammar|vocabulary)\b", s):
        return False
    # 须像完整句:以句号/问号/叹号收尾,或首字母大写且含空格分词≥6
    words = re.findall(r"[A-Za-z']+", s)
    if len(words) < 6:
        return False
    if not (s[-1] in ".?!" or (s[0].isupper() and len(words) >= 8)):
        return False
    return True


def _min_words_for_grade(grade: str | None, stage: str | None) -> int:
    """理解向门槛略低于平台默认 20,适配教材短文。"""
    g = grade or ""
    if any(k in g for k in ("高三", "高3", "高二", "高2")):
        return 14
    if any(k in g for k in ("高一", "高1", "高中")):
        return 12
    if any(k in g for k in ("九年级", "初三", "八年级", "初二")):
        return 10
    if stage == "高":
        return 12
    if stage == "小":
        return 8
    return 10  # 初一及默认


def _diff_threshold(grade: str | None, stage: str | None) -> int:
    """年级锚点略下调,把「对本年级略难」的句也纳入。"""
    from app.services.long_sentence_service import _theta_from_grade
    return max(18, int(_theta_from_grade(grade, stage)) - 12)


def _input_key(course_text: str, grade: str | None, grammar_names: list[str]) -> str:
    gscope = ",".join(sorted({(n or "").strip() for n in grammar_names if (n or "").strip()}))
    return _md5(f"{_CACHE_VER}|{(grade or '').strip()}|{gscope}|{course_text.strip()}")


def _row_out(r) -> dict[str, Any]:
    tier = getattr(r, "tier", None)
    return {
        "id": str(r.id),
        "text": r.text,
        "translation": r.translation or "",
        "why": r.why or "",
        "src": r.src,
        "difficulty": r.difficulty,
        "tier": tier,
        "tier_label": _TIER_LABEL.get(int(tier), "") if tier is not None else "",
        "grammar_point": getattr(r, "grammar_point", None) or "",
        "sort_order": r.sort_order,
    }


async def _grammar_scope_names(db: AsyncSession, unit_id: uuid.UUID) -> list[str]:
    from app.services.curriculum_service import list_unit_linked_nodes
    nodes = await list_unit_linked_nodes(db, unit_id=unit_id)
    names: list[str] = []
    for n in nodes:
        if "语法" not in (n.get("kinds") or []):
            continue
        if n.get("node_name"):
            names.append(n["node_name"])
        for p in n.get("points") or []:
            if p and p not in names:
                names.append(p)
    return names


def _extract_candidates(
    course_text: str, *, grade: str | None, stage: str | None,
) -> list[dict[str, Any]]:
    """规则抽尽:先合法性闸门,再词数/难度;滤光则由上层走合成。"""
    from app.services.long_sentence_service import (
        detect_syntax_points, split_sentences, syntactic_complexity, _is_long,
    )
    min_words = _min_words_for_grade(grade, stage)
    thr = _diff_threshold(grade, stage)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sent in split_sentences(course_text or ""):
        s = re.sub(r"\s+", " ", (sent or "").strip())
        if len(s) < 8 or s.lower() in seen:
            continue
        if not is_valid_natural_sentence(s):
            continue
        comp = syntactic_complexity(s, min_words)
        hard = _is_long(comp, s, min_words) or (
            comp["word_count"] >= min_words and comp["difficulty"] >= thr
        )
        if not hard:
            continue
        seen.add(s.lower())
        pts = detect_syntax_points(s)
        why = (" · ".join(pts) if pts else "信息链较长 / 结构复合") + f" · 难度{comp['difficulty']}"
        out.append({
            "text": s,
            "translation": "",
            "why": why,
            "src": "extract",
            "difficulty": comp["difficulty"],
        })
    return out


def _normalize_item(
    row: dict[str, Any], *, default_src: str, grammar_names: list[str] | None = None,
) -> dict[str, Any] | None:
    """解析 LLM 一行 → 过规则闸 → tier/gp + spaCy 难度;非法返回 None。"""
    from app.services.long_sentence_service import syntactic_complexity
    en = (row.get("en") or row.get("text") or "").strip()
    if not en or not is_valid_natural_sentence(en):
        return None
    src = (row.get("src") or default_src).strip().lower()
    if src not in ("extract", "synth"):
        src = default_src
    tier = _clamp_tier(row.get("tier") or row.get("diff_tier"))
    gp = _match_grammar_point(
        str(row.get("gp") or row.get("grammar_point") or ""),
        grammar_names or [],
    )
    diff = None
    try:
        diff = syntactic_complexity(en).get("difficulty")
    except Exception:  # noqa: BLE001
        diff = None
    label = _TIER_LABEL.get(tier, "中")
    why = (row.get("why") or "").strip()
    if not why:
        why = f"{gp or '结构复合'} · {label}" if gp else (
            f"原文抽取 · {label}" if src == "extract" else f"合成句 · {label}"
        )
    return {
        "text": en,
        "translation": (row.get("zh") or row.get("translation") or "").strip(),
        "why": why,
        "src": src,
        "difficulty": diff,
        "tier": tier,
        "grammar_point": gp,
    }


async def _llm_extract_or_synth(
    *, grade: str | None, stage: str | None, grammar_names: list[str],
    course_text: str,
) -> list[dict[str, Any]]:
    """一次 LLM——抽取最多 8 句;没有则合成 5–8 句。

    约束:贴本单元语法;tier 梯度;不补译文。截断不升档,空结果立刻限量合成。
    """
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    g_label = (grade or stage or "初中") or "初中"
    gscope = "、".join(grammar_names[:12]) if grammar_names else "本年级常见复合句/并列句"
    body = (course_text or "").strip()[:3000]

    if is_llm_dev_mode():
        return await _synth_sentences(
            grade=grade, stage=stage, grammar_names=grammar_names,
            course_text=course_text,
        )

    system = (
        "你是中学英语教材编辑。按下列规则处理单元原文长难句(理解练习用)。\n"
        f"【1·抽取】从原文挑出最多 {_EXTRACT_MAX} 句合格长难句(宁少勿滥,勿贪多):\n"
        "- 完整、合法、可独立理解的自然叙述句(有标点)。\n"
        "- 信息链/结构有一定复合(并列、从句等)。\n"
        "- **每句必须体现本单元语法范围中的某一点**(见用户消息名单),在 gp 填写该点名。\n"
        "- **严禁**:语法说明(We use…with…)、填空、选项列举、斜杠范式、等号对照、练习指令、目录行、残缺碎片。\n"
        f"【2·合成】若一条都抽不到:合成恰好 {_SYNTH_MIN}–{_SYNTH_MAX} 句(不得超过 {_SYNTH_MAX})。"
        f"难度锚定年级 {g_label} 与本单元;用词简单;结构复合;每句 gp 必须选自本单元语法名单;"
        "同样严禁非法形式。\n"
        "【3·难度梯度】每句标 tier:1=易、2=中、3=难。"
        "整份结果须覆盖梯度(至少含易与难);"
        "合成时按易→难排列,且 1/2/3 都尽量出现。\n"
        "【4·输出】不要中文译文。sentences 数组长度绝对不超过 "
        f"{_EXTRACT_MAX}。\n"
        "mode=extract 全是抽取;mode=synth 全是合成(勿混用)。\n"
        '只输出 JSON:{"mode":"extract"|"synth","sentences":[{"en":"...","tier":1,"gp":"语法点名"}]}'
    )
    user = (
        f"年级:{g_label}\n本单元语法范围(gp 必须选自以下,勿编造名单外考点):\n{gscope}\n"
        f"单元原文:\n{body or '(空)'}\nJSON:"
    )
    # 限量≤8 句足够;截断不升档(escalate_ceiling=None),避免白烧第二次长调用
    data = await complete_json(
        system_prompt=system, user_prompt=user, max_tokens=1600,
        model=fast_model(), feature="unit_ls_extract_or_synth",
        escalate_ceiling=None,
        validate=lambda x: isinstance(x, dict) and isinstance(x.get("sentences"), list),
    ) or {}

    mode = (data.get("mode") or "").strip().lower()
    default_src = "synth" if mode == "synth" else "extract"
    out: list[dict[str, Any]] = []
    cap = _SYNTH_MAX if mode == "synth" else _EXTRACT_MAX
    for row in data.get("sentences") or []:
        if not isinstance(row, dict):
            continue
        it = _normalize_item(row, default_src=default_src, grammar_names=grammar_names)
        if it is None:
            continue
        if mode == "synth":
            it["src"] = "synth"
        out.append(it)
        if len(out) >= cap:
            break

    if mode != "synth" and out:
        return _sort_by_gradient(out[:_EXTRACT_MAX])

    if mode == "synth" and len(out) >= _SYNTH_MIN:
        return _sort_by_gradient(out[:_SYNTH_MAX])

    _log.warning("unit_ls L1 empty after gate (mode=%s n=%d), fallback synth", mode, len(out))
    return await _synth_sentences(
        grade=grade, stage=stage, grammar_names=grammar_names,
        course_text=course_text,
    )


async def _enrich_translations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(遗留)批量为抽取句补译文;L1 主路径已由 LLM 自带 zh,一般不再调用。"""
    need = [it for it in items if it.get("src") == "extract" and not (it.get("translation") or "").strip()]
    if not need:
        return items
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        for it in need:
            it["translation"] = it.get("translation") or "（开发模式占位译文）"
        return items
    lines = "\n".join(f"{i + 1}. {it['text']}" for i, it in enumerate(need))
    data = await complete_json(
        system_prompt=(
            "你是中学英语助教。给下列英文句各写一句简洁中文译文。"
            '只输出 JSON:{"items":[{"i":1,"zh":"..."}]}'
        ),
        user_prompt=f"句子:\n{lines}\nJSON:",
        max_tokens=1200,
        model=fast_model(),
        feature="unit_ls_enrich",
        validate=lambda x: isinstance(x, dict) and isinstance(x.get("items"), list),
    ) or {}
    zh_map: dict[int, str] = {}
    for row in data.get("items") or []:
        if not isinstance(row, dict):
            continue
        try:
            i = int(row.get("i"))
        except (TypeError, ValueError):
            continue
        zh = (row.get("zh") or "").strip()
        if zh:
            zh_map[i] = zh
    for i, it in enumerate(need):
        it["translation"] = zh_map.get(i + 1, it.get("translation") or "")
    return items


async def _synth_sentences(
    *, grade: str | None, stage: str | None, grammar_names: list[str],
    course_text: str,
) -> list[dict[str, Any]]:
    """原文抽不出时:合成 5–8 句;贴本单元语法 + tier 梯度。截断不升档。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    g_label = (grade or stage or "初中") or "初中"
    gscope = "、".join(grammar_names[:12]) if grammar_names else "本年级常见复合句/并列句"
    gp0 = (grammar_names[0] if grammar_names else "复合句") or "复合句"
    snippet = (course_text or "").strip()[:600]

    if is_llm_dev_mode():
        demo = [
            {
                "en": "When the bell rings, students walk into the classroom and put their books on the desks.",
                "tier": 1, "gp": gp0,
            },
            {
                "en": "Although Millie is quiet, she often helps her classmates with English after school.",
                "tier": 2, "gp": gp0,
            },
            {
                "en": "The library is the place where many students like to read stories on rainy days.",
                "tier": 2, "gp": gp0,
            },
            {
                "en": "If you finish your homework early, you can join the school band and practice with friends.",
                "tier": 3, "gp": gp0,
            },
            {
                "en": "Sandy says that playing the piano every day helps her feel calm before a test.",
                "tier": 3, "gp": gp0,
            },
        ]
        out = []
        for d in demo:
            it = _normalize_item(d, default_src="synth", grammar_names=grammar_names)
            if it:
                out.append(it)
        return _sort_by_gradient(out)

    system = (
        "你是中学英语教材编者。原文中找不到适合本年级的长难句时,"
        f"请合成恰好 {_SYNTH_MIN}–{_SYNTH_MAX} 句英文长难句(不得超过 {_SYNTH_MAX}),"
        "供学生练习「如何理解长难句」。\n"
        "硬性要求:\n"
        f"1. 难度锚定:{g_label};每句 gp 必须选自本单元语法名单,句子结构必须体现该点。\n"
        "2. **除结构词外,实词必须简单常见**,不高于该年级课本用词;不要生僻词。\n"
        "3. 每句必须是**完整、合法、可独立理解的自然英文句**(有标点);"
        "严禁斜杠范式(He/She/It)、等号对照(do not = don't)、单词粘连、语法讲解/练习指令。\n"
        "4. 每句信息链要够长(宜 ≥12 词);en 一句一行短写,勿冗长。\n"
        "5. 标 tier:1=易、2=中、3=难;须有易→难梯度,1/2/3 都尽量出现,并按易→难排列。\n"
        "6. **不要输出中文译文、不要 why**。\n"
        f'只输出 JSON:{{"sentences":[{{"en":"...","tier":1,"gp":"语法点名"}}]}}'
    )
    user = (
        f"年级:{g_label}\n本单元语法范围(gp 必须选自以下):\n{gscope}\n"
        f"原文片段(供话题/人名参考,勿照抄生僻词):\n{snippet or '(无)'}\nJSON:"
    )
    data = await complete_json(
        system_prompt=system, user_prompt=user, max_tokens=1400,
        model=fast_model(), feature="unit_ls_synth",
        escalate_ceiling=None,
        validate=lambda x: isinstance(x, dict)
        and isinstance(x.get("sentences"), list)
        and len([s for s in (x.get("sentences") or []) if isinstance(s, dict) and str(s.get("en") or "").strip()]) >= _SYNTH_MIN,
    ) or {}
    out: list[dict[str, Any]] = []
    for row in (data.get("sentences") or [])[:_SYNTH_MAX]:
        if not isinstance(row, dict):
            continue
        it = _normalize_item(row, default_src="synth", grammar_names=grammar_names)
        if it is None:
            continue
        it["src"] = "synth"
        out.append(it)
    if len(out) < _SYNTH_MIN:
        raise AppError(code=502, message="合成长难句失败,请重试")
    return _sort_by_gradient(out)


async def _cache_get(db: AsyncSession, key: str) -> list[dict[str, Any]] | None:
    from app.models.d29_unit_ls_understand import UnitLsUnderstandCache
    row = await db.get(UnitLsUnderstandCache, key)
    if row is None or not isinstance(row.result, dict):
        return None
    items = row.result.get("items")
    if not isinstance(items, list) or not items:
        return None
    # 二次闸门:缓存里若混入非法句则丢弃该缓存(当未命中)
    kept = []
    for it in items:
        if not isinstance(it, dict) or not is_valid_natural_sentence(str(it.get("text") or "")):
            continue
        kept.append({
            **it,
            "tier": _clamp_tier(it.get("tier")),
            "grammar_point": (it.get("grammar_point") or "")[:120],
        })
    return _sort_by_gradient(kept) if kept else None


async def _cache_put(
    db: AsyncSession, *, key: str, unit_id: uuid.UUID, grade: str | None,
    items: list[dict[str, Any]],
) -> None:
    from app.models.d29_unit_ls_understand import UnitLsUnderstandCache
    payload = {
        "items": [
            {
                "text": it["text"],
                "translation": it.get("translation") or "",
                "why": it.get("why") or "",
                "src": it.get("src") or "extract",
                "difficulty": it.get("difficulty"),
                "tier": _clamp_tier(it.get("tier")),
                "grammar_point": (it.get("grammar_point") or "")[:120],
            }
            for it in items
        ]
    }
    stmt = pg_insert(UnitLsUnderstandCache).values(
        input_md5=key, unit_id=unit_id, grade=grade, result=payload,
    ).on_conflict_do_update(
        index_elements=["input_md5"],
        set_={"unit_id": unit_id, "grade": grade, "result": payload},
    )
    await db.execute(stmt)


async def _replace_unit_rows(
    db: AsyncSession, *, unit_id: uuid.UUID, course_md5: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from app.models.d29_unit_ls_understand import UnitUnderstandLs
    await db.execute(sa.delete(UnitUnderstandLs).where(UnitUnderstandLs.unit_id == unit_id))
    out: list[dict[str, Any]] = []
    for i, it in enumerate(items):
        row = UnitUnderstandLs(
            id=uuid.uuid4(),
            unit_id=unit_id,
            text=it["text"],
            translation=(it.get("translation") or None),
            why=(it.get("why") or None),
            src=it.get("src") or "extract",
            difficulty=it.get("difficulty"),
            tier=_clamp_tier(it.get("tier")),
            grammar_point=(it.get("grammar_point") or None) or None,
            sort_order=i,
            course_text_md5=course_md5,
        )
        db.add(row)
        out.append(_row_out(row))
    await db.flush()
    return out


async def list_unit_understand_ls(db: AsyncSession, *, unit_id: uuid.UUID) -> dict[str, Any]:
    from app.models.d4_knowledge import CurriculumUnit
    from app.models.d29_unit_ls_understand import UnitUnderstandLs
    unit = await db.get(CurriculumUnit, unit_id)
    rows = (await db.execute(
        sa.select(UnitUnderstandLs)
        .where(UnitUnderstandLs.unit_id == unit_id)
        .order_by(UnitUnderstandLs.sort_order, UnitUnderstandLs.created_at)
    )).scalars().all()
    items = [_row_out(r) for r in rows]
    n_ex = sum(1 for x in items if x["src"] == "extract")
    n_syn = sum(1 for x in items if x["src"] == "synth")
    return {
        "items": items,
        "total": len(items),
        "extract_count": n_ex,
        "synth_count": n_syn,
        "grade": (unit.grade if unit else "") or "",
    }


async def generate_unit_understand_ls(
    db: AsyncSession, *, unit_id: uuid.UUID, force: bool = False,
) -> dict[str, Any]:
    """一次 LLM 抽取≤8 句或合成 5–8 句。须已保存 course_text。截断不升档。"""
    from app.models.d4_knowledge import CurriculumUnit
    from app.services.long_sentence_service import _stage_from_grade

    unit = await db.get(CurriculumUnit, unit_id)
    if unit is None:
        raise AppError(code=404, message="单元不存在")
    course_text = (getattr(unit, "course_text", None) or "").strip()
    if not course_text:
        raise AppError(code=400, message="请先在「粘贴原文」保存课文")

    grade = unit.grade
    stage = _stage_from_grade(grade)
    grammar_names = await _grammar_scope_names(db, unit_id)
    key = _input_key(course_text, grade, grammar_names)
    course_md5 = _md5(course_text)

    cached_hit = False
    items: list[dict[str, Any]] | None = None
    if not force:
        items = await _cache_get(db, key)
        if items is not None:
            cached_hit = True

    if items is None:
        items = await _llm_extract_or_synth(
            grade=grade, stage=stage, grammar_names=grammar_names,
            course_text=course_text,
        )
        mode = "llm"
        items = _sort_by_gradient(items)
        await _cache_put(db, key=key, unit_id=unit_id, grade=grade, items=items)
        _log.info(
            "unit_ls_understand generate unit=%s mode=%s n=%d cache_write",
            unit_id, mode, len(items),
        )
    else:
        mode = "cache"
        items = _sort_by_gradient(items)
        _log.info("unit_ls_understand cache hit unit=%s n=%d", unit_id, len(items))

    rows = await _replace_unit_rows(
        db, unit_id=unit_id, course_md5=course_md5, items=items)
    await db.commit()
    n_ex = sum(1 for x in rows if x["src"] == "extract")
    n_syn = sum(1 for x in rows if x["src"] == "synth")
    return {
        "items": rows,
        "total": len(rows),
        "extract_count": n_ex,
        "synth_count": n_syn,
        "mode": "extract" if n_ex and not n_syn else ("synth" if n_syn and not n_ex else "mixed"),
        "cached": cached_hit,
        "grade": grade or "",
        "grammar_scope": grammar_names,
    }


async def update_unit_understand_ls(
    db: AsyncSession, *, unit_id: uuid.UUID, item_id: uuid.UUID,
    text: str | None = None, translation: str | None = None, why: str | None = None,
) -> dict[str, Any]:
    from app.models.d29_unit_ls_understand import UnitUnderstandLs
    row = await db.get(UnitUnderstandLs, item_id)
    if row is None or row.unit_id != unit_id:
        raise AppError(code=404, message="长难句不存在")
    if text is not None:
        t = text.strip()
        if not t:
            raise AppError(code=400, message="句子不能为空")
        row.text = t
        try:
            from app.services.long_sentence_service import syntactic_complexity
            row.difficulty = syntactic_complexity(t).get("difficulty")
        except Exception:  # noqa: BLE001
            pass
    if translation is not None:
        row.translation = translation.strip() or None
    if why is not None:
        row.why = why.strip() or None
    await db.commit()
    await db.refresh(row)
    return _row_out(row)


async def delete_unit_understand_ls(
    db: AsyncSession, *, unit_id: uuid.UUID, item_id: uuid.UUID,
) -> dict[str, Any]:
    from app.models.d29_unit_ls_understand import UnitUnderstandLs
    row = await db.get(UnitUnderstandLs, item_id)
    if row is None or row.unit_id != unit_id:
        raise AppError(code=404, message="长难句不存在")
    await db.delete(row)
    await db.commit()
    return {"id": str(item_id), "deleted": True}
