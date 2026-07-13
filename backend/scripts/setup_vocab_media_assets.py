"""建 vocab_media_asset(词条媒体版本)表 + 播种存量媒体为「选用」版本。幂等,可重复跑。

背景:词条媒体改为「每次生成入库不覆盖 + 可人工选用某版本」。本脚本:
  1) 幂等建表 vocab_media_asset(+ (word_id,kind) 索引);
  2) 对已有 image_urls / word_audio_url / gif_url 且该 kind 尚无版本记录的词条,
     补一条 selected=True 的版本(把现状纳入版本历史)。

跑法(在 backend/ 下): python scripts/setup_vocab_media_assets.py
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select, text

from app.core.database import _async_engine, async_session_factory
from app.models.d5_learning import VocabMediaAsset, VocabularyWord


async def main() -> None:
    async with _async_engine.begin() as conn:
        await conn.run_sync(VocabMediaAsset.__table__.create, checkfirst=True)
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vocab_media_asset_word_kind "
            "ON vocab_media_asset(word_id, kind)"))
    print("表 vocab_media_asset 已建/存在")

    async with async_session_factory() as db:
        words = (await db.execute(select(VocabularyWord).where(
            (VocabularyWord.image_urls.isnot(None))
            | (VocabularyWord.word_audio_url.isnot(None))
            | (VocabularyWord.gif_url.isnot(None))))).scalars().all()
        existing: dict = {}
        for wid, k in (await db.execute(
                select(VocabMediaAsset.word_id, VocabMediaAsset.kind))).all():
            existing.setdefault(wid, set()).add(k)
        n = 0
        for w in words:
            have = existing.get(w.id, set())
            if "image" not in have:
                for u in (w.image_urls or []):
                    if u:
                        db.add(VocabMediaAsset(id=uuid.uuid4(), word_id=w.id, kind="image",
                                               url=u, selected=True)); n += 1
            if "audio" not in have and w.word_audio_url:
                db.add(VocabMediaAsset(id=uuid.uuid4(), word_id=w.id, kind="audio",
                                       url=w.word_audio_url, selected=True)); n += 1
            if "gif" not in have and w.gif_url:
                db.add(VocabMediaAsset(id=uuid.uuid4(), word_id=w.id, kind="gif",
                                       url=w.gif_url, selected=True)); n += 1
        await db.commit()
        print(f"播种版本行数: {n}")


if __name__ == "__main__":
    asyncio.run(main())
