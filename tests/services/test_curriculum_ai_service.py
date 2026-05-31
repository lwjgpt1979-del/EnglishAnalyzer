"""curriculum_ai_service dev mock 测试。

dev mock（DEEPSEEK_API_KEY 以 sk-placeholder 开头）下返回固定结构，
让 persist + 前端开发不需要真实 API key。
"""
from __future__ import annotations

import pytest

from app.services.curriculum_ai_service import generate_unit


@pytest.mark.asyncio
async def test_dev_mock_returns_valid_structure():
    """dev mock 必须返回符合 AIGeneratedUnit 的完整结构。"""
    unit = await generate_unit(
        textbook_version="译林版",
        grade="小学5年级",
        semester="上",
        unit_no=1,
    )

    assert unit.textbook_version == "译林版"
    assert unit.grade == "小学5年级"
    assert unit.semester == "上"
    assert unit.unit_no == 1
    assert unit.unit_title  # 非空
    assert len(unit.knowledge_points) >= 3
    assert len(unit.words) >= 5

    # 知识点 4 维度都得有
    for kp in unit.knowledge_points:
        assert set(kp.contents.keys()) == {"listening", "dictation", "grammar", "writing"}
        assert all(v.strip() for v in kp.contents.values())
        # code 必须包含 unit 标识方便幂等 upsert
        assert "u1" in kp.code or str(unit.unit_no) in kp.code


@pytest.mark.asyncio
async def test_dev_mock_different_units_have_different_titles():
    """不同 unit_no 的 mock 结果应该可区分（避免幂等 upsert 把所有单元合并）。"""
    u1 = await generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1)
    u2 = await generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=2)
    assert u1.unit_title != u2.unit_title
    assert u1.knowledge_points[0].code != u2.knowledge_points[0].code
