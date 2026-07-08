"""V2 课程浏览 Pydantic schemas（D-079 / M2）。"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ─── AI 生成输出结构（curriculum_ai_service → curriculum_service.persist_unit）─

class AIWordItem(BaseModel):
    word: str
    phonetic: str | None = None
    definitions: list[dict] = Field(
        ..., description="[{pos: 'n.', meaning: '苹果'}, ...]"
    )
    examples: list[str] = []
    difficulty: int = Field(..., ge=1, le=5)
    is_core: bool = True


_KP_CATEGORIES = {"grammar", "vocabulary", "reading", "writing", "listening"}
# DeepSeek 偶尔返回白名单外的分类(如 speaking / translation),归一化避免单个分类值
# 让整单元校验失败(category 在 KP-First 流程里不参与落库，仅作标签)。
_KP_CATEGORY_ALIASES = {
    "speaking": "listening", "speak": "listening", "口语": "listening", "听说": "listening",
    "translation": "writing", "翻译": "writing", "语法": "grammar", "词汇": "vocabulary",
    "阅读": "reading", "写作": "writing", "听力": "listening",
}


class AIKnowledgePointItem(BaseModel):
    code: str = Field(..., description="全局唯一编码，例如 'yl-g5s1-u1-kp1'")
    name: str
    category: Literal["grammar", "vocabulary", "reading", "writing", "listening"]
    description: str

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, v: object) -> str:
        if not isinstance(v, str):
            return "vocabulary"
        s = v.strip().lower()
        if s in _KP_CATEGORIES:
            return s
        return _KP_CATEGORY_ALIASES.get(s, "vocabulary")
    contents: dict[str, str] = Field(
        default_factory=dict,
        description="key ∈ {listening, vocabulary, grammar, reading, translation, writing}, value 为 markdown。"
                    "骨架生成(上传阶段)留空，六维讲解按需延后生成。",
    )


class AIGeneratedUnit(BaseModel):
    textbook_version: str
    grade: str
    semester: Literal["上", "下"]
    unit_no: int = Field(..., ge=1, le=20)
    unit_title: str
    knowledge_points: list[AIKnowledgePointItem] = Field(..., min_length=3)
    words: list[AIWordItem] = Field(..., min_length=5)


class AIUnitPassage(BaseModel):
    """单元析出的一篇短文/范文(原样抽取)。kind ∈ 听力/阅读/写作。"""
    kind: Literal["听力", "阅读", "写作"]
    title: str | None = None
    text: str


class UnitPassageOut(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    kind: str
    title: str | None = None
    text: str
    sort_order: int = 0


# ─── API 响应 ───────────────────────────────────────────────────────────────

class UnitOut(BaseModel):
    id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    unit_no: int
    unit_title: str
    locked: bool = Field(..., description="是否需付费解锁（unit_no=1 永远 false）")
    kp_count: int = 0


class KnowledgePointOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: str
    description: str | None = None


class WordOut(BaseModel):
    id: uuid.UUID
    word: str
    phonetic: str | None = None
    definitions: list[dict] = []
    difficulty: int


class UnitDetailOut(UnitOut):
    knowledge_points: list[KnowledgePointOut] = []
    words: list[WordOut] = []


class KPContentOut(BaseModel):
    """考点讲解的一个「教学环节」(按考点类型自适应,见 kp_lecture_service.LECTURE_TEMPLATES)。"""
    section_key: str      # concept | rule | examples | pitfalls | ...(随类型)
    title: str            # 环节中文标题(如 概念点破 / 例句精讲)
    content_md: str
    media_url: str | None = None


# ─── 运营审核/编辑（M5）：运营可见完整字段，仅 platform_admin 可访问 ────────────

class AdminContentItem(BaseModel):
    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    dimension: str
    content_md: str
    audio_url: str | None = None
    status: str
    generated_by: str


class AdminContentListOut(BaseModel):
    total: int
    items: list[AdminContentItem]


class ContentReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published，false=驳回→retired")


class ContentUpdateRequest(BaseModel):
    content_md: str | None = Field(None, min_length=1, description="修订后的正文 Markdown")
    audio_url: str | None = Field(None, description="音频 URL（可选）")


class KPSearchItem(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    description: str | None = None


class UnitDeleteIn(BaseModel):
    """批量删除单元（连带知识图谱边 / 单词通词表 / 短文及考点边）。"""
    unit_ids: list[uuid.UUID] = Field(..., min_length=1)
