"""固化阅读理解(rc)/听力(lt)/作文(wr)考点结构进知识图谱;删除旧「篇章」(k-3)。

依据:课标2022 理解性/表达性技能 + 中考阅读/听力题型、书面表达评分标准 + 常考体裁。
幂等:已存在的 code 跳过;k-3 子树若在则 FK 安全删除。系统未上线,可重复 upgrade。

Revision ID: m100_rc_lt_wr_kp
Revises: m99_tag_stage
Create Date: 2026-06-20
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "m100_rc_lt_wr_kp"
down_revision = "m99_tag_stage"
branch_labels = None
depends_on = None

# (code, name, parent_code, applicable_stages, sort_order);父在子前
NODES = [
    ('lt', '听力', None, None, 0),
    ('lt-1', '细节信息听辨', 'lt', None, 1),
    ('lt-1-1', '时间与日期', 'lt-1', ['初'], 1),
    ('lt-1-2', '数字·价格·数量', 'lt-1', ['初'], 2),
    ('lt-1-3', '地点与方向', 'lt-1', ['初'], 3),
    ('lt-1-4', '人物与事件', 'lt-1', ['初'], 4),
    ('lt-2', '主旨大意', 'lt', None, 2),
    ('lt-2-1', '对话主题', 'lt-2', ['初'], 1),
    ('lt-2-2', '独白与短文主旨', 'lt-2', ['初'], 2),
    ('lt-3', '推理判断', 'lt', None, 3),
    ('lt-3-1', '说话者身份与关系', 'lt-3', ['初'], 1),
    ('lt-3-2', '谈话场所与情景', 'lt-3', ['初'], 2),
    ('lt-3-3', '说话者意图与目的', 'lt-3', ['初'], 3),
    ('lt-3-4', '观点态度与情感', 'lt-3', ['初'], 4),
    ('lt-4', '信息处理与计算', 'lt', None, 4),
    ('lt-4-1', '数字与时间运算', 'lt-4', ['初'], 1),
    ('lt-4-2', '比较与筛选', 'lt-4', ['初'], 2),
    ('lt-4-3', '同义转换', 'lt-4', ['初'], 3),
    ('lt-5', '情景反应', 'lt', ['初'], 5),
    ('lt-6', '语音听辨', 'lt', None, 6),
    ('lt-6-1', '连读与弱读', 'lt-6', ['初'], 1),
    ('lt-6-2', '失爆与同化', 'lt-6', ['初'], 2),
    ('lt-6-3', '相似音与语调辨别', 'lt-6', ['初'], 3),
    ('rc', '阅读理解', None, None, 0),
    ('rc-1', '细节理解', 'rc', None, 1),
    ('rc-1-1', '直接信息查找(5W1H/数字时间)', 'rc-1', ['初'], 1),
    ('rc-1-2', '同义转换(原文改写匹配)', 'rc-1', ['初'], 2),
    ('rc-1-3', '图表与非连续文本信息', 'rc-1', ['初'], 3),
    ('rc-2', '主旨大意', 'rc', None, 2),
    ('rc-2-1', '段落大意', 'rc-2', ['初'], 1),
    ('rc-2-2', '全文主旨与中心思想', 'rc-2', ['初'], 2),
    ('rc-2-3', '标题归纳', 'rc-2', ['初'], 3),
    ('rc-3', '推理判断', 'rc', None, 3),
    ('rc-3-1', '事实推断', 'rc-3', ['初'], 1),
    ('rc-3-2', '写作目的与作者意图', 'rc-3', ['初'], 2),
    ('rc-3-3', '文章出处与读者对象', 'rc-3', ['初'], 3),
    ('rc-4', '词义猜测', 'rc', None, 4),
    ('rc-4-1', '据上下文猜词义', 'rc-4', ['初'], 1),
    ('rc-4-2', '据构词法猜词义', 'rc-4', ['初'], 2),
    ('rc-4-3', '代词指代', 'rc-4', ['初'], 3),
    ('rc-5', '观点态度', 'rc', None, 5),
    ('rc-5-1', '作者态度(支持/反对/中立)', 'rc-5', ['初'], 1),
    ('rc-5-2', '人物情感与观点', 'rc-5', ['初'], 2),
    ('rc-6', '篇章结构与衔接', 'rc', None, 6),
    ('rc-6-1', '逻辑关系(因果/转折/对比/顺序)', 'rc-6', ['初'], 1),
    ('rc-6-2', '句子还原与段落排序', 'rc-6', ['初'], 2),
    ('rc-6-3', '指代与衔接', 'rc-6', ['初'], 3),
    ('wr', '作文', None, None, 0),
    ('wr-1', '内容要点', 'wr', None, 1),
    ('wr-1-1', '审题与要点提取', 'wr-1', ['初'], 1),
    ('wr-1-2', '要点齐全与切题', 'wr-1', ['初'], 2),
    ('wr-1-3', '内容拓展与细节', 'wr-1', ['初'], 3),
    ('wr-2', '语言准确性', 'wr', None, 2),
    ('wr-2-1', '时态与主谓一致', 'wr-2', ['初'], 1),
    ('wr-2-2', '词汇拼写与词性', 'wr-2', ['初'], 2),
    ('wr-2-3', '句子结构正确(无残缺/杂糅)', 'wr-2', ['初'], 3),
    ('wr-2-4', '标点与大小写', 'wr-2', ['初'], 4),
    ('wr-3', '语言丰富性', 'wr', None, 3),
    ('wr-3-1', '高级词汇与短语', 'wr-3', ['初'], 1),
    ('wr-3-2', '复合句与从句', 'wr-3', ['初'], 2),
    ('wr-3-3', '特殊句式(强调/倒装/感叹)', 'wr-3', ['初'], 3),
    ('wr-4', '结构与连贯', 'wr', None, 4),
    ('wr-4-1', '篇章结构(开头-主体-结尾/分段)', 'wr-4', ['初'], 1),
    ('wr-4-2', '逻辑连贯与过渡(连接词)', 'wr-4', ['初'], 2),
    ('wr-4-3', '句数与详略控制', 'wr-4', ['初'], 3),
    ('wr-5', '书写规范', 'wr', ['初'], 5),
    ('wr-6', '体裁与格式', 'wr', None, 6),
    ('wr-6-1', '书信与电子邮件(五要素格式)', 'wr-6', ['初'], 1),
    ('wr-6-2', '通知与便条', 'wr-6', ['初'], 2),
    ('wr-6-3', '日记', 'wr-6', ['初'], 3),
    ('wr-6-4', '看图与记叙文', 'wr-6', ['初'], 4),
    ('wr-6-5', '话题与议论文', 'wr-6', ['初'], 5),
]
ROOT_CODES = ("rc", "lt", "wr")


def _fk_safe_delete(bind, ids):
    """删 knowledge_nodes 行前,清掉所有指向它们的外键子行(parent_id 除外)。"""
    if not ids:
        return
    fks = bind.execute(sa.text("""
        select tc.table_name, kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu on tc.constraint_name=kcu.constraint_name
        join information_schema.constraint_column_usage ccu on tc.constraint_name=ccu.constraint_name
        where tc.constraint_type='FOREIGN KEY' and ccu.table_name='knowledge_nodes'
          and kcu.column_name <> 'parent_id'
    """)).all()
    for t, c in fks:
        bind.execute(sa.text(f"delete from {t} where {c} = any(:ids)"), {"ids": ids})


def upgrade() -> None:
    bind = op.get_bind()
    # 1) 删旧「篇章」(k-3)子树(被 rc 取代)
    kids = bind.execute(sa.text("""
        with recursive t as (
            select id from knowledge_nodes where code = 'k-3'
            union all select k.id from knowledge_nodes k join t on k.parent_id = t.id
        ) select id from t
    """)).scalars().all()
    if kids:
        _fk_safe_delete(bind, list(kids))
        # 叶子在前:循环删到空(子树不深)
        for _ in range(8):
            bind.execute(sa.text(
                "delete from knowledge_nodes where id = any(:ids) and id not in "
                "(select parent_id from knowledge_nodes where parent_id = any(:ids))"),
                {"ids": list(kids)})

    # 2) 幂等建 rc/lt/wr:已存在 code 跳过;父在子前,按 code 查父 id
    code2id = {}
    for code, name, parent, stages, sort in NODES:
        row = bind.execute(sa.text("select id from knowledge_nodes where code=:c"), {"c": code}).first()
        if row:
            code2id[code] = row[0]
            continue
        pid = code2id.get(parent)
        if parent and pid is None:
            r2 = bind.execute(sa.text("select id from knowledge_nodes where code=:c"), {"c": parent}).first()
            pid = r2[0] if r2 else None
        nid = uuid.uuid4()
        bind.execute(sa.text("""
            insert into knowledge_nodes(id, axis, parent_id, name, code, applicable_stages, status, source, sort_order)
            values(:id, 'knowledge', :pid, :name, :code, cast(:stages as jsonb), 'active', 'exam', :sort)
        """), {"id": nid, "pid": pid, "name": name, "code": code,
               "stages": (None if stages is None else __import__('json').dumps(stages)), "sort": sort})
        code2id[code] = nid


def downgrade() -> None:
    bind = op.get_bind()
    ids = bind.execute(sa.text("""
        with recursive t as (
            select id from knowledge_nodes where code = any(:roots)
            union all select k.id from knowledge_nodes k join t on k.parent_id = t.id
        ) select id from t
    """), {"roots": list(ROOT_CODES)}).scalars().all()
    if ids:
        _fk_safe_delete(bind, list(ids))
        for _ in range(8):
            bind.execute(sa.text(
                "delete from knowledge_nodes where id = any(:ids) and id not in "
                "(select parent_id from knowledge_nodes where parent_id = any(:ids))"),
                {"ids": list(ids)})
