"""R0.2 KP 归一化工具单测(纯函数,无 DB)。"""
from __future__ import annotations

import pytest

from app.services.kp_normalize import normalize_kp_name


@pytest.mark.parametrize("raw,expected", [
    ("定语从句", "定语从句"),
    ("定语从句。", "定语从句"),                 # 去尾部标点
    ("过去  完成时", "过去完成时"),             # 去内部空白
    (" 现在完成时 ", "现在完成时"),             # 去首尾空白
    ("现在完成时（Present）", "现在完成时present"),  # 全角括号 + ASCII 小写
    ("Present Perfect", "presentperfect"),       # 英文大小写折叠 + 去空格
    ("ＣＥＴ４", "cet4"),                       # 全角字母数字 → 半角小写
    ("过去完成时!!!", "过去完成时"),            # 去多重标点
    ("", ""),
])
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_kp_name(raw) == expected


def test_variants_collapse_for_dedup() -> None:
    """同义不折叠(交审核),但确定性差异要折叠成同键。"""
    # 标点/空白差异 → 同键(可去重)
    assert normalize_kp_name("过去完成时") == normalize_kp_name("过去 完成时。")
    # 真正不同的写法 → 不同键(留给受控匹配/人工 merge,不在此处合并)
    assert normalize_kp_name("过去完成时") != normalize_kp_name("过去完成式")
