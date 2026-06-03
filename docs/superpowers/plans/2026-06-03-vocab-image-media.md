# 词力通图背单词（配图 + 英文描述 + 双音频）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 词力通词卡增加「多张配图 + 英文可理解性描述 + 单词发音音频 + 英文描述朗读音频」，运营后台生成/审核，学生端展示；全程 dev-mock 占位不花钱，真·文生图/真 TTS 留可插拔 config 接缝。

**Architecture:** 复用 `vocabulary_words`（迁移 0016 加 5 个 nullable 字段）。新增 `vocab_media_provider`（图/音频 provider 抽象，dev-mock 出占位 URL，类比 `llm_provider`）+ `vocab_media_service`（生成/审核/编辑）。运营 admin 4 端点（复用 `require_role`）。学生端 `WordCardOut` 带媒体（仅 `media_status='published'`）。沿用 D-095/096 审核闸门：生成默认 `draft`，运营审核→`published`，学生端只见 published。

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic；uni-app Vue3 小程序。

参考 spec：`docs/superpowers/specs/2026-06-03-vocab-image-media-design.md`。

---

### Task 1: DB 字段 + 迁移 0016 + config 接缝

**Files:**
- Modify: `backend/app/models/d5_learning.py`（VocabularyWord 加 5 字段）
- Create: `backend/alembic/versions/0016_vocab_media_fields.py`
- Modify: `backend/app/core/config.py`（image_*/tts_* 占位配置）
- Test: `tests/models/test_model_structure.py`

- [ ] **Step 1: 写失败测试**（`tests/models/test_model_structure.py` 末尾）

```python
def test_vocabulary_words_has_media_fields():
    from app.models.d5_learning import VocabularyWord
    cols = set(VocabularyWord.__table__.columns.keys())
    for c in ["image_urls", "en_description", "word_audio_url", "en_desc_audio_url", "media_status"]:
        assert c in cols, f"VocabularyWord 缺字段 {c}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/models/test_model_structure.py -k vocabulary_words_has_media -v`
Expected: FAIL（字段不存在）。

- [ ] **Step 3: 加模型字段**（`d5_learning.py` 的 `VocabularyWord` 类内，`difficulty` 字段后）

```python
    # —— 图背单词媒体（P1 词力通深化 / D-101；dev-mock 占位，真生成留 config 接缝）——
    image_urls = mapped_column(JSONB, nullable=True)
    en_description = mapped_column(sa.Text, nullable=True)
    word_audio_url = mapped_column(sa.String, nullable=True)
    en_desc_audio_url = mapped_column(sa.String, nullable=True)
    media_status = mapped_column(sa.String, nullable=False, server_default=sa.text("'draft'"))
```

> 确认 `d5_learning.py` 顶部已 import `JSONB`（`from sqlalchemy.dialects.postgresql import JSONB`）；若无则补。`sa` 已导入。

- [ ] **Step 4: 写迁移 0016**（`backend/alembic/versions/0016_vocab_media_fields.py`）

```python
"""vocab media fields: image_urls/en_description/audio/media_status (词力通图背单词)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocabulary_words", sa.Column("image_urls", postgresql.JSONB(), nullable=True))
    op.add_column("vocabulary_words", sa.Column("en_description", sa.Text(), nullable=True))
    op.add_column("vocabulary_words", sa.Column("word_audio_url", sa.String(), nullable=True))
    op.add_column("vocabulary_words", sa.Column("en_desc_audio_url", sa.String(), nullable=True))
    op.add_column("vocabulary_words", sa.Column(
        "media_status", sa.String(), nullable=False, server_default=sa.text("'draft'")
    ))


def downgrade() -> None:
    op.drop_column("vocabulary_words", "media_status")
    op.drop_column("vocabulary_words", "en_desc_audio_url")
    op.drop_column("vocabulary_words", "word_audio_url")
    op.drop_column("vocabulary_words", "en_description")
    op.drop_column("vocabulary_words", "image_urls")
```

- [ ] **Step 5: 加 config 接缝**（`backend/app/core/config.py` 的 Settings 内，cos_* 附近）

```python
    # ── 文生图 provider（dev 以 placeholder 触发 mock，真生成留接缝）──
    image_provider: str = "mock"
    image_api_key: str = "img-placeholder-for-dev"
    image_count_per_word: int = 3
    # ── TTS provider（dev mock）──
    tts_provider: str = "mock"
    tts_api_key: str = "tts-placeholder-for-dev"
```

- [ ] **Step 6: 跑迁移 + 测试**

Run: `cd backend && set -a && . ./.env && set +a && /opt/anaconda3/bin/python -m alembic upgrade head`
Run: `/opt/anaconda3/bin/python -m pytest ../tests/models/test_model_structure.py -k vocabulary_words_has_media -v`
Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/d5_learning.py backend/alembic/versions/0016_vocab_media_fields.py backend/app/core/config.py tests/models/test_model_structure.py
git commit -m "feat(backend): vocabulary_words 加图背单词媒体字段 + 迁移 0016 + config 接缝"
```

### Task 2: vocab_media_provider（图/音频 dev-mock provider）

**Files:**
- Create: `backend/app/services/vocab_media_provider.py`
- Test: `tests/services/test_vocab_media_provider.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from app.services import vocab_media_provider as p

def test_image_dev_mode_default():
    assert p.is_image_dev_mode() is True   # 默认 placeholder

def test_tts_dev_mode_default():
    assert p.is_tts_dev_mode() is True

def test_generate_images_devmock_count_and_determinism():
    urls = p.generate_images("confident", n=3)
    assert len(urls) == 3
    assert all(isinstance(u, str) and u.startswith("http") for u in urls)
    assert urls == p.generate_images("confident", n=3)  # 确定性

def test_generate_tts_devmock():
    u = p.generate_tts("hello world")
    assert isinstance(u, str) and u.startswith("http")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_vocab_media_provider.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现**

```python
"""词力通图/音频 provider 抽象（P1 / D-101）。

dev-mock：图与音频返回确定性占位 URL，一分钱不花、可测。
真·文生图 / 真 TTS 留 config 接缝（image_provider/tts_provider != "mock"），
等确认预算 + 安全渠道给 key 后实现 _real_* 分支。
"""
from __future__ import annotations

import hashlib
import urllib.parse

from app.core.config import settings


def is_image_dev_mode() -> bool:
    return settings.image_provider == "mock" or settings.image_api_key.startswith("img-placeholder")


def is_tts_dev_mode() -> bool:
    return settings.tts_provider == "mock" or settings.tts_api_key.startswith("tts-placeholder")


def generate_images(prompt: str, n: int = 3) -> list[str]:
    """返回 n 张图 URL。dev-mock 用 placehold.co 占位（按 prompt+序号确定性）。"""
    if is_image_dev_mode():
        safe = urllib.parse.quote((prompt or "word")[:20])
        return [f"https://placehold.co/600x400?text={safe}-{i + 1}" for i in range(n)]
    raise NotImplementedError("真·文生图 provider 未接入（需预算 + key）")


def generate_tts(text: str) -> str:
    """返回音频 URL。dev-mock 用确定性占位 URL（按文本 hash）。"""
    if is_tts_dev_mode():
        h = hashlib.md5((text or "").encode("utf-8")).hexdigest()[:12]
        return f"https://mock-tts.local/audio/{h}.mp3"
    raise NotImplementedError("真 TTS provider 未接入（需预算 + key）")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/opt/anaconda3/bin/python -m pytest ../tests/services/test_vocab_media_provider.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/vocab_media_provider.py tests/services/test_vocab_media_provider.py
git commit -m "feat(backend): 词力通图/音频 provider（dev-mock 占位 + 真生成接缝）"
```

### Task 3: vocab_media_service（生成 / 审核 / 编辑 / 列表）

**Files:**
- Create: `backend/app/services/vocab_media_service.py`
- Test: `tests/services/test_vocab_media_service.py`

- [ ] **Step 1: 写失败测试**

```python
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from app.core.database import _async_session_factory
from app.models.d5_learning import VocabularyWord
from app.services import vocab_media_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _seed_word(s) -> uuid.UUID:
    w = VocabularyWord(
        id=uuid.uuid4(), word=f"media_{uuid.uuid4().hex[:6]}", phonetic="t",
        definitions=[{"pos": "n.", "meaning": "测试"}], examples=None, difficulty=1,
    )
    s.add(w); await s.flush(); return w.id


@pytest.mark.asyncio
async def test_generate_writes_all_media_draft(db_session):
    wid = await _seed_word(db_session)
    w = await vocab_media_service.generate_for_word(db_session, word_id=wid)
    assert w.image_urls and len(w.image_urls) >= 1
    assert w.en_description
    assert w.word_audio_url and w.en_desc_audio_url
    assert w.media_status == "draft"

@pytest.mark.asyncio
async def test_review_approve_publishes(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    w = await vocab_media_service.review_word_media(db_session, word_id=wid, approve=True)
    assert w.media_status == "published"

@pytest.mark.asyncio
async def test_review_reject_retires(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    w = await vocab_media_service.review_word_media(db_session, word_id=wid, approve=False)
    assert w.media_status == "retired"

@pytest.mark.asyncio
async def test_update_media_edits_fields(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    w = await vocab_media_service.update_word_media(
        db_session, word_id=wid, en_description="edited desc", image_urls=["https://x/y.png"],
    )
    assert w.en_description == "edited desc"
    assert w.image_urls == ["https://x/y.png"]

@pytest.mark.asyncio
async def test_list_for_review_filters_status(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    await db_session.flush()
    rows, total = await vocab_media_service.list_words_for_media_review(db_session, media_status="draft")
    assert total >= 1 and any(r.id == wid for r in rows)

@pytest.mark.asyncio
async def test_generate_missing_word_raises(db_session):
    from app.core.exceptions import AppError
    with pytest.raises(AppError):
        await vocab_media_service.generate_for_word(db_session, word_id=uuid.uuid4())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_vocab_media_service.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现**

```python
"""词力通图背单词媒体业务（P1 / D-101）。

generate_for_word：英文描述（LLM，dev-mock 出固定文本）+ 多图 + 双音频（provider dev-mock），
写库默认 media_status='draft'，运营审核后 published。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.config import settings
from app.models.d5_learning import VocabularyWord
from app.services import llm_provider, vocab_media_provider


def _primary_meaning(w: VocabularyWord) -> str:
    d = w.definitions
    if isinstance(d, list) and d:
        return str(d[0].get("meaning", ""))
    return ""


async def _gen_en_description(word: str, meaning: str) -> str:
    """英文可理解性描述：dev-mock 出固定模板；真 LLM 走 chat_completion。"""
    if llm_provider.is_llm_dev_mode():
        return (f"'{word}' means {meaning}. Use it in simple English: "
                f"This is a clear, learner-friendly explanation of the word '{word}'.")
    resp = await llm_provider.chat_completion(
        system_prompt="You are an English teacher. Explain the word for a young learner "
                      "using simple English (CEFR A2). 2-3 short sentences, no Chinese.",
        user_prompt=f"Word: {word}\nChinese meaning: {meaning}",
        max_tokens=200,
    )
    return (resp.choices[0].message.content or "").strip()


async def generate_for_word(db: AsyncSession, *, word_id: uuid.UUID) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    meaning = _primary_meaning(w)
    en = await _gen_en_description(w.word, meaning)
    images = vocab_media_provider.generate_images(w.word, n=settings.image_count_per_word)
    w.en_description = en
    w.image_urls = images
    w.word_audio_url = vocab_media_provider.generate_tts(w.word)
    w.en_desc_audio_url = vocab_media_provider.generate_tts(en)
    w.media_status = "draft"
    await db.flush()
    return w


async def review_word_media(db: AsyncSession, *, word_id: uuid.UUID, approve: bool) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    w.media_status = "published" if approve else "retired"
    await db.flush()
    return w


async def update_word_media(
    db: AsyncSession, *, word_id: uuid.UUID,
    image_urls: list[str] | None = None, en_description: str | None = None,
    word_audio_url: str | None = None, en_desc_audio_url: str | None = None,
) -> VocabularyWord:
    w = (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()
    if w is None:
        raise AppError(code=404, message="单词不存在")
    if image_urls is not None:
        w.image_urls = image_urls
    if en_description is not None:
        w.en_description = en_description
    if word_audio_url is not None:
        w.word_audio_url = word_audio_url
    if en_desc_audio_url is not None:
        w.en_desc_audio_url = en_desc_audio_url
    await db.flush()
    return w


async def list_words_for_media_review(
    db: AsyncSession, *, media_status: str = "draft", skip: int = 0, limit: int = 20,
) -> tuple[list[VocabularyWord], int]:
    base = select(VocabularyWord).where(VocabularyWord.media_status == media_status)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabularyWord.word).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/opt/anaconda3/bin/python -m pytest ../tests/services/test_vocab_media_service.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/vocab_media_service.py tests/services/test_vocab_media_service.py
git commit -m "feat(backend): 词力通媒体 service（生成/审核/编辑/列表，dev-mock）"
```

### Task 4: Schemas + 运营 admin API

**Files:**
- Modify: `backend/app/schemas/vocabulary.py`（加 admin 媒体 DTO）
- Modify: `backend/app/api/v1/admin.py`（4 端点 + helper）
- Test: `tests/api/test_admin_vocab_media.py`

新增 schema（`schemas/vocabulary.py` 末尾）：

```python
class AdminVocabMediaItem(BaseModel):
    word_id: uuid.UUID
    word: str
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None
    media_status: str

class AdminVocabMediaListOut(BaseModel):
    total: int
    items: list[AdminVocabMediaItem]

class VocabMediaReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published，false=驳回→retired")

class VocabMediaUpdateRequest(BaseModel):
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None
```

`admin.py` 加 import + helper + 4 端点：

```python
from app.models.d5_learning import VocabularyWord
from app.schemas.vocabulary import (
    AdminVocabMediaItem, AdminVocabMediaListOut,
    VocabMediaReviewRequest, VocabMediaUpdateRequest,
)
from app.services import vocab_media_service   # 加入现有 services import 组

def _to_vocab_media_item(w: VocabularyWord) -> AdminVocabMediaItem:
    return AdminVocabMediaItem(
        word_id=w.id, word=w.word, image_urls=w.image_urls,
        en_description=w.en_description, word_audio_url=w.word_audio_url,
        en_desc_audio_url=w.en_desc_audio_url, media_status=str(w.media_status),
    )

@router.post("/vocab/{word_id}/generate-media", response_model=BaseResponse[AdminVocabMediaItem])
async def generate_vocab_media(word_id: uuid.UUID, db: DbDep, admin: AdminDep):
    w = await vocab_media_service.generate_for_word(db, word_id=word_id)
    await db.commit()
    return make_ok(_to_vocab_media_item(w))

@router.get("/vocab", response_model=BaseResponse[AdminVocabMediaListOut])
async def list_vocab_media(db: DbDep, admin: AdminDep,
    media_status: str = "draft", skip: int = 0, limit: int = 20):
    rows, total = await vocab_media_service.list_words_for_media_review(
        db, media_status=media_status, skip=skip, limit=limit)
    return make_ok(AdminVocabMediaListOut(total=total, items=[_to_vocab_media_item(w) for w in rows]))

@router.post("/vocab/{word_id}/media/review", response_model=BaseResponse[AdminVocabMediaItem])
async def review_vocab_media(word_id: uuid.UUID, body: VocabMediaReviewRequest, db: DbDep, admin: AdminDep):
    w = await vocab_media_service.review_word_media(db, word_id=word_id, approve=body.approve)
    await db.commit()
    return make_ok(_to_vocab_media_item(w))

@router.put("/vocab/{word_id}/media", response_model=BaseResponse[AdminVocabMediaItem])
async def update_vocab_media(word_id: uuid.UUID, body: VocabMediaUpdateRequest, db: DbDep, admin: AdminDep):
    w = await vocab_media_service.update_word_media(
        db, word_id=word_id, image_urls=body.image_urls, en_description=body.en_description,
        word_audio_url=body.word_audio_url, en_desc_audio_url=body.en_desc_audio_url)
    await db.commit()
    return make_ok(_to_vocab_media_item(w))
```

- [ ] **Step 1: 写失败测试**（`tests/api/test_admin_vocab_media.py`，镜像 `test_admin_contents.py`：建 admin（登录→DB 改 role）+ 1 个词；POST generate-media→200 draft；GET /admin/vocab?media_status=draft 见到；PUT 改 en_description；POST review approve→published；非管理员 GET 403）。helper 照 `test_admin_contents.py` 同款。
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 schema + 端点**
- [ ] **Step 4: 跑测试确认通过** `/opt/anaconda3/bin/python -m pytest ../tests/api/test_admin_vocab_media.py -v`
- [ ] **Step 5: Commit** `feat(backend): 运营 admin 词力通媒体 API（生成/列表/审核/编辑）`

### Task 5: 学生端 WordCardOut 带媒体（仅 published）

**Files:**
- Modify: `backend/app/schemas/vocabulary.py`（WordCardOut 加 4 字段）
- Modify: `backend/app/services/vocabulary_service.py`（`_to_card` 按 media_status 填媒体）
- Test: `tests/services/test_vocabulary_service.py`

WordCardOut 增字段：

```python
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None
```

`_to_card` 改（仅 published 才带媒体；草稿/未生成 → None）：

```python
def _to_card(w: VocabularyWord, *, level: str, is_new: bool) -> WordCardOut:
    pub = str(getattr(w, "media_status", "draft")) == "published"
    return WordCardOut(
        word_id=w.id, word=w.word, phonetic=w.phonetic,
        definitions=w.definitions, examples=w.examples, difficulty=w.difficulty,
        level=level, is_new=is_new,
        image_urls=(w.image_urls if pub else None),
        en_description=(w.en_description if pub else None),
        word_audio_url=(w.word_audio_url if pub else None),
        en_desc_audio_url=(w.en_desc_audio_url if pub else None),
    )
```

- [ ] **Step 1: 写失败测试**（`tests/services/test_vocabulary_service.py` 末尾）

```python
@pytest.mark.asyncio
async def test_daily_task_includes_published_media_only(db_session, seeded_kp):
    import uuid as _uuid
    from app.models.d5_learning import VocabularyWord
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    # 已发布媒体的词
    w_pub = VocabularyWord(id=_uuid.uuid4(), word=f"pub_{_uuid.uuid4().hex[:6]}", phonetic="p",
        definitions=[{"pos":"n.","meaning":"x"}], examples=None, difficulty=0,
        image_urls=["https://i/1.png"], en_description="desc", word_audio_url="https://a/w.mp3",
        en_desc_audio_url="https://a/d.mp3", media_status="published")
    # 草稿媒体的词
    w_draft = VocabularyWord(id=_uuid.uuid4(), word=f"dft_{_uuid.uuid4().hex[:6]}", phonetic="d",
        definitions=[{"pos":"n.","meaning":"y"}], examples=None, difficulty=0,
        image_urls=["https://i/2.png"], en_description="hidden", media_status="draft")
    db_session.add_all([w_pub, w_draft]); await db_session.flush()
    task = await vocabulary_service.get_daily_task(db_session, student_id=sid)
    by_id = {c.word_id: c for c in task.new_words}
    assert by_id[w_pub.id].image_urls == ["https://i/1.png"]
    assert by_id[w_pub.id].en_description == "desc"
    assert by_id[w_draft.id].image_urls is None   # 草稿不下发
    assert by_id[w_draft.id].en_description is None
```

> `_make_student` / `seeded_kp` / `db_session` 已在该测试文件存在（词力通 Task 2 建的）。新词难度 0 确保进 free 档前 5。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_vocabulary_service.py -k published_media_only -v`
Expected: FAIL（WordCardOut 无 image_urls）。

- [ ] **Step 3: 实现**（WordCardOut 加字段 + `_to_card` 改造，见上）
- [ ] **Step 4: 跑测试确认通过 + service 全量**

Run: `/opt/anaconda3/bin/python -m pytest ../tests/services/test_vocabulary_service.py ../tests/api/test_vocabulary.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/vocabulary.py backend/app/services/vocabulary_service.py tests/services/test_vocabulary_service.py
git commit -m "feat(backend): 词力通 daily-task 词卡带 published 媒体（图/英文描述/双音频）"
```

### Task 6: 前端词卡媒体展示

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`（VocabWordCard 加 4 字段）
- Modify: `frontend/miniprogram/src/pages/vocabulary/index.vue`（词卡区展示媒体）

- [ ] **Step 1: 加 TS 字段**（`types/api.ts` 的 `VocabWordCard` 接口）

```typescript
  image_urls?: string[] | null
  en_description?: string | null
  word_audio_url?: string | null
  en_desc_audio_url?: string | null
```

- [ ] **Step 2: 词卡区展示媒体**（`pages/vocabulary/index.vue` 的"学习阶段：词卡"块，例句后、按钮前插入）

```html
      <!-- 图背单词：配图 -->
      <scroll-view v-if="curStudy.image_urls && curStudy.image_urls.length" scroll-x class="img-row">
        <image v-for="(u, i) in curStudy.image_urls" :key="i" :src="u" mode="aspectFill" class="word-img" />
      </scroll-view>
      <!-- 英文可理解性描述 -->
      <view v-if="curStudy.en_description" class="en-desc">
        <text class="en-desc-text">{{ curStudy.en_description }}</text>
      </view>
      <!-- 双音频播放 -->
      <view class="audio-row">
        <text v-if="curStudy.word_audio_url" class="audio-btn" @tap="playAudio(curStudy.word_audio_url)">🔊 单词</text>
        <text v-if="curStudy.en_desc_audio_url" class="audio-btn" @tap="playAudio(curStudy.en_desc_audio_url)">🔊 英文描述</text>
      </view>
```

加播放方法（`<script setup>` 内）：

```typescript
let _audioCtx: UniApp.InnerAudioContext | null = null
function playAudio(src?: string | null) {
  if (!src) return
  if (!_audioCtx) _audioCtx = uni.createInnerAudioContext()
  _audioCtx.src = src
  _audioCtx.play()
}
```

加样式（`<style scoped>` 内）：

```css
.img-row { white-space: nowrap; margin: 20rpx 0; }
.word-img { width: 220rpx; height: 160rpx; border-radius: var(--r-md); margin-right: 16rpx; display: inline-block; background: var(--c-bg-soft); }
.en-desc { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; margin: 16rpx 0; }
.en-desc-text { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
.audio-row { display: flex; gap: 24rpx; margin-bottom: 8rpx; }
.audio-btn { font-size: 28rpx; color: var(--c-gold); font-weight: 600; }
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: DONE Build complete。

- [ ] **Step 4: Commit**

```bash
git add frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/pages/vocabulary/index.vue
git commit -m "feat(frontend): 词力通词卡展示配图+英文描述+双音频播放"
```

### Task 7: 集成验证 + 归档 D-101

- [ ] **Step 1: 后端全量** `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -q -p no:randomly` 期望全绿（352 + 本次新增）。
- [ ] **Step 2: 前端 build** `cd frontend/miniprogram && npm run build:mp-weixin` 通过。
- [ ] **Step 3: 归档 D-101**（docs/决策归档.md 顶部）：图背单词 MVP（媒体字段 + provider dev-mock + 媒体 service + 4 admin 端点 + 学生端 published 媒体 + 前端词卡展示）；明确 dev-mock 不花钱、真文生图/真 TTS/看图选词/真实 COS 上传留后续；迁移 0016。
- [ ] **Step 4: Commit +（征得同意后）push**

---

## 备注
- **dev-mock 边界**：图用 placehold.co、音频用 mock-tts.local 占位 URL（音频实际不可播放，仅验证 UI/数据流）；真生成接缝 `image_provider`/`tts_provider != "mock"` 时走 `_real_*`（未实现，留预算确认后）。
- **媒体审核闸门**：生成默认 `draft`，学生端只见 `published`（与 D-095/096 一致）。
- **向后兼容**：存量词 media_status 默认 draft、媒体字段 NULL → 学生端回退纯文本词卡，不影响 D-100 已有流程。
