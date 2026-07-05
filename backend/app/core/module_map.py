"""admin 后台「路径 → 功能模块」映射(单一数据源)。

两处共用,保证口径一致:
- 操作审计(audit_middleware):写操作按模块归类,便于筛查;
- 模块权限(RBAC):子管理员 users.admin_modules 只放行所辖模块。

模块键与 admin 前端菜单分组一一对应;新增菜单组时此处同步加规则。
"""
from __future__ import annotations

# (路径子串前缀元组, 模块键) —— 从上到下第一条命中
_MODULE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("/sales/",), "sales"),
    (("/pricing", "/entitlement", "/finance", "/refund", "/invoice",
      "/payment-account", "/branch-compan", "/institution-code-pricing", "/order"), "finance"),
    (("/users", "/coupon", "/campaign", "/announcement", "/notification", "/ban"), "ops"),
    (("/institution", "/teacher"), "teacher_inst"),
    (("/llm-config", "/system", "/sensitive-words", "/region", "/textbook-map",
      "/audit-logs", "/admins"), "system"),
    (("/support", "/faq", "/feedback"), "support"),
    (("/vocab", "/word"), "vocab"),
    (("/tts", "/speaking", "/theme"), "speak"),
]

# 全部模块键(admin_modules 白名单;与 admin 前端菜单分组对应)
MODULES = ("content", "vocab", "speak", "teacher_inst", "ops",
           "sales", "finance", "support", "system")

# 任何管理员都放行的公共路径(个人信息/首页大盘)
_COMMON = ("/me", "/dashboard")


def module_of(path: str) -> str:
    """按路径归类模块。未命中规则的大头是内容生产(真题/知识点/课程…)→ content。"""
    p = path.split("/api/v1/admin", 1)[-1]
    for prefixes, mod in _MODULE_RULES:
        if any(x in p for x in prefixes):
            return mod
    return "content"


def is_common_path(path: str) -> bool:
    p = path.split("/api/v1/admin", 1)[-1]
    return any(p == c or p.startswith(c + "/") or p.startswith(c + "?") for c in _COMMON)
