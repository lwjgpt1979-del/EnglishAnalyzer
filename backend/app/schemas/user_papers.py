"""V2 整卷上传 OCR 拆题 Pydantic schemas（D-089 / M4）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserPaperCreate(BaseModel):
    """学生提交整卷：一张或多张试卷图片 URL（已通过 upload 预签名上传到 COS）。"""
    source_image_urls: list[str] = Field(..., min_length=1, max_length=20)
    title: str | None = Field(None, max_length=100)


class UserPaperQuestionOut(BaseModel):
    """拆出来的单题。"""
    id: uuid.UUID
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None
    is_wrong: bool
    passage: str | None = None       # 所属短文/语篇(完形/阅读;独立题为空)
    block_key: str | None = None     # 同篇小问共享的分组键
    node_id: uuid.UUID | None = None # 命中的知识节点(语法可加入作业精讲·语法)
    kp_name: str | None = None       # 归类知识点名
    kp_kind: str | None = None       # 'grammar'=考语法 / 'vocab'=考词汇 / 其它 None


class UserPaperSectionOut(BaseModel):
    """原卷大题/板块(还原题型结构):单项选择 / 完形填空 / 阅读理解…"""
    id: uuid.UUID
    label: str
    section_type: str | None = None
    is_suggested: bool = False       # True=AI 建议分类(原卷没识别到大题头),前端标「建议」、学生可改
    questions: list[UserPaperQuestionOut]


class SectionUpdateIn(BaseModel):
    """学生修改大题的题型分类。"""
    label: str = Field(..., min_length=1, max_length=40)


class AnalyzeSentenceIn(BaseModel):
    """P3:按需解析一句长难句;save 时可带来源卷(作业精讲按批次归组)。"""
    sentence: str = Field(..., min_length=1, max_length=600)
    paper_id: uuid.UUID | None = None


class UserPaperOut(BaseModel):
    """试卷概要（列表用）。"""
    id: uuid.UUID
    title: str | None
    source_image_urls: list[str]
    ocr_status: str | None
    question_count: int
    created_at: datetime


class UserPaperDetailOut(UserPaperOut):
    """试卷详情：概要 + 按原卷大题分组的结构(sections) + 扁平题目列表(questions,兼容)。"""
    sections: list[UserPaperSectionOut] = []
    questions: list[UserPaperQuestionOut]


class UserPaperListOut(BaseModel):
    items: list[UserPaperOut]
    total: int
