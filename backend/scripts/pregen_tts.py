"""批量预生成 TTS 音频到 COS —— 仅做部分测试用（小批量）。

把"听力素材整段 + 少量词库单词/英文描述"提前用火山 TTS 合成并上传 COS，
让这些内容首次播放即从 COS 秒开。幂等：已存在的对象直接复用、不重复合成。

用法（需 .env 配好 TTS_PROVIDER=volcano + COS）：
    cd backend && PYTHONPATH=. python scripts/pregen_tts.py            # 默认词库取 10 个
    PYTHONPATH=. python scripts/pregen_tts.py --vocab-limit 30         # 取 30 个
    PYTHONPATH=. python scripts/pregen_tts.py --no-listening           # 只跑词库
"""
from __future__ import annotations

import argparse
import asyncio
import logging

logging.disable(logging.CRITICAL)

from sqlalchemy import select  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d5_learning import VocabularyWord  # noqa: E402
from app.services import listening_service, tts_service  # noqa: E402


async def _gen_one(label: str, text: str) -> bool:
    try:
        url = await tts_service.get_or_create_audio_url(text)
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {label[:36]:<36} ERROR {e}")
        return False
    if url:
        print(f"  ✓ {label[:36]:<36} -> {url.rsplit('/', 1)[-1]}")
        return True
    print(f"  ✗ {label[:36]:<36} (COS 未配置 / 合成失败)")
    return False


async def main(vocab_limit: int, include_listening: bool) -> None:
    texts: list[tuple[str, str]] = []

    if include_listening:
        for ex in listening_service._EXERCISES:  # noqa: SLF001
            texts.append((f"[听力] {ex['title']}", ex["transcript"]))

    async with _async_session_factory() as db:
        words = (await db.execute(
            select(VocabularyWord).order_by(VocabularyWord.difficulty).limit(vocab_limit)
        )).scalars().all()
        for w in words:
            texts.append((f"[单词] {w.word}", w.word))
            if w.en_description:
                texts.append((f"[描述] {w.word}", w.en_description))

    print(f"待预生成 {len(texts)} 条音频（小批量测试）...\n")
    ok = sum([await _gen_one(label, text) for label, text in texts])
    print(f"\n完成：成功 {ok} / 共 {len(texts)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab-limit", type=int, default=10, help="词库取词数（默认 10，测试用）")
    ap.add_argument("--no-listening", action="store_true", help="跳过听力素材，只跑词库")
    args = ap.parse_args()
    asyncio.run(main(args.vocab_limit, not args.no_listening))
