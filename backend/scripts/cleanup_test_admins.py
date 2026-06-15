"""清理自动化测试残留的 platform_admin 账号。

只删用户名匹配测试前缀（ops_/pa_/padmin_ + 6位十六进制）的管理员，
**保留** admin / demoadmin 及任何其他真实账号。

安全：
  - 默认 dry-run，仅统计、列样本，不删除。
  - 加 --apply 才真正删除；逐个独立事务，遇外键引用则跳过并记录（不破坏数据）。

用法：
  cd backend && set -a && . ./.env && set +a
  python -m scripts.cleanup_test_admins            # 预览
  python -m scripts.cleanup_test_admins --apply    # 执行删除
"""
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import _async_session_factory

# ops_xxxxxx / pa_xxxxxx / padmin_xxxxxx（6 位十六进制）
PATTERN = r"^(ops|pa|padmin)_[0-9a-f]{6}$"
KEEP = ("admin", "demoadmin")


async def main() -> None:
    apply = "--apply" in sys.argv
    async with _async_session_factory() as s:
        # 正则已排除 admin/demoadmin（它们不匹配测试前缀），KEEP 再兜底过滤
        rows = (await s.execute(text(
            "SELECT id, username FROM users "
            "WHERE role='platform_admin' AND username ~ :pat ORDER BY created_at"
        ).bindparams(pat=PATTERN))).fetchall()
        rows = [r for r in rows if r[1] not in KEEP]

        print(f"匹配测试管理员：{len(rows)} 个（保留 {', '.join(KEEP)} 及其他真实账号）")
        for r in rows[:10]:
            print("  样本:", r[1])
        if len(rows) > 10:
            print(f"  ... 其余 {len(rows) - 10} 个")

        if not apply:
            print("\n[dry-run] 未删除。确认无误后加 --apply 执行。")
            return

        deleted, skipped = 0, 0
        for r in rows:
            try:
                async with s.begin_nested():
                    await s.execute(text("DELETE FROM users WHERE id=:i"), {"i": r[0]})
                deleted += 1
            except IntegrityError:
                skipped += 1  # 被外键引用（如有真实操作记录），跳过保平安
        await s.commit()
        print(f"\n✓ 已删除 {deleted} 个；因外键引用跳过 {skipped} 个。")


if __name__ == "__main__":
    asyncio.run(main())
