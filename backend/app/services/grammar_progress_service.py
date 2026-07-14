"""教材进度驱动的个人语法掌握模型(§P1 升级)。

个人语法树 = 组合视图,读取时拼:
  ① 当前教材进度内、从知识图谱取的语法节点(共享只读骨架);
  ② 各渠道学过且匹配上图谱的节点(掌握度走 StudentKp,R8 统一跨渠道台账);
  ③ 没匹配上图谱的个人节点(student_grammar_node)。

未学 = (进度内图谱语法节点 − 已学) ∪ 个人未学节点,按教材序排;
先修 = 教材序里排在某未学点之前、且也没学的点。顺序天然来自教材(grade→semester→unit_no),
不依赖手搓/AI 造的 prereq 边。
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.models.d17_curriculum_kg import UnitNode
from app.models.d27_student_grammar import StudentGrammarNode

_SEM_RANK = {"上": 0, "下": 1}
_MASTERED = 0.7

# 句法关键词(→ 挂 jf 顶)与词法关键词(→ 挂 cf 顶);都不含 → 判定非语法,不建个人节点。
_SYNTAX_KW = ("从句", "句型", "倒装", "强调", "虚拟", "并列", "复合句", "简单句",
              "主谓", "感叹", "疑问", "祈使", "there be", "宾语", "定语", "状语", "同位语")
_MORPH_KW = ("名词", "冠词", "代词", "数词", "形容词", "副词", "介词", "连词",
             "动词", "时态", "语态", "情态", "非谓语", "动名词", "不定式", "分词")


def _grammar_anchor(name: str) -> str | None:
    """语法名 → 挂靠顶层 code(句法 jf / 词法 cf);非语法名返回 None(不建个人节点)。"""
    n = name or ""
    if any(k in n for k in _SYNTAX_KW):
        return "jf"
    if any(k in n for k in _MORPH_KW):
        return "cf"
    return None


async def add_personal_if_grammar(db: AsyncSession, *, student_id: uuid.UUID,
                                  name: str, source: str = "upload_paper",
                                  source_paper_id: uuid.UUID | None = None) -> bool:
    """上传拆题里未命中图谱的知识点:若是语法名 → 建/保留个人语法节点(挂个人树)。返回是否建。
    命中图谱的走正常 node_id,不进这里;个人的归个人,不收编回公共图谱。
    source_paper_id:来源卷——首次建时记上,供作业精讲·语法按卷归组(旧行未记的回填一次)。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    anchor = _grammar_anchor((name or "").strip())
    if not anchor:
        return False
    norm = (name or "").strip().lower()
    if not norm:
        return False
    stmt = pg_insert(StudentGrammarNode).values(
        id=uuid.uuid4(), student_id=student_id, name=name.strip(),
        name_norm=norm, anchor_code=anchor, source=source, source_paper_id=source_paper_id)
    if source_paper_id is not None:   # 已存在但没记来源卷 → 回填(便于归组);已记的不动
        stmt = stmt.on_conflict_do_update(
            constraint="uix_student_grammar_node",
            set_={"source_paper_id": source_paper_id},
            where=(StudentGrammarNode.source_paper_id.is_(None)))
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=["student_id", "name_norm"])
    await db.execute(stmt)
    return True


def _grade_rank(g: str) -> int:
    from app.services.curriculum_service import _grade_rank_py
    return _grade_rank_py(g)


def unit_rank(grade: str | None, semester: str | None, unit_no: int | None) -> tuple:
    """教材全序排序键:(年级序, 学期序 上0下1, 单元号)。缺失单元号按学期末(大数)。"""
    return (_grade_rank(grade or ""), _SEM_RANK.get(semester or "", 9),
            unit_no if unit_no is not None else 9999)


def current_rank(student: User) -> tuple | None:
    """学生当前教材进度位置;未设年级/学期 → None(无法算未学池)。
    未设具体单元 → 视作当前学期末(纳入该学期全部单元)。"""
    if not student.preferred_grade or not student.preferred_semester:
        return None
    return unit_rank(student.preferred_grade, student.preferred_semester, student.preferred_unit_no)


async def _learned_node_ids(db: AsyncSession, *, student_id: uuid.UUID,
                            node_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """这批语法节点里学生已掌握(≥0.7)的;四维优先,回退加权。跨渠道台账 StudentKp。"""
    if not node_ids:
        return set()
    from app.services.kp_mastery_service import weighted_mastery, grammar_overrides
    codes = {nid: code for nid, code in (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.code).where(KnowledgeNode.id.in_(node_ids)))).all()}
    ov = await grammar_overrides(db, student_id=student_id,
                                 nodes_with_code=[(nid, c) for nid, c in codes.items()])
    sk_map = {sk.node_id: sk for sk in (await db.execute(
        select(StudentKp).where(StudentKp.student_id == student_id,
                                StudentKp.node_id.in_(node_ids)))).scalars().all()}
    learned: set[uuid.UUID] = set()
    for nid in node_ids:
        if nid in ov:
            m, e = ov[nid]
        elif nid in sk_map:
            sk = sk_map[nid]
            m, e = weighted_mastery(sk.fa_correct, sk.fa_wrong, sk.corrected_count, sk.redo_wrong_count)
        else:
            m, e = None, 0
        if e and m is not None and m >= _MASTERED:
            learned.add(nid)
    return learned


async def _scoped_grammar_nodes(db: AsyncSession, *, student: User) -> list[dict]:
    """当前教材+进度内的图谱语法节点(每节点取其最早出现单元的教材序)。未设进度 → []。"""
    cur = current_rank(student)
    if cur is None or not student.preferred_textbook_version:
        return []
    rows = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
               CurriculumUnit.grade, CurriculumUnit.semester, CurriculumUnit.unit_no)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .join(CurriculumUnit, CurriculumUnit.id == UnitNode.unit_id)
        .where(CurriculumUnit.textbook_version == student.preferred_textbook_version))).all()
    best: dict[uuid.UUID, dict] = {}
    for nid, name, code, grade, sem, uno in rows:
        if not (code or "").lower().startswith(("cf", "jf")):   # 严格取语法轴(cf 词法 / jf 句法)
            continue
        r = unit_rank(grade, sem, uno)
        if r > cur:                                  # 超出当前进度 → 还没到,不算
            continue
        prev = best.get(nid)
        if prev is None or r < prev["rank"]:
            best[nid] = {"node_id": str(nid), "name": name, "code": code, "rank": r}
    return list(best.values())


async def personal_grammar_tree(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """个人语法树 + 未学/已学分桶(教材进度驱动)。供学生端语法树页 & P1 升级复用。

    返回 {learned:[...], unlearned:[...], personal:[...], has_progress:bool}
      unlearned 已按教材序排;每项含 rank(仅内部排序)。
    """
    student = await db.get(User, student_id)
    if student is None:
        return {"learned": [], "unlearned": [], "personal": [], "has_progress": False}

    scoped = await _scoped_grammar_nodes(db, student=student)
    learned_ids = await _learned_node_ids(
        db, student_id=student_id, node_ids=[uuid.UUID(n["node_id"]) for n in scoped])

    learned, unlearned = [], []
    for n in scoped:
        (learned if uuid.UUID(n["node_id"]) in learned_ids else unlearned).append(n)

    # 个人节点(没匹配上图谱的):天然未学;匹配上(ref_node_id)且已学的排除,避免与图谱项重复
    prows = (await db.execute(
        select(StudentGrammarNode).where(StudentGrammarNode.student_id == student_id))).scalars().all()
    personal = []
    for p in prows:
        if p.ref_node_id and p.ref_node_id in learned_ids:
            continue
        personal.append({"personal_id": str(p.id), "name": p.name,
                         "anchor_code": p.anchor_code, "source": p.source,
                         "ref_node_id": str(p.ref_node_id) if p.ref_node_id else None,
                         "rank": (99, 9, 9999)})

    unlearned.sort(key=lambda x: x["rank"])
    learned.sort(key=lambda x: x["rank"])
    return {"learned": learned, "unlearned": unlearned + personal,
            "personal": personal, "has_progress": True}


async def grammar_tree_grouped(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """个人语法树(分组可视版):按 词法(cf)/句法(jf) → 二级分类 铺开,供学生端语法树页。

    返回 {
      has_progress, totals:{learned,unlearned},
      roots:[{code,name,learned,unlearned, cats:[{code,name,learned,unlearned,
              items:[{node_id,name,status}]}]}],   # status: learned | unlearned
      personal:[{personal_id,name,anchor,source}]  # 没匹配图谱的个人节点(自建/未收录)
    }
    """
    tree = await personal_grammar_tree(db, student_id=student_id)
    if not tree["has_progress"]:
        return {"has_progress": False, "totals": {"learned": 0, "unlearned": 0},
                "roots": [], "personal": []}

    # code → 中文名(全量 cf/jf 节点,供分类表头;332 行,便宜)
    name_by_code = dict((await db.execute(
        select(KnowledgeNode.code, KnowledgeNode.name)
        .where(KnowledgeNode.code.op("~")("^(cf|jf)")))).all())

    def _cat_code(code: str) -> str:
        parts = (code or "").split("-")
        return "-".join(parts[:2]) if len(parts) >= 2 else code

    # 组装:roots[top] -> cats[cat] -> items
    roots: dict[str, dict] = {}
    for status, bucket in (("learned", tree["learned"]),
                           ("unlearned", [n for n in tree["unlearned"] if n.get("code")])):
        for n in bucket:
            code = n["code"]
            top = code.split("-")[0]
            cat = _cat_code(code)
            root = roots.setdefault(top, {"code": top, "name": name_by_code.get(top, top),
                                          "learned": 0, "unlearned": 0, "cats": {}})
            c = root["cats"].setdefault(cat, {"code": cat, "name": name_by_code.get(cat, cat),
                                              "learned": 0, "unlearned": 0, "items": []})
            c["items"].append({"node_id": n["node_id"], "name": n["name"], "status": status})
            c[status] += 1
            root[status] += 1

    # 稳定顺序:cf 在前 jf 在后;分类按 code 排;项目按已学后置(未学在前)
    _TOP_ORDER = {"cf": 0, "jf": 1}
    roots_out = []
    for top in sorted(roots, key=lambda t: _TOP_ORDER.get(t, 9)):
        r = roots[top]
        cats = sorted(r["cats"].values(), key=lambda c: c["code"])
        for c in cats:
            c["items"].sort(key=lambda x: (x["status"] == "learned", x["name"]))
        roots_out.append({"code": r["code"], "name": r["name"],
                          "learned": r["learned"], "unlearned": r["unlearned"], "cats": cats})

    personal = [{"personal_id": p["personal_id"], "name": p["name"],
                 "anchor": p.get("anchor_code"), "source": p.get("source")}
                for p in tree["personal"]]
    return {"has_progress": True,
            "totals": {"learned": len(tree["learned"]),
                       "unlearned": len([n for n in tree["unlearned"] if n.get("code")]) + len(personal)},
            "roots": roots_out, "personal": personal}


async def prereqs_before(db: AsyncSession, *, student_id: uuid.UUID,
                         target_code: str, target_rank: tuple, limit: int = 5) -> list[dict]:
    """某未学语法点的「先修」:同一顶层大类(code 首段)里、教材序更早、且也没学的点。"""
    tree = await personal_grammar_tree(db, student_id=student_id)
    top = (target_code or "").split("-")[0]                    # cf / jf 顶层
    out = [n for n in tree["unlearned"]
           if n.get("code") and n["code"].split("-")[0] == top
           and n["rank"] < target_rank and n["code"] != target_code]
    out.sort(key=lambda x: x["rank"])
    return out[:limit]
