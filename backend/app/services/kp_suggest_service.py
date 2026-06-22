"""真题 → 受控考点 AI 建议(母题挂 KP 提效)。

KV 缓存优化(https://api-docs.deepseek.com/zh-cn/guides/kv_cache):
把**稳定不变的「知识点目录(仅编码+名称,不含详解正文)」放进 system 消息当缓存前缀**——
无论哪个题型、哪份卷,该前缀逐 token 一致 → 命中 DeepSeek KV 缓存;把**可变的(题型提示词
+ 本大题短文 + 小题)放进 user 消息**(在前缀之后)。

按 question_type 分组,各用「题型 AI 提示词」(kp_prompt_service)做 user 端指引;
LLM 用短「编码/序号」回映(避免 UUID 抄错),服务端映射回真实 node_id / question_id。
建议**不自动挂**,返回 {question_id: [(node_id, name, code)]}。dev-mock 跳过 LLM。
"""
from __future__ import annotations

import asyncio
import json
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformPaper, PlatformQuestion, PlatformQuestionKp, Passage
from app.services import kp_prompt_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

# 学段包含关系:高 ⊇ 初 ⊇ 小。匹配某学段卷时,该学段「及更低」的考点都算候选。
_STAGE_RANK = {"小": 0, "初": 1, "高": 2}


def _stages_at_or_below(stage: str | None) -> list[str] | None:
    """某学段可用的考点学段集合(含更低)。None=不限(返回 None 表示不过滤)。"""
    pr = _STAGE_RANK.get(stage or "")
    if pr is None:
        return None
    return [s for s, r in _STAGE_RANK.items() if r <= pr]


def _stage_allows(cand_stages: list | None, allowed: list[str] | None) -> bool:
    """考点是否适用:通用(未标)恒可;否则其任一学段落在 allowed 集合内。"""
    if allowed is None or not cand_stages:
        return True
    return any(s in allowed for s in cand_stages)

# system 前缀固定开头(与目录拼成稳定缓存前缀)
_SYS_HEAD = (
    "你是初中英语考点标注专家。下面给出受控「知识点目录」,每行:编码<TAB>名称。\n"
    "规则:只能从该目录为题目挑考点并返回其编码;不得编造目录外的编码;每道小题最多挑 2 个"
    "最贴切的考点,无明确考点给空数组。严格输出 JSON,不要任何解释。\n\n【知识点目录】\n"
)


async def _load_catalog(db: AsyncSession) -> tuple[dict, list[tuple]]:
    """考点目录。返回 (code2node, entries[(node_id, code, 行文本, 适用学段)])。

    每行只含「编码<TAB>名称」——**不带 node_resource 详解内容**(避免请求臃肿/破坏缓存)。
    考点口径 = 受控知识树里**有父且无子的叶子节点**(分类/中间节点不入目录)。
    """
    child = aliased(KnowledgeNode)
    is_leaf = ~sa.exists().where(child.parent_id == KnowledgeNode.id)
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
                  KnowledgeNode.applicable_stages)
        .where(KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active",
               KnowledgeNode.parent_id.isnot(None), is_leaf)
        .order_by(KnowledgeNode.code)
    )).all()
    code2node: dict[str, tuple[uuid.UUID, str]] = {}
    entries: list[tuple] = []
    for nid, nm, code, stages in rows:
        if code in code2node:
            continue
        code2node[code] = (nid, nm)
        entries.append((nid, code, f"{code}\t{nm}", stages or []))
    return code2node, entries


async def _load_categories(db: AsyncSession) -> tuple[dict, str]:
    """可挂分类 = 受控树里**有子节点的(非叶)**节点(供"新建考点"提议选归属)。
    返回 (code2node{code:(id,name)}, lines="code<TAB>名称\\n...")。"""
    child = aliased(KnowledgeNode)
    has_child = sa.exists().where(child.parent_id == KnowledgeNode.id)
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
        .where(KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active", has_child)
        .order_by(KnowledgeNode.code))).all()
    code2node = {code: (nid, nm) for nid, nm, code in rows}
    lines = "\n".join(f"{code}\t{nm}" for nid, nm, code in rows)
    return code2node, lines


async def _descendant_node_ids(db: AsyncSession, root_ids: list) -> set | None:
    """关注分类 → 该分类**整棵子树**的全部节点 id(含自身)。空=不限(返回 None)。

    按 parent_id 树展开(而非 code 前缀):手动建的分类(m-*/k-* code)也能正确囊括其后代考点。
    """
    roots = [r for r in root_ids if r]
    if not roots:
        return None
    sql = sa.text("""
        WITH RECURSIVE t AS (
            SELECT id FROM knowledge_nodes WHERE id = ANY(:roots)
            UNION ALL
            SELECT k.id FROM knowledge_nodes k JOIN t ON k.parent_id = t.id
        ) SELECT id FROM t
    """)
    rows = (await db.execute(sql, {"roots": [str(r) for r in roots]})).all()
    return {r[0] for r in rows}


def _system_for(entries: list[tuple], allowed_node_ids: set | None,
                stage: str | None = None) -> str:
    """过滤考点目录拼稳定 system 前缀。allowed_node_ids=关注分类子树节点集(None=全部);
    stage=题/卷学段过滤,包含式(高⊇初⊇小):该学段及更低的考点 + 通用考点都纳入。"""
    allowed_stages = _stages_at_or_below(stage)
    lines: list[str] = []
    for nid, _code, ln, stages in entries:
        if allowed_node_ids is not None and nid not in allowed_node_ids:
            continue
        if not _stage_allows(stages, allowed_stages):
            continue
        lines.append(ln)
    return _SYS_HEAD + "\n".join(lines)


async def _passages_for(db: AsyncSession, block_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = list({b for b in block_ids if b})
    if not ids:
        return {}
    rows = (await db.execute(sa.select(Passage.id, Passage.text).where(Passage.id.in_(ids)))).all()
    return {pid: (txt or "") for pid, txt in rows}


async def _suggest_group(group: list[PlatformQuestion], code2node: dict, system_msg: str,
                         type_prompt: str, passages: dict[uuid.UUID, str],
                         min_kp: int = 0, max_kp: int = 2,
                         cat_lines: str = "", cat_code2node: dict | None = None,
                         ) -> tuple[dict[uuid.UUID, list[tuple]], dict[uuid.UUID, list[tuple]]]:
    """同题型一组题调一次 LLM(system=稳定目录前缀,user=题型提示词+短文+小题)。

    返回 (matches, proposals):
      matches[qid]   = [(node_id, name, code)]      命中的现有考点
      proposals[qid] = [(name, parent_node_id, parent_name)]  目录无对应 → 建议新建考点+归属分类
    """
    out: dict = {q.id: [] for q in group}
    proposals: dict = {q.id: [] for q in group}
    cat_code2node = cat_code2node or {}
    # 短 id(question_id 前 8 位 hex)做小题标识——不与题干里的题号(8.9.…)相混
    by_qid: dict[str, PlatformQuestion] = {}
    for q in group:
        k = str(q.id)[:8]
        while k in by_qid:          # 极罕见前缀碰撞 → 加长
            k = str(q.id)[:len(k) + 4]
        by_qid[k] = q
    q_qid = {q.id: k for k, q in by_qid.items()}

    # 本组涉及的短文,按 A/B/C 标号(供小题引用)
    blk_label: dict[uuid.UUID, str] = {}
    for q in group:
        if q.block_id and q.block_id in passages and q.block_id not in blk_label:
            blk_label[q.block_id] = chr(ord("A") + len(blk_label))
    # 材料给足上下文:短文填空/完型常 1000-2000 字,且空号(如 ____59____)散落全篇,
    # 截太短会让靠后的空(60/61/62…)看不到上下文而漏挂。放到 2400 字符。
    mat = "".join(f"[材料{lab}] {passages[bid][:2400]}\n"
                  for bid, lab in blk_label.items())

    qlines = "\n".join(
        f"qid={q_qid[q.id]}\t[{q.section or ''}{('·材料' + blk_label[q.block_id]) if q.block_id in blk_label else ''}]\t"
        f"{(q.stem or '').replace(chr(10), ' ')[:160]}"
        for q in group)

    cnt = ((f"每题挑 {min_kp}-{max_kp} 个" if min_kp else f"每题挑至多 {max_kp} 个")
           + "最贴切考点;**不要硬凑**,无贴切考点就给 [](随后可用 propose 建议新建)。")
    nq = len(group)
    # 缺口建议:目录里没有合适考点但该题确有明确考点时,提议新建考点并归到某分类
    gap = ("\n\n【可挂分类(catCode<TAB>名称)——仅当目录无现成考点、但本题确有明确考点时,"
           "用 propose 提议新建一个考点并归到最贴切的分类】\n" + cat_lines) if cat_lines else ""
    propose_spec = (',"propose":{"name":"建议新建的考点名","cat":"归属分类catCode"}'
                    if cat_lines else "")
    user = (
        f"{type_prompt}\n{cnt}\n\n"
        + (f"【本大题短文/材料】\n{mat}\n" if mat else "")
        + f"【小题(qid<TAB>[大题·材料]<TAB>题干)】\n{qlines}\n"
        + gap + "\n\n"
        f'返回 JSON:{{"items":[{{"qid":"小题qid","codes":["编码",...]{propose_spec}}}]}}。'
        f'**必须为上面全部 {nq} 道小题各返回一条**(逐一判断,无考点才给 codes:[]),不得遗漏任何 qid;'
        'qid 原样回传,codes 只用目录里的编码;propose 仅在 codes 为空且确有明确考点时给(否则省略)。'
    )
    try:
        resp = await chat_completion(
            system_prompt=system_msg, user_prompt=user, max_tokens=4096,
            response_format={"type": "json_object"}, temperature=0.0)
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return out, proposals
    for it in (data.get("items") or []):
        q = by_qid.get(str(it.get("qid")))
        if q is None:
            continue
        seen: set[uuid.UUID] = set()
        for code in (it.get("codes") or [])[:max_kp]:
            ref = code2node.get(code)
            if ref and ref[0] not in seen:
                seen.add(ref[0])
                out[q.id].append((ref[0], ref[1], code))
        # 无命中且 AI 给了 propose → 收为"新建考点"建议(解析归属分类)
        pr = it.get("propose")
        if not out[q.id] and isinstance(pr, dict) and (pr.get("name") or "").strip():
            cat = cat_code2node.get(str(pr.get("cat")))
            proposals[q.id].append(
                (pr["name"].strip()[:60], cat[0] if cat else None, cat[1] if cat else None))
    return out, proposals


async def suggest_kps_for_text(
    db: AsyncSession, text: str, *, source_type: str = "教材·其他", stage: str | None = None,
) -> list[tuple[uuid.UUID, str, str]]:
    """一段正文(教材等)→ 受控考点建议。用该来源类型的提示词 + 关注分类 + 学段过滤目录。"""
    if not (text or "").strip() or is_llm_dev_mode():
        return []
    code2node, entries = await _load_catalog(db)
    prompts = await kp_prompt_service.get_prompts(db)
    item = kp_prompt_service.default_item_for(prompts, source_type)
    allowed = await _descendant_node_ids(db, item.get("focus_node_ids") or [])
    system_msg = _system_for(entries, allowed, stage)
    max_kp = int(item.get("max_kp", 8))
    user = (
        f"{item['text']}\n挑出正文覆盖到的考点(至多 {max_kp} 个)。\n\n【正文】\n{text[:4000]}\n\n"
        '返回 JSON:{"codes":["编码",...]};只用目录里的编码。'
    )
    try:
        resp = await chat_completion(system_prompt=system_msg, user_prompt=user,
                                     max_tokens=2048, response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for code in (data.get("codes") or [])[:max_kp]:
        ref = code2node.get(code)
        if ref and ref[0] not in seen:
            seen.add(ref[0])
            out.append((ref[0], ref[1], code))
    return out


_PASSAGE_ROOT = {"听力": "lt", "阅读": "rc", "写作": "wr"}

# 短文本身只标「内容类」考点(主题/主旨/关键信息/场景人物/篇章结构);
# 「答题技能类」考点(同义转换/推断/筛选/运算/词义猜测/情景反应)需配题目才能考查,
# 对原始短文是过度匹配 → 从板块候选里排除。仅用于短文匹配,真题题目不受影响。
_PASSAGE_SKILL_EXCLUDE = {
    "lt-4",      # 听力·信息处理与计算(数字运算/比较筛选/同义转换)
    "lt-5",      # 听力·情景反应
    "rc-3",      # 阅读·推理判断
    "rc-4",      # 阅读·词义猜测
    "rc-1-2",    # 阅读·同义转换(原文改写匹配)
}


async def suggest_kps_for_passage(
    db: AsyncSession, text: str, kind: str, *, max_kp: int | None = None,
) -> list[tuple[uuid.UUID, str, str]]:
    """单元短文 → 关联考点。**两段式**(各自目录干净,比混在一起单次调用更稳):

    1) 板块考点:按 kind 限定子树(听力→lt-*/阅读→rc-*/写作→wr-*),用「教材·{kind}」板块提示词。
    2) 额外类别:若「关注分类」配了板块之外的分类(如给短文加词法/句法),再聚焦挑一次该短文
       **实际体现**的语言点考点。

    实测:混在一个 434 项的大目录里单次问,AI 经常对阅读/写作返回空;拆成两次聚焦后都稳定。
    """
    root_code = _PASSAGE_ROOT.get(kind)
    if not (text or "").strip() or not root_code or is_llm_dev_mode():
        return []
    code2node, entries = await _load_catalog(db)
    prompts = await kp_prompt_service.get_prompts(db)
    item = kp_prompt_service.default_item_for(prompts, f"教材·{kind}")
    cap = max_kp if max_kp is not None else int(item.get("max_kp", 3))
    snippet = text[:3000]

    out: list[tuple[uuid.UUID, str, str]] = []
    seen: set = set()

    async def _collect(allowed: set | None, user_prompt: str) -> None:
        if not allowed:
            return
        system_msg = _system_for(entries, allowed, None)
        try:
            # temperature=0:让短文→考点匹配尽量确定,避免同短文 run-to-run 飘(时有时无)
            resp = await chat_completion(system_prompt=system_msg, user_prompt=user_prompt,
                                         max_tokens=1024, response_format={"type": "json_object"},
                                         temperature=0.0)
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception:  # noqa: BLE001
            return
        for code in (data.get("codes") or []):
            ref = code2node.get(code)
            if ref and ref[0] not in seen:
                seen.add(ref[0])
                out.append((ref[0], ref[1], code))

    # ① 板块本身考点(lt/rc/wr)
    root_id = (await db.execute(sa.select(KnowledgeNode.id)
                                .where(KnowledgeNode.code == root_code))).scalar_one_or_none()
    board_allowed = await _descendant_node_ids(db, [root_id]) if root_id else None
    # 收紧:短文只挂内容类考点,排除答题技能类子树
    if board_allowed:
        excl_ids = [r[0] for r in (await db.execute(
            sa.select(KnowledgeNode.id).where(KnowledgeNode.code.in_(_PASSAGE_SKILL_EXCLUDE))
        )).all()]
        if excl_ids:
            board_allowed = board_allowed - (await _descendant_node_ids(db, excl_ids) or set())
    await _collect(board_allowed,
        f"{item['text']}\n挑最贴切的{kind}考点(至多 {cap} 个);**不要硬凑**,无贴切考点就给空数组。\n\n"
        f"【{kind}材料】\n{snippet}\n\n"
        '返回 JSON:{"codes":["编码",...]};只用目录里的编码。')

    # ② 关注分类里超出本板块根的额外类别(如 词法/句法),聚焦再挑一次
    focus_ids = item.get("focus_node_ids") or []
    extra = [(r[0], r[1]) for r in (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name)
        .where(KnowledgeNode.id.in_(focus_ids), KnowledgeNode.code != root_code)
    )).all()] if focus_ids else []
    extra_allowed = await _descendant_node_ids(db, [e[0] for e in extra]) if extra else None
    if extra_allowed:
        names = "、".join(e[1] for e in extra)
        await _collect(extra_allowed,
            f"下面是一篇英语{kind}材料。目录里都是「{names}」方面的语言点考点。"
            f"请挑出材料中**确实体现**的语言点考点(至多 {cap} 个;确实没有就给空数组,不要硬凑)。\n\n"
            f"【材料】\n{snippet}\n\n"
            '返回 JSON:{"codes":["编码",...]};只用目录里的编码。')

    return out[:cap]


async def suggest_kps_for_paper(
    db: AsyncSession, paper_id: uuid.UUID, *,
    sections: list[str] | None = None, prompt_id: str | None = None,
    skip_attached: bool = False,
) -> tuple[dict[uuid.UUID, list[tuple]], dict[uuid.UUID, list[tuple]]]:
    """按题型分组建议考点;每题型用其(默认/指定)提示词 + 关注分类过滤目录。

    skip_attached=True(整卷匹配用):跳过**已挂考点的题**,只补未挂的,避免重复匹配;
    单题型「一键挂」传 False,可对该题型全部重跑。

    返回 (matches, proposals):matches[qid]=[(node_id,name,code)];
    proposals[qid]=[(新考点名, 归属分类node_id, 归属分类名)]——目录无对应时 AI 的"新建考点"建议。
    """
    stmt = sa.select(PlatformQuestion).where(
        PlatformQuestion.paper_id == paper_id, PlatformQuestion.type == "real")
    if sections:
        stmt = stmt.where(PlatformQuestion.section.in_(sections))
    qs = list((await db.execute(stmt)).scalars().all())
    if skip_attached and qs:
        attached = set((await db.execute(
            sa.select(PlatformQuestionKp.question_id)
            .where(PlatformQuestionKp.question_id.in_([q.id for q in qs]))
        )).scalars().all())
        qs = [q for q in qs if q.id not in attached]
    if not qs or is_llm_dev_mode():
        return {q.id: [] for q in qs}, {}

    code2node, entries = await _load_catalog(db)
    cat_code2node, cat_lines = await _load_categories(db)
    passages = await _passages_for(db, [q.block_id for q in qs])
    prompts = await kp_prompt_service.get_prompts(db)
    override = kp_prompt_service.item_by_id(prompts, prompt_id) if prompt_id else None
    # 卷的学段(优先卷,回退小题)→ 候选考点按学段软过滤(未标学段=通用)
    stage = (await db.execute(sa.select(PlatformPaper.stage)
                              .where(PlatformPaper.id == paper_id))).scalar_one_or_none()
    if not stage:
        stage = next((q.stage for q in qs if getattr(q, "stage", None)), None)

    def _etype(q: PlatformQuestion) -> str:
        # 题型优先按 section 关键字细分(短文填空/单词检测/句子翻译/听力 各自独立配提示词),
        # 否则回退 question_type。
        sec = q.section or ""
        if "听力" in sec:
            return "听力"
        if "短文填空" in sec:
            return "短文填空"
        if "单词检测" in sec or "词汇检测" in sec:
            return "单词检测"
        if "句子翻译" in sec or "翻译" in sec:
            return "句子翻译"
        qt = q.question_type or ""
        # 命中已配置题型则用之,否则归到「其他」兜底配置(避免未适配题型乱挂到单选)
        return qt if qt in kp_prompt_service.QUESTION_TYPES else "其他"

    groups: dict[str, list[PlatformQuestion]] = {}
    for q in qs:
        groups.setdefault(_etype(q), []).append(q)

    # 两段式触发条件(按「至多」考点数):
    #   · 至多 = 1     → 一段式:关注分类取并集,一次问挑最贴切的 1 个(避免段数把上限翻倍)。
    #   · 至多 > 1 且关注分类 ≥ 2 → 两段式:按配置顺序(主→次)每个分类各聚焦匹配一段,合并后按至多截断。
    # 拆段的原因:多分类混在一个大目录里单次问,AI 易漏/飘;各自干净目录分别匹配再合并更稳。
    # 串行预算:并行期各组共用同一 db session,不能并发查询,故先把子树都算好再并行调模型。
    items = {qt: (override or kp_prompt_service.default_item_for(prompts, qt)) for qt in groups}
    focus_split: dict[str, list[set | None]] = {}
    for qt, it in items.items():
        fids = it.get("focus_node_ids") or []
        if int(it.get("max_kp", 2)) <= 1 or len(fids) <= 1:
            focus_split[qt] = [await _descendant_node_ids(db, fids)]      # 一段式:0→[None](全部)/ 多分类→[并集]
        else:
            focus_split[qt] = [await _descendant_node_ids(db, [fid]) for fid in fids]  # 两段式:每分类一段(主→次)

    async def _run_group(qtype: str, group: list[PlatformQuestion], it: dict) -> tuple[dict, dict]:
        splits = focus_split[qtype]
        mn, mx = int(it.get("min_kp", 0)), int(it.get("max_kp", 2))
        if len(splits) == 1:                                  # 单段(0/1 个关注分类):原逻辑
            system_msg = _system_for(entries, splits[0], stage)
            return await _suggest_group(group, code2node, system_msg, it["text"], passages,
                                        mn, mx, cat_lines, cat_code2node)
        # 两段式:每个关注分类各聚焦匹配一次,合并 per-qid 考点(去重),让词法/句法等都不漏
        merged: dict = {q.id: [] for q in group}
        seen: dict = {q.id: set() for q in group}
        props_acc: dict = {q.id: [] for q in group}
        for sub in splits:
            system_msg = _system_for(entries, sub, stage)
            m, p = await _suggest_group(group, code2node, system_msg, it["text"], passages,
                                        mn, mx, cat_lines, cat_code2node)
            for qid, lst in m.items():
                for ref in lst:
                    if ref[0] not in seen[qid]:
                        seen[qid].add(ref[0]); merged[qid].append(ref)
            for qid, lst in p.items():
                props_acc[qid].extend(lst)
        # max_kp 是**每题总上限**:多段合并后按 mx 截断,避免段数把上限翻倍
        for qid in merged:
            merged[qid] = merged[qid][:mx]
        # 缺口建议:仅当某题在所有段都没匹配到考点时保留(按建议名去重)
        props: dict = {}
        for qid, plist in props_acc.items():
            if merged[qid] or not plist:
                continue
            dedup, seen_name = [], set()
            for pr in plist:
                if pr[0] not in seen_name:
                    seen_name.add(pr[0]); dedup.append(pr)
            props[qid] = dedup
        return merged, props

    # 各题型分组**并行**调用大模型:墙钟时间 = 最慢一组,而非求和(整卷不再超时)
    out: dict[uuid.UUID, list[tuple]] = {q.id: [] for q in qs}
    proposals: dict[uuid.UUID, list[tuple]] = {}
    results = await asyncio.gather(
        *(_run_group(qtype, group, items[qtype]) for qtype, group in groups.items()),
        return_exceptions=True)
    for r in results:
        if isinstance(r, tuple):     # (matches, proposals);单组失败(异常)跳过,不拖垮整卷
            out.update(r[0])
            proposals.update({q: v for q, v in r[1].items() if v})
    return out, proposals
