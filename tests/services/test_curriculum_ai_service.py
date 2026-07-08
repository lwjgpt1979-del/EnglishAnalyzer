"""curriculum_ai_service dev mock 测试。

dev mock（DEEPSEEK_API_KEY 以 sk-placeholder 开头）下返回固定结构，
让 persist + 前端开发不需要真实 API key。
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.curriculum_ai_service import generate_unit


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock 路径；防止环境里有真 DEEPSEEK_API_KEY 时测试打到真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


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

    # 讲解已迁到 kp_lecture(按考点类型的教学环节),不再随 AI 单元生成;此处只校验骨架。
    for kp in unit.knowledge_points:
        # code 必须包含 unit 标识方便幂等 upsert
        assert "u1" in kp.code or str(unit.unit_no) in kp.code


@pytest.mark.asyncio
async def test_dev_mock_different_units_have_different_titles():
    """不同 unit_no 的 mock 结果应该可区分（避免幂等 upsert 把所有单元合并）。"""
    u1 = await generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1)
    u2 = await generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=2)
    assert u1.unit_title != u2.unit_title
    assert u1.knowledge_points[0].code != u2.knowledge_points[0].code
