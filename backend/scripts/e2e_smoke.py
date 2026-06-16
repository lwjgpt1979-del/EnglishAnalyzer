"""上线冒烟：对一个运行中的后端做 API 级 E2E 检查（上线硬化）。

用法：
  BASE_URL=https://api.goodgrammar.top \
  ADMIN_USER=xxx ADMIN_PASS=yyy \
  python -m scripts.e2e_smoke

不传 ADMIN_USER/PASS 时只跑无需鉴权的检查（/health）。
真机小程序链路（拍照上传→OCR→诊断、支付等）需在微信开发者工具按
docs/上线前清单.md §E 人工走查，本脚本不覆盖端上交互。
"""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER")
ADMIN_PASS = os.environ.get("ADMIN_PASS")

_passed, _failed = 0, 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    mark = "✅" if ok else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
    if ok:
        _passed += 1
    else:
        _failed += 1


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15.0) as c:
        # 1) 健康检查
        try:
            r = c.get("/health")
            check("GET /health", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as e:
            check("GET /health", False, str(e))
            print("\n后端不可达，终止。"); return 1

        # 2) 管理后台登录 + 大盘（提供凭证才跑）
        if ADMIN_USER and ADMIN_PASS:
            token = None
            try:
                r = c.post("/api/v1/admin/auth/login",
                           json={"username": ADMIN_USER, "password": ADMIN_PASS})
                ok = r.status_code == 200 and r.json().get("data", {}).get("access_token")
                token = r.json().get("data", {}).get("access_token") if ok else None
                check("POST /admin/auth/login", bool(ok), f"HTTP {r.status_code}")
            except Exception as e:
                check("POST /admin/auth/login", False, str(e))
            if token:
                h = {"Authorization": f"Bearer {token}"}
                try:
                    r = c.get("/api/v1/admin/dashboard", headers=h)
                    check("GET /admin/dashboard", r.status_code == 200, f"HTTP {r.status_code}")
                except Exception as e:
                    check("GET /admin/dashboard", False, str(e))
                # 限流冒烟：错误密码连打应触发 429（验证防爆破生效）
                try:
                    codes = [c.post("/api/v1/admin/auth/login",
                                    json={"username": ADMIN_USER, "password": "wrong"}).status_code
                             for _ in range(12)]
                    check("登录限流(防爆破)生效", 429 in codes, f"状态码序列尾部={codes[-3:]}")
                except Exception as e:
                    check("登录限流(防爆破)生效", False, str(e))
        else:
            print("ℹ️ 未提供 ADMIN_USER/ADMIN_PASS，跳过鉴权链路检查")

    print(f"\n结果：{_passed} 通过 / {_failed} 失败")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
