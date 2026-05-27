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


# ── Service 集成测试（需要真实 DB）─────────────────────────────────────────────

from app.core.database import _async_session_factory
from app.services.auth_service import upsert_user
from app.services.teacher_service import (
    add_comment,
    become_teacher,
    bind_with_teacher,
    generate_invite_code,
    get_comments_for_wq,
    get_my_students,
    get_student_wrong_questions,
)
from app.models.d3_wrong_questions import WrongQuestion, TeacherComment
from app.core.exceptions import AppError


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student_user(db_session):
    user = await upsert_user(db_session, openid=f"teacher_svc_student_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def teacher_user(db_session):
    user = await upsert_user(db_session, openid=f"teacher_svc_teacher_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    data = BecomeTeacherRequest(subject="英语")
    await become_teacher(db_session, user=user, data=data)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_become_teacher_creates_record(db_session, student_user):
    data = BecomeTeacherRequest(subject="英语")
    teacher = await become_teacher(db_session, user=student_user, data=data)
    await db_session.flush()

    assert teacher.id == student_user.id
    assert teacher.subject == "英语"
    assert student_user.role == "teacher"


@pytest.mark.asyncio
async def test_become_teacher_is_idempotent(db_session, student_user):
    data = BecomeTeacherRequest(subject="英语")
    t1 = await become_teacher(db_session, user=student_user, data=data)
    await db_session.flush()
    t2 = await become_teacher(db_session, user=student_user, data=data)
    assert t1.id == t2.id


@pytest.mark.asyncio
async def test_generate_invite_code(db_session, teacher_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()

    assert len(invite.code) == 6
    assert invite.code == invite.code.upper()
    assert invite.type == "teacher_bind"
    assert invite.used_at is None


@pytest.mark.asyncio
async def test_bind_with_teacher_success(db_session, teacher_user, student_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()

    relation = await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    assert relation.teacher_id == teacher_user.id
    assert relation.student_id == student_user.id
    assert relation.status == "active"
    assert invite.used_at is not None


@pytest.mark.asyncio
async def test_bind_with_teacher_invalid_code_raises(db_session, student_user):
    with pytest.raises(AppError) as exc_info:
        await bind_with_teacher(db_session, student=student_user, code="XXXXXX")
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_bind_with_teacher_already_bound_raises(db_session, teacher_user, student_user):
    invite1 = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite1.code)
    await db_session.flush()

    invite2 = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    with pytest.raises(AppError) as exc_info:
        await bind_with_teacher(db_session, student=student_user, code=invite2.code)
    assert exc_info.value.code == 409


@pytest.mark.asyncio
async def test_get_my_students(db_session, teacher_user, student_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    students = await get_my_students(db_session, teacher_id=teacher_user.id)
    assert len(students) == 1
    assert students[0].student_id == student_user.id


@pytest.mark.asyncio
async def test_add_comment_success(db_session, teacher_user, student_user):
    # 先绑定
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    # 创建错题
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_user.id,
        source_image_url="https://example.com/img.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    # 老师批注
    comment = await add_comment(
        db_session,
        teacher_id=teacher_user.id,
        wq_id=wq.id,
        data=TeacherCommentCreate(comment_text="注意时态"),
    )
    await db_session.flush()

    assert comment.comment_text == "注意时态"
    assert comment.teacher_id == teacher_user.id
    assert comment.wrong_question_id == wq.id


@pytest.mark.asyncio
async def test_add_comment_unbound_teacher_raises(db_session, teacher_user, student_user):
    # 未绑定直接批注
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_user.id,
        source_image_url="https://example.com/img2.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await add_comment(
            db_session,
            teacher_id=teacher_user.id,
            wq_id=wq.id,
            data=TeacherCommentCreate(comment_text="应该报错"),
        )
    assert exc_info.value.code == 403


@pytest.mark.asyncio
async def test_get_comments_for_wq(db_session, teacher_user, student_user):
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_user.id,
        source_image_url="https://example.com/img3.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    await add_comment(db_session, teacher_id=teacher_user.id, wq_id=wq.id,
                      data=TeacherCommentCreate(comment_text="批注1"))
    await add_comment(db_session, teacher_id=teacher_user.id, wq_id=wq.id,
                      data=TeacherCommentCreate(comment_text="批注2"))
    await db_session.flush()

    comments = await get_comments_for_wq(db_session, wq_id=wq.id)
    assert len(comments) == 2
    assert comments[0].comment_text == "批注1"


@pytest.mark.asyncio
async def test_get_student_wrong_questions(db_session, teacher_user, student_user):
    # 绑定师生
    invite = await generate_invite_code(db_session, teacher_id=teacher_user.id)
    await db_session.flush()
    await bind_with_teacher(db_session, student=student_user, code=invite.code)
    await db_session.flush()

    # 创建2道错题
    for i in range(2):
        wq = WrongQuestion(
            id=uuid.uuid4(),
            student_id=student_user.id,
            source_image_url=f"https://example.com/img_svc_{i}.jpg",
            is_mastered=False,
        )
        db_session.add(wq)
    await db_session.flush()

    wqs = await get_student_wrong_questions(
        db_session, teacher_id=teacher_user.id, student_id=student_user.id
    )
    assert len(wqs) == 2
    # 验证未绑定教师无法查看
    other_teacher = await upsert_user(db_session, openid=f"other_t_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    with pytest.raises(AppError) as exc_info:
        await get_student_wrong_questions(
            db_session, teacher_id=other_teacher.id, student_id=student_user.id
        )
    assert exc_info.value.code == 403

# ── API 集成测试 ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def student_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"teacher_api_stu_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest_asyncio.fixture
async def teacher_headers(client: AsyncClient):
    """学生登录后立即升级为教师，返回 headers。"""
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"teacher_api_tch_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # 升级为教师
    become_resp = await client.post(
        "/api/v1/teacher/profile", json={"subject": "英语"}, headers=headers
    )
    assert become_resp.status_code == 200, become_resp.text
    return headers


@pytest.mark.asyncio
async def test_become_teacher_api(client: AsyncClient, student_headers):
    resp = await client.post(
        "/api/v1/teacher/profile",
        json={"subject": "英语"},
        headers=student_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["cert_status"] == "uncertified"
    assert data["subject"] == "英语"
    assert data["max_students"] == 50


@pytest.mark.asyncio
async def test_create_invite_code_requires_teacher(client: AsyncClient, student_headers):
    """未升级为教师的用户不能生成邀请码。"""
    resp = await client.post("/api/v1/teacher/invite-code", headers=student_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_invite_code_api(client: AsyncClient, teacher_headers):
    resp = await client.post("/api/v1/teacher/invite-code", headers=teacher_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["code"]) == 6
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_bind_teacher_api(client: AsyncClient, teacher_headers, student_headers):
    """学生用邀请码绑定老师。"""
    # 教师生成邀请码
    invite_resp = await client.post(
        "/api/v1/teacher/invite-code", headers=teacher_headers
    )
    code = invite_resp.json()["data"]["code"]

    # 学生绑定
    bind_resp = await client.post(
        "/api/v1/teacher/bind", json={"code": code}, headers=student_headers
    )
    assert bind_resp.status_code == 200
    data = bind_resp.json()["data"]
    assert "student_id" in data
    assert "bound_at" in data


@pytest.mark.asyncio
async def test_list_students_api(client: AsyncClient, teacher_headers, student_headers):
    """绑定后教师可查看学生列表。"""
    invite_resp = await client.post(
        "/api/v1/teacher/invite-code", headers=teacher_headers
    )
    code = invite_resp.json()["data"]["code"]
    await client.post(
        "/api/v1/teacher/bind", json={"code": code}, headers=student_headers
    )

    list_resp = await client.get("/api/v1/teacher/students", headers=teacher_headers)
    assert list_resp.status_code == 200
    students = list_resp.json()["data"]
    assert len(students) >= 1


@pytest.mark.asyncio
async def test_add_comment_and_get_comments_api(
    client: AsyncClient, teacher_headers, student_headers
):
    """老师批注 + 学生/老师读批注。"""
    # 绑定
    invite_resp = await client.post(
        "/api/v1/teacher/invite-code", headers=teacher_headers
    )
    code = invite_resp.json()["data"]["code"]
    await client.post(
        "/api/v1/teacher/bind", json={"code": code}, headers=student_headers
    )

    # 学生创建错题
    wq_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://example.com/teacher_comment_test.jpg"},
        headers=student_headers,
    )
    assert wq_resp.status_code == 200, wq_resp.text
    wq_id = wq_resp.json()["data"]["id"]

    # 老师批注
    comment_resp = await client.post(
        f"/api/v1/teacher/wrong-questions/{wq_id}/comments",
        json={"comment_text": "注意主谓一致"},
        headers=teacher_headers,
    )
    assert comment_resp.status_code == 200
    assert comment_resp.json()["data"]["comment_text"] == "注意主谓一致"

    # 读取批注（老师读）
    get_resp = await client.get(
        f"/api/v1/teacher/wrong-questions/{wq_id}/comments",
        headers=teacher_headers,
    )
    assert get_resp.status_code == 200
    comments = get_resp.json()["data"]
    assert len(comments) == 1
    assert comments[0]["comment_text"] == "注意主谓一致"

    # 读取批注（学生读）
    student_get = await client.get(
        f"/api/v1/teacher/wrong-questions/{wq_id}/comments",
        headers=student_headers,
    )
    assert student_get.status_code == 200
    assert len(student_get.json()["data"]) == 1
