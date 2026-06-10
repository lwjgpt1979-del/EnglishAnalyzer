"""小程序主题预设（M11 换肤系统）。

单一来源：平台后台读此列表做画廊与选择，小程序启动读 active 主题的 tokens 应用。
token 键对应 App.vue 中的 CSS 变量名（去掉 -- 前缀、连字符转下划线）。
"""
from __future__ import annotations

# 每套主题 = 一组 CSS 变量值。前端按 key→--c-xxx 映射注入。
THEMES: list[dict] = [
    {
        "key": "cyan",
        "name": "清新青蓝",
        "desc": "青蓝 + 暖琥珀，活力护眼，默认推荐",
        "tokens": {
            "c_primary": "#2ec4d6", "c_primary_deep": "#16a8c4",
            "c_primary_soft": "#d4f3f7", "c_primary_faint": "#eefbfc",
            "c_gold": "#ffb020", "c_accent": "#ff7a59", "c_olive": "#5ec9b8",
            "c_bg_page": "#f1f6f9", "c_bg_soft": "#edf3f6", "c_border": "#e4ecf0",
            "g_primary": "linear-gradient(135deg,#3ad0df 0%,#1ba6cc 100%)",
            "g_hero": "linear-gradient(135deg,#4ed6e4 0%,#2c9fdf 100%)",
            "shadow_primary": "0 10rpx 28rpx rgba(27,166,204,0.30)",
        },
    },
    {
        "key": "mint",
        "name": "薄荷森林",
        "desc": "青绿 + 暖黄，清新自然，平和专注",
        "tokens": {
            "c_primary": "#22c08a", "c_primary_deep": "#12a374",
            "c_primary_soft": "#d2f4e7", "c_primary_faint": "#eefbf6",
            "c_gold": "#ffc24b", "c_accent": "#ff8a5b", "c_olive": "#7fd1c4",
            "c_bg_page": "#eef8f3", "c_bg_soft": "#e7f3ee", "c_border": "#e0efe8",
            "g_primary": "linear-gradient(135deg,#3ad99e 0%,#13a577 100%)",
            "g_hero": "linear-gradient(135deg,#46e0a6 0%,#10a572 100%)",
            "shadow_primary": "0 10rpx 28rpx rgba(18,163,116,0.30)",
        },
    },
    {
        "key": "sky",
        "name": "天空蓝",
        "desc": "明亮天蓝 + 珊瑚，经典信赖，阳光",
        "tokens": {
            "c_primary": "#3d8bf5", "c_primary_deep": "#2b6fd6",
            "c_primary_soft": "#dbe9ff", "c_primary_faint": "#eef5ff",
            "c_gold": "#ffb020", "c_accent": "#ff7a59", "c_olive": "#6ec0ff",
            "c_bg_page": "#f1f5fc", "c_bg_soft": "#eaf1fb", "c_border": "#e2eaf5",
            "g_primary": "linear-gradient(135deg,#5aa0ff 0%,#3570e0 100%)",
            "g_hero": "linear-gradient(135deg,#62a8ff 0%,#2f6fe0 100%)",
            "shadow_primary": "0 10rpx 28rpx rgba(43,111,214,0.30)",
        },
    },
    {
        "key": "coral",
        "name": "活力珊瑚",
        "desc": "珊瑚橙 + 青点缀，温暖俏皮，最童趣",
        "tokens": {
            "c_primary": "#ff7a59", "c_primary_deep": "#f0563a",
            "c_primary_soft": "#ffe0d6", "c_primary_faint": "#fff3ef",
            "c_gold": "#ffc24b", "c_accent": "#2ec4d6", "c_olive": "#ffb59e",
            "c_bg_page": "#fff5f2", "c_bg_soft": "#fcebe5", "c_border": "#f6e2da",
            "g_primary": "linear-gradient(135deg,#ff9a6b 0%,#f5603f 100%)",
            "g_hero": "linear-gradient(135deg,#ffa074 0%,#ff6a4d 100%)",
            "shadow_primary": "0 10rpx 28rpx rgba(240,86,58,0.28)",
        },
    },
    {
        "key": "violet",
        "name": "优雅紫",
        "desc": "柔和紫 + 暖琥珀，高级创意，沉静",
        "tokens": {
            "c_primary": "#7c6cf0", "c_primary_deep": "#5d4ad6",
            "c_primary_soft": "#e4e0fc", "c_primary_faint": "#f3f1fe",
            "c_gold": "#ffb020", "c_accent": "#ff7a9c", "c_olive": "#a99cf5",
            "c_bg_page": "#f4f3fb", "c_bg_soft": "#edeafa", "c_border": "#e6e2f4",
            "g_primary": "linear-gradient(135deg,#9b8bff 0%,#6a55e6 100%)",
            "g_hero": "linear-gradient(135deg,#a08fff 0%,#6750e6 100%)",
            "shadow_primary": "0 10rpx 28rpx rgba(93,74,214,0.28)",
        },
    },
]

_BY_KEY = {t["key"]: t for t in THEMES}
DEFAULT_THEME_KEY = "cyan"


def get_theme(key: str) -> dict:
    return _BY_KEY.get(key) or _BY_KEY[DEFAULT_THEME_KEY]
