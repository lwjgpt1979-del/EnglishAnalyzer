"""3 次真实 DeepSeek 调用探针:打印请求报文(system+user)+ 返回报文(内容+usage 缓存命中)+ 校验。

每次对一个大题做 KP 建议(同一稳定 system 目录前缀);看 prompt_cache_hit_tokens 是否命中。
运行:DATABASE_URL=... python3 scripts/kp_suggest_probe.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.services import kp_suggest_service as kss, kp_prompt_service as kps  # noqa: E402

OUT = Path("/Users/johnlu/.cache/kp_probe.txt")
_orig = kss.chat_completion
_cap: list = []


async def _spy(*, system_prompt, user_prompt, **kw):
    resp = await _orig(system_prompt=system_prompt, user_prompt=user_prompt, **kw)
    _cap.append((system_prompt, user_prompt, resp))
    return resp


async def main():
    kss.chat_completion = _spy
    buf: list[str] = []

    def w(*a):
        buf.append(" ".join(str(x) for x in a))

    async with async_session_factory() as db:
        pid = (await db.execute(text("select id from platform_paper where name like '%苏州%' limit 1"))).scalar()
        code2node, _ = await kss._load_catalog(db)
        tests = ["完形填空", "阅读理解", "听力部分"]   # 同一 system 前缀,看缓存命中
        for n, sec in enumerate(tests, 1):
            _cap.clear()
            sug = await kss.suggest_kps_for_paper(db, pid, sections=[sec])
            if not _cap:
                w(f"\n==== 测试{n} [{sec}] 无 LLM 调用(可能 dev 模式)===="); continue
            system, user, resp = _cap[-1]
            usage = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage)
            content = resp.choices[0].message.content or ""
            sys_lines = system.splitlines()

            w(f"\n{'='*70}\n==== 测试{n}:大题「{sec}」====")
            w("\n--- 请求报文 · system(稳定缓存前缀)---")
            w(f"[system 总长 {len(system)} 字符,共 {len(sys_lines)} 行]")
            w("【开头规则】"); w("\n".join(sys_lines[:4]))
            w("【目录样例(节选3行)】"); w("\n".join(sys_lines[5:8]))
            w("【目录结尾】"); w(sys_lines[-1][:90], "…")
            w("\n--- 请求报文 · user(可变)---")
            w(user[:1400] + ("…(截断)" if len(user) > 1400 else ""))

            w("\n--- 返回报文 · content ---")
            w(content[:900])
            w("\n--- 返回报文 · usage(缓存命中看 cache_hit/miss)---")
            w(json.dumps(usage, ensure_ascii=False))
            hit = usage.get("prompt_cache_hit_tokens")
            miss = usage.get("prompt_cache_miss_tokens")
            w(f">> prompt_tokens={usage.get('prompt_tokens')}  cache_hit={hit}  cache_miss={miss}  "
              f"=> {'命中缓存✓' if (hit or 0) > 0 else '未命中(首次/已过期)'}")

            # 校验:返回的编码是否都在目录内,映射的题是否都属于该大题
            try:
                data = json.loads(content)
                bad = [c for it in data.get("items", []) for c in (it.get("codes") or []) if c not in code2node]
                ne = {k: v for k, v in sug.items() if v}
                w(f"\n--- 正确性 ---")
                w(f"建议题数 {len(ne)}/{len(sug)} | 目录外编码 {len(bad)} 个 {bad[:5]} | "
                  f"样例 {[[x[2] for x in v] for v in list(ne.values())[:3]]}")
            except Exception as e:  # noqa: BLE001
                w("解析校验异常:", str(e)[:60])

    OUT.write_text("\n".join(buf), encoding="utf-8")
    print("WROTE", OUT)


if __name__ == "__main__":
    asyncio.run(main())
