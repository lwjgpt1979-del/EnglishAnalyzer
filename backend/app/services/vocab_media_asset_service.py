"""词条媒体版本(vocab_media_asset)service:记录/列出/选用。

每次生成的图/音/GIF 都入库不覆盖(record_assets),记风格+提示词;后台可人工「选用」某版本
(select_asset)。词条上的 image_urls / word_audio_url / gif_url 始终是「当前选用」的镜像
(_sync_word),故学生端与其余业务读法不变。
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d5_learning import VocabMediaAsset, VocabularyWord

_KINDS = ("image", "audio", "gif")


async def _sync_word(db: AsyncSession, word_id: uuid.UUID) -> None:
    """按各 kind 的「选用」资产,回填词条 image_urls / word_audio_url / gif_url(单一真源镜像)。"""
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if w is None:
        return
    assets = (await db.execute(
        select(VocabMediaAsset).where(VocabMediaAsset.word_id == word_id)
        .order_by(VocabMediaAsset.created_at))).scalars().all()
    by_kind: dict[str, list[VocabMediaAsset]] = {}
    for a in assets:
        by_kind.setdefault(a.kind, []).append(a)
    if "image" in by_kind:
        sel = [a.url for a in by_kind["image"] if a.selected]
        w.image_urls = sel or None
    if "audio" in by_kind:
        sel = [a.url for a in by_kind["audio"] if a.selected]
        w.word_audio_url = sel[0] if sel else None
    if "gif" in by_kind:
        sel = [a.url for a in by_kind["gif"] if a.selected]
        w.gif_url = sel[0] if sel else None
    await db.flush()


async def record_assets(db: AsyncSession, *, word_id: uuid.UUID, kind: str, urls: list[str],
                        style: str | None = None, prompt: str | None = None,
                        select_new: bool = True) -> None:
    """把本次生成的若干 url 作为新版本入库(不覆盖历史)。select_new=True 时:先把该 kind 旧版本
    全部取消选用,再把这批设为选用(=最新生成成为当前)。随后同步词条镜像字段。"""
    urls = [u for u in urls if u]
    if not urls:
        return
    if select_new:
        await db.execute(update(VocabMediaAsset)
                         .where(VocabMediaAsset.word_id == word_id, VocabMediaAsset.kind == kind,
                                VocabMediaAsset.selected.is_(True))
                         .values(selected=False))
    for u in urls:
        db.add(VocabMediaAsset(id=uuid.uuid4(), word_id=word_id, kind=kind, url=u,
                               style=style, prompt=prompt, selected=select_new))
    await db.flush()
    if select_new:
        await _sync_word(db, word_id)


async def list_assets(db: AsyncSession, *, word_id: uuid.UUID) -> dict:
    """按 kind 分组列出该词全部版本(新→旧),每项 {id,url,style,prompt,selected,created_at}。"""
    assets = (await db.execute(
        select(VocabMediaAsset).where(VocabMediaAsset.word_id == word_id)
        .order_by(VocabMediaAsset.created_at.desc()))).scalars().all()
    out: dict[str, list] = {"image": [], "audio": [], "gif": []}
    for a in assets:
        out.setdefault(a.kind, []).append({
            "id": str(a.id), "url": a.url, "style": a.style, "prompt": a.prompt,
            "selected": bool(a.selected),
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return out


async def select_asset(db: AsyncSession, *, asset_id: uuid.UUID) -> dict:
    """人工选用某版本:同 kind 其余取消选用,该版本设为选用,同步词条镜像。返回该词最新版本列表。"""
    a = (await db.execute(
        select(VocabMediaAsset).where(VocabMediaAsset.id == asset_id))).scalar_one_or_none()
    if a is None:
        raise AppError(code=404, message="版本不存在")
    await db.execute(update(VocabMediaAsset)
                     .where(VocabMediaAsset.word_id == a.word_id, VocabMediaAsset.kind == a.kind)
                     .values(selected=False))
    a.selected = True
    await db.flush()
    await _sync_word(db, a.word_id)
    return await list_assets(db, word_id=a.word_id)


async def delete_asset(db: AsyncSession, *, asset_id: uuid.UUID) -> dict:
    """删除某版本(不允许删掉最后一个选用版本导致镜像空)。返回该词最新版本列表。"""
    a = (await db.execute(
        select(VocabMediaAsset).where(VocabMediaAsset.id == asset_id))).scalar_one_or_none()
    if a is None:
        raise AppError(code=404, message="版本不存在")
    word_id, was_selected, kind = a.word_id, a.selected, a.kind
    await db.delete(a)
    await db.flush()
    if was_selected:   # 删的是选用版 → 自动改选该 kind 最新的一版(若还有)
        latest = (await db.execute(
            select(VocabMediaAsset).where(VocabMediaAsset.word_id == word_id, VocabMediaAsset.kind == kind)
            .order_by(VocabMediaAsset.created_at.desc()).limit(1))).scalar_one_or_none()
        if latest is not None:
            latest.selected = True
            await db.flush()
        await _sync_word(db, word_id)
    return await list_assets(db, word_id=word_id)
