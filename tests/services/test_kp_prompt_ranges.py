"""kp_prompt_service:关注分类「按分类设考点数范围」(focus_ranges)的存取/校验。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services import kp_prompt_service as kps


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


def test_range_for_per_category_and_fallback():
    item = {"min_kp": 1, "max_kp": 2, "focus_ranges": {"n1": [0, 3]}}
    assert kps.range_for(item, "n1") == (0, 3)      # 单独配
    assert kps.range_for(item, "n2") == (1, 2)      # 未配 → 回退提示词级
    assert kps.range_for({"min_kp": 0, "max_kp": 5}, "x") == (0, 5)   # 无 focus_ranges 字段


async def _a_user(s) -> uuid.UUID:
    from app.models.d1_users import User
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="platform_admin"))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_save_get_focus_ranges_roundtrip(db_session):
    admin = await _a_user(db_session)
    n1, n2, n_stale = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    await kps.save_prompts(db_session, updated_by=admin, prompts=[{
        "name": "单选-测试", "text": "挑语法考点", "question_type": "单选", "is_default": True,
        "focus_node_ids": [n1, n2],
        "focus_ranges": {
            n1: [0, 3],            # 选中分类:保留
            n2: [None, 2.0],       # null/float(前端 input 可能产出)→ 清洗成 [0,2]
            n_stale: [1, 4],       # 不在 focus_node_ids → 应被丢弃
        },
        "min_kp": 1, "max_kp": 2,
    }])
    await db_session.flush()

    prompts = await kps.get_prompts(db_session)
    item = next(p for p in prompts if p.get("name") == "单选-测试")
    fr = item["focus_ranges"]
    assert fr[n1] == [0, 3]
    assert fr[n2] == [0, 2]          # null→0、2.0→2 清洗
    assert n_stale not in fr         # 未选中的分类范围被清掉
    assert kps.range_for(item, n1) == (0, 3)
    assert kps.range_for(item, "未知") == (1, 2)   # 回退提示词级


def test_make_scope():
    assert kps.make_scope("译林版", "七年级", "上") == "译林版|七年级|上"
    assert kps.make_scope("译林版", None, "上") is None     # 任一缺失 → 全局
    assert kps.make_scope("", "七年级", "上") is None


@pytest.mark.asyncio
async def test_scope_override_fallback_list_delete(db_session):
    admin = await _a_user(db_session)
    scope = f"译林版|七年级|测{uuid.uuid4().hex[:4]}"

    # 1) 没定制 → get(scope) 回退全局/内置(与 get(None) 同结构,含全部题型)
    base = await kps.get_prompts(db_session, scope)
    assert {p["question_type"] for p in base} >= set(kps.ALL_TYPES)
    assert scope not in await kps.list_scopes(db_session)

    # 2) 存该 scope 定制(把单选正文改掉)
    await kps.save_prompts(db_session, updated_by=admin, scope=scope, prompts=[{
        "name": "本学期单选", "text": "本学期专用提示词", "question_type": "单选",
        "is_default": True, "focus_node_ids": [], "min_kp": 1, "max_kp": 1, "focus_ranges": {},
    }])
    await db_session.flush()

    # 3) get(scope) 拿到定制;get(None) 全局不受影响
    scoped = await kps.get_prompts(db_session, scope)
    assert any(p["question_type"] == "单选" and p["text"] == "本学期专用提示词" for p in scoped)
    glob = await kps.get_prompts(db_session, None)
    assert not any(p.get("text") == "本学期专用提示词" for p in glob)
    assert scope in await kps.list_scopes(db_session)

    # 4) 删除定制 → 回退继承全局;list 不再含
    assert await kps.delete_scope(db_session, scope) is True
    await db_session.flush()
    assert scope not in await kps.list_scopes(db_session)
    after = await kps.get_prompts(db_session, scope)
    assert not any(p.get("text") == "本学期专用提示词" for p in after)


@pytest.mark.asyncio
async def test_passage_include_skill_flag(db_session):
    admin = await _a_user(db_session)
    scope = f"译林版|七年级|测{uuid.uuid4().hex[:4]}"

    assert await kps.get_passage_include_skill(db_session, scope) is False   # 默认收紧

    one = [{"name": "x", "text": "t", "question_type": "教材·听力", "is_default": True,
            "focus_node_ids": [], "min_kp": 1, "max_kp": 1, "focus_ranges": {}}]
    # 该学期打开「也挂技能类」
    await kps.save_prompts(db_session, updated_by=admin, scope=scope, prompts=one,
                           passage_include_skill=True)
    await db_session.flush()
    assert await kps.get_passage_include_skill(db_session, scope) is True
    # 全局仍默认 False(未配)
    assert await kps.get_passage_include_skill(db_session, None) is False

    # 再存(不传 flag)应保留原值 True,不被重置
    await kps.save_prompts(db_session, updated_by=admin, scope=scope, prompts=one)
    await db_session.flush()
    assert await kps.get_passage_include_skill(db_session, scope) is True
