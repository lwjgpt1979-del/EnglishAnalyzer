"""年级归一:旧格式(七/八/九年级、无前缀)→ 规范(初中N年级),幂等,识别不了原样。"""
from app.services.curriculum_service import normalize_grade, CANONICAL_GRADES


def test_normalize_grade():
    # 旧初中格式(无前缀·中文数字)→ 规范
    assert normalize_grade("七年级") == "初中7年级"
    assert normalize_grade("八年级") == "初中8年级"
    assert normalize_grade("九年级") == "初中9年级"
    # 已规范 → 幂等
    assert normalize_grade("初中7年级") == "初中7年级"
    assert normalize_grade("小学5年级") == "小学5年级"
    assert normalize_grade("高中2年级") == "高中2年级"
    # 阿拉伯裸年级 → 按数字归学段
    assert normalize_grade("7年级") == "初中7年级"
    assert normalize_grade("5年级") == "小学5年级"
    # 识别不了/空 → 原样
    assert normalize_grade("测试年级") == "测试年级"
    assert normalize_grade("") == ""
    assert normalize_grade(None) is None


def test_canonical_grades_cover_junior():
    assert "初中7年级" in CANONICAL_GRADES and "小学5年级" in CANONICAL_GRADES
    assert "七年级" not in CANONICAL_GRADES     # 规范里不含旧格式
