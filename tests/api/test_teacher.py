"""教师端测试。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.schemas.teacher import (
    BecomeTeacherRequest,
    BindTeacherRequest,
    InviteCodeOut,
    TeacherCommentCreate,
    TeacherCommentOut,
    TeacherProfileOut,
    TeacherStudentOut,
)


# ── Schema 单元测试 ────────────────────────────────────────────────────────────


def test_become_teacher_request_optional_subject():
    req = BecomeTeacherRequest()
    assert req.subject is None


def test_become_teacher_request_with_subject():
    req = BecomeTeacherRequest(subject="英语")
    assert req.subject == "英语"


def test_bind_teacher_request_validates_length():
    req = BindTeacherRequest(code="ABC123")
    assert req.code == "ABC123"


def test_teacher_comment_create_schema():
    req = TeacherCommentCreate(comment_text="注意时态用法")
    assert req.comment_text == "注意时态用法"


def test_teacher_comment_out_schema():
    now = datetime.now(timezone.utc)
    out = TeacherCommentOut(
        id=uuid.uuid4(),
        wrong_question_id=uuid.uuid4(),
        teacher_id=uuid.uuid4(),
        comment_text="该题考查时态",
        created_at=now,
    )
    assert out.comment_text == "该题考查时态"
