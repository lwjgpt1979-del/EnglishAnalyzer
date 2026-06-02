# M1: V2 数据模型基础 + 学期会员重构（Plan N）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development

**Goal:** V2 演进第一阶段（详见 `docs/v2-evolution-plan.md` 第四节 M1）：
1. 把 V2 的 9 张新表 + 3 张改表落到数据库（迁移 0007 + 0008）
2. 重构会员/订单：按学期计价（价格从 `system_configs` 读，可由运营改 SQL）
3. 鉴权改为：`purchased_semesters` 覆盖检查（替代旧 membership.tier 鉴权）
4. 完善资料 onboarding 加教材偏好（教材/年级/学期）
5. 前端 profile 旧"档位×月数"购买 UI 作废，改"学期详情页 → 三档"模式（M1 阶段先做后端 + 最简前端，UI 完整态留 M2）

**Architecture:**
- 新旧并存：旧 `wrong_questions` 表、旧 `memberships` 表保留只读；新流量走 V2 表
- 价格运营可配：`system_configs.key='semester_pricing'` 存 JSON `{basic:39, pro:79, promax:159}`，pricing_service 读它
- 鉴权 helper：`semester_access_service.assert_can_access(user, textbook, grade, semester, required_tier)` 统一入口
- M1 不做：教材内容、真题、仿真题（M2/M3）、整卷上传（M4）、运营后台（M5）

**Tech Stack:** FastAPI · SQLAlchemy 2.x · Pydantic v2 · pytest-asyncio STRICT · uni-app Vue3

---

## File Structure

```
新增后端:
  backend/alembic/versions/0007_v2_curriculum_tables.py
  backend/alembic/versions/0008_v2_user_order_extensions.py
  backend/app/models/d11_v2_curriculum.py        # 域11: V2 教材内容 (knowledge_point_contents)
  backend/app/models/d12_v2_exams.py             # 域12: V2 真题/仿真题
  backend/app/models/d13_v2_user_papers.py       # 域13: V2 整卷上传
  backend/app/models/d14_v2_semesters.py         # 域14: V2 学期会员
  backend/app/schemas/semesters.py               # 学期相关 schemas
  backend/app/services/pricing_service.py        # 学期定价（读 system_configs）
  backend/app/services/semester_service.py       # purchased_semesters CRUD + 鉴权
  tests/api/test_m1_semesters.py

修改后端:
  backend/app/models/d1_users.py                 # User 加 preferred_*
  backend/app/models/d2_payments.py              # Order 加 semester_count, purchased_semester_ids
  backend/app/models/__init__.py                 # +d11~d14 imports
  backend/app/services/order_service.py          # 改 create_order 走学期计价
  backend/app/services/membership_service.py     # ⚠️ 部分作废（保留旧函数标记 @deprecated；新流走 semester_service）
  backend/app/api/v1/orders.py                   # 下单加 semester 字段
  backend/app/schemas/payments.py                # OrderCreate 加 semesters 字段
  backend/app/api/v1/auth.py                     # complete-profile 加 preferred_* 字段
  backend/app/schemas/compliance.py              # CompleteProfileRequest 加教材字段
  backend/app/services/auth_service.py           # complete_profile 写入 preferred_*

修改前端:
  frontend/miniprogram/src/types/api.ts          # +Semester / PriceConfig / PurchasedSemester 类型
  frontend/miniprogram/src/api/semesters.ts      # 新：学期相关 API
  frontend/miniprogram/src/pages/auth/complete-profile.vue   # 加教材/年级/学期 picker
  frontend/miniprogram/src/pages/profile/index.vue           # 旧购买区改提示"V2 学期购买入口待定"占位
```

**Key facts to confirm before coding:**
- 现有 invite_code_type enum: `relative_bind / institution_join / teacher_bind`（不动）
- 现有 cert_status_enum, bind_*_enum 等（不动）
- 当前迁移链尾：`0006`（D-074）
- semester_pricing 默认值：`{"basic": 39, "pro": 79, "promax": 159}`（运营改 system_configs.value 即可）
- 种子教材：译林版（textbook_version='译林版'），grade=`小学5年级`/`初中7年级`，semester=`上`/`下`

---

## Task 0: 迁移 0007 — V2 核心表 (9 张) + 模型文件

**Files:**
- Create: `backend/alembic/versions/0007_v2_curriculum_tables.py`
- Create: `backend/app/models/d11_v2_curriculum.py`
- Create: `backend/app/models/d12_v2_exams.py`
- Create: `backend/app/models/d13_v2_user_papers.py`
- Create: `backend/app/models/d14_v2_semesters.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 4 个模型文件**

`d11_v2_curriculum.py`（教材深度内容）：
```python
"""域11: V2 教材深度内容 (1 张表)
  knowledge_point_contents
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base

dimension_enum = sa.Enum(
    "listening", "dictation", "grammar", "writing",
    name="content_dimension",
)
content_status_enum = sa.Enum(
    "draft", "reviewing", "published", "retired",
    name="content_status",
)
generated_by_enum = sa.Enum(
    "ai_full", "ai_with_human_review",
    name="content_generated_by",
)


class KnowledgePointContent(Base):
    """每个知识点 × 4 维度（听/听写/语法/写作）的 AI 解读内容。"""
    __tablename__ = "knowledge_point_contents"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_point_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False
    )
    dimension = mapped_column(dimension_enum, nullable=False)
    content_md = mapped_column(sa.Text, nullable=False)
    audio_url = mapped_column(sa.String, nullable=True)
    example_json = mapped_column(JSONB, nullable=True)
    status = mapped_column(content_status_enum, nullable=False, server_default=sa.text("'draft'"))
    generated_by = mapped_column(generated_by_enum, nullable=False)
    reviewed_by = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("knowledge_point_id", "dimension", name="uix_kp_dimension"),
    )
```

`d12_v2_exams.py`（真题 + 仿真题）：
```python
"""域12: V2 真题与仿真题 (4 张表)
  exam_papers · exam_questions · exam_question_knowledge_points · simulated_questions
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base
from .d1_users import semester_enum
from .d6_ai_questions import ai_question_type_enum

exam_source_enum = sa.Enum("official_seed", "teacher_upload", name="exam_source")
exam_status_enum = sa.Enum("draft", "published", "retired", name="exam_status")
sim_status_enum = sa.Enum("draft", "reviewing", "published", "retired", name="sim_status")


class ExamPaper(Base):
    __tablename__ = "exam_papers"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = mapped_column(exam_source_enum, nullable=False)
    uploader_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    class_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    region = mapped_column(sa.String, nullable=True)
    title = mapped_column(sa.String, nullable=False)
    paper_url = mapped_column(sa.String, nullable=True)
    ocr_status = mapped_column(sa.String, nullable=True)
    status = mapped_column(exam_status_enum, nullable=False, server_default=sa.text("'draft'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_papers.id"), nullable=False)
    question_no = mapped_column(sa.String, nullable=False)
    question_type = mapped_column(ai_question_type_enum, nullable=False)
    stem = mapped_column(sa.Text, nullable=False)
    options = mapped_column(JSONB, nullable=True)
    answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class ExamQuestionKnowledgePoint(Base):
    __tablename__ = "exam_question_knowledge_points"
    exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), primary_key=True)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True)
    relevance = mapped_column(sa.SmallInteger, nullable=False, server_default=sa.text("100"))


class SimulatedQuestion(Base):
    __tablename__ = "simulated_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False)
    question_type = mapped_column(ai_question_type_enum, nullable=False)
    stem = mapped_column(sa.Text, nullable=False)
    options = mapped_column(JSONB, nullable=True)
    answer = mapped_column(sa.Text, nullable=False)
    explanation = mapped_column(sa.Text, nullable=True)
    difficulty = mapped_column(sa.SmallInteger, nullable=False)
    generation_metadata = mapped_column(JSONB, nullable=True)
    status = mapped_column(sim_status_enum, nullable=False, server_default=sa.text("'draft'"))
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())
```

`d13_v2_user_papers.py`（用户上传整卷）：
```python
"""域13: V2 学生整卷上传 (3 张表)
  user_uploaded_papers · user_paper_questions · user_paper_question_knowledge_points
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column
from .base import Base
from .d6_ai_questions import ai_question_type_enum


class UserUploadedPaper(Base):
    __tablename__ = "user_uploaded_papers"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    title = mapped_column(sa.String, nullable=True)
    source_image_urls = mapped_column(JSONB, nullable=False)
    ocr_status = mapped_column(sa.String, nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class UserPaperQuestion(Base):
    __tablename__ = "user_paper_questions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_paper_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_uploaded_papers.id"), nullable=False)
    question_no = mapped_column(sa.String, nullable=True)
    question_type = mapped_column(ai_question_type_enum, nullable=True)
    stem = mapped_column(sa.Text, nullable=True)
    student_answer = mapped_column(sa.Text, nullable=True)
    correct_answer = mapped_column(sa.Text, nullable=True)
    explanation = mapped_column(sa.Text, nullable=True)
    is_wrong = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    matched_exam_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())


class UserPaperQuestionKnowledgePoint(Base):
    __tablename__ = "user_paper_question_knowledge_points"
    user_paper_question_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("user_paper_questions.id"), primary_key=True)
    knowledge_point_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True)
```

`d14_v2_semesters.py`（已购学期）：
```python
"""域14: V2 学期会员 (1 张表)
  purchased_semesters
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column
from .base import Base
from .d1_users import semester_enum
from .d2_payments import order_tier_enum


class PurchasedSemester(Base):
    """用户已购买的学期会员。一行 = 一个 (用户, 教材, 年级, 学期, 档位, 6 个月有效期)。"""
    __tablename__ = "purchased_semesters"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    tier = mapped_column(order_tier_enum, nullable=False)
    semester_no = mapped_column(sa.SmallInteger, nullable=False)
    started_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    order_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_purchased_semesters_user_lookup",
                 "user_id", "textbook_version", "grade", "semester"),
    )
```

- [ ] **Step 2: 修改 `backend/app/models/__init__.py` 加 4 个新域 imports**

```python
# 域11: V2 教材深度内容 (1 张表)
from .d11_v2_curriculum import KnowledgePointContent  # noqa: F401

# 域12: V2 真题与仿真题 (4 张表)
from .d12_v2_exams import (  # noqa: F401
    ExamPaper, ExamQuestion, ExamQuestionKnowledgePoint, SimulatedQuestion,
)

# 域13: V2 学生整卷上传 (3 张表)
from .d13_v2_user_papers import (  # noqa: F401
    UserUploadedPaper, UserPaperQuestion, UserPaperQuestionKnowledgePoint,
)

# 域14: V2 学期会员 (1 张表)
from .d14_v2_semesters import PurchasedSemester  # noqa: F401
```

- [ ] **Step 3: 创建迁移 0007**

```python
"""v2_curriculum_tables: 9 V2 core tables (M1 / D-079)

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— enums ——
    op.execute("CREATE TYPE content_dimension AS ENUM ('listening', 'dictation', 'grammar', 'writing')")
    op.execute("CREATE TYPE content_status AS ENUM ('draft', 'reviewing', 'published', 'retired')")
    op.execute("CREATE TYPE content_generated_by AS ENUM ('ai_full', 'ai_with_human_review')")
    op.execute("CREATE TYPE exam_source AS ENUM ('official_seed', 'teacher_upload')")
    op.execute("CREATE TYPE exam_status AS ENUM ('draft', 'published', 'retired')")
    op.execute("CREATE TYPE sim_status AS ENUM ('draft', 'reviewing', 'published', 'retired')")

    # —— knowledge_point_contents ——
    op.create_table(
        "knowledge_point_contents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("dimension", sa.Enum("listening", "dictation", "grammar", "writing", name="content_dimension", create_type=False), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("audio_url", sa.String, nullable=True),
        sa.Column("example_json", JSONB, nullable=True),
        sa.Column("status", sa.Enum("draft", "reviewing", "published", "retired", name="content_status", create_type=False), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("generated_by", sa.Enum("ai_full", "ai_with_human_review", name="content_generated_by", create_type=False), nullable=False),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("knowledge_point_id", "dimension", name="uix_kp_dimension"),
    )

    # —— exam_papers ——
    op.create_table(
        "exam_papers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.Enum("official_seed", "teacher_upload", name="exam_source", create_type=False), nullable=False),
        sa.Column("uploader_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("class_id", UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True),
        sa.Column("textbook_version", sa.String, nullable=False),
        sa.Column("grade", sa.String, nullable=False),
        sa.Column("semester", sa.Enum(name="semester", create_type=False), nullable=False),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("paper_url", sa.String, nullable=True),
        sa.Column("ocr_status", sa.String, nullable=True),
        sa.Column("status", sa.Enum("draft", "published", "retired", name="exam_status", create_type=False), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— exam_questions ——
    op.create_table(
        "exam_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("exam_papers.id"), nullable=False),
        sa.Column("question_no", sa.String, nullable=False),
        sa.Column("question_type", sa.Enum(name="ai_question_type", create_type=False), nullable=False),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("difficulty", sa.SmallInteger, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— exam_question_knowledge_points ——
    op.create_table(
        "exam_question_knowledge_points",
        sa.Column("exam_question_id", UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), primary_key=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True),
        sa.Column("relevance", sa.SmallInteger, nullable=False, server_default=sa.text("100")),
    )

    # —— simulated_questions ——
    op.create_table(
        "simulated_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_exam_question_id", UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("question_type", sa.Enum(name="ai_question_type", create_type=False), nullable=False),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("difficulty", sa.SmallInteger, nullable=False),
        sa.Column("generation_metadata", JSONB, nullable=True),
        sa.Column("status", sa.Enum("draft", "reviewing", "published", "retired", name="sim_status", create_type=False), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— user_uploaded_papers ——
    op.create_table(
        "user_uploaded_papers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String, nullable=True),
        sa.Column("source_image_urls", JSONB, nullable=False),
        sa.Column("ocr_status", sa.String, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— user_paper_questions ——
    op.create_table(
        "user_paper_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_paper_id", UUID(as_uuid=True), sa.ForeignKey("user_uploaded_papers.id"), nullable=False),
        sa.Column("question_no", sa.String, nullable=True),
        sa.Column("question_type", sa.Enum(name="ai_question_type", create_type=False), nullable=True),
        sa.Column("stem", sa.Text, nullable=True),
        sa.Column("student_answer", sa.Text, nullable=True),
        sa.Column("correct_answer", sa.Text, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("is_wrong", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("matched_exam_question_id", UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— user_paper_question_knowledge_points ——
    op.create_table(
        "user_paper_question_knowledge_points",
        sa.Column("user_paper_question_id", UUID(as_uuid=True), sa.ForeignKey("user_paper_questions.id"), primary_key=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True),
    )

    # —— purchased_semesters ——
    op.create_table(
        "purchased_semesters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("textbook_version", sa.String, nullable=False),
        sa.Column("grade", sa.String, nullable=False),
        sa.Column("semester", sa.Enum(name="semester", create_type=False), nullable=False),
        sa.Column("tier", sa.Enum(name="order_tier", create_type=False), nullable=False),
        sa.Column("semester_no", sa.SmallInteger, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_purchased_semesters_user_lookup",
        "purchased_semesters",
        ["user_id", "textbook_version", "grade", "semester"],
    )


def downgrade() -> None:
    op.drop_index("ix_purchased_semesters_user_lookup", table_name="purchased_semesters")
    op.drop_table("purchased_semesters")
    op.drop_table("user_paper_question_knowledge_points")
    op.drop_table("user_paper_questions")
    op.drop_table("user_uploaded_papers")
    op.drop_table("simulated_questions")
    op.drop_table("exam_question_knowledge_points")
    op.drop_table("exam_questions")
    op.drop_table("exam_papers")
    op.drop_table("knowledge_point_contents")
    for t in ["content_dimension", "content_status", "content_generated_by",
              "exam_source", "exam_status", "sim_status"]:
        op.execute(f"DROP TYPE {t}")
```

- [ ] **Step 4: 跑迁移 + 全量测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer" alembic upgrade head
/opt/anaconda3/bin/python -m pytest ../tests/ -q
```
Expected: `Running upgrade 0006 -> 0007`；全量仍 PASS（223）

**注意 test_model_structure 表数量校验**：若该测试硬编码"37 张表"或类似，需要更新到 +9=46（或基于当前数加 9）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/d11_v2_curriculum.py backend/app/models/d12_v2_exams.py \
        backend/app/models/d13_v2_user_papers.py backend/app/models/d14_v2_semesters.py \
        backend/app/models/__init__.py \
        backend/alembic/versions/0007_v2_curriculum_tables.py \
        tests/models/test_model_structure.py  # 如果改了表数量
git commit -m "feat(db): migration 0007 — V2 9 new tables (curriculum/exams/user-papers/semesters)"
```

---

## Task 1: 迁移 0008 — User/Order 扩展 + system_configs 价格 seed

**Files:**
- Create: `backend/alembic/versions/0008_v2_user_order_extensions.py`
- Modify: `backend/app/models/d1_users.py`
- Modify: `backend/app/models/d2_payments.py`

- [ ] **Step 1: User 模型加 preferred_* 字段**

在 `d1_users.User` 类内（compliance 字段之后、updated_at 之前）追加：
```python
    # —— V2 教材偏好（D-079 / M1）——
    preferred_textbook_version = mapped_column(sa.String, nullable=True)
    preferred_grade = mapped_column(sa.String, nullable=True)
    preferred_semester = mapped_column(semester_enum, nullable=True)
```

- [ ] **Step 2: Order 模型加 V2 字段**

在 `d2_payments.Order` 类内（updated_at 之前）追加：
```python
    # —— V2 学期会员（D-079 / M1）——
    semester_count = mapped_column(sa.SmallInteger, nullable=True)
    purchased_semester_ids = mapped_column(JSONB, nullable=True)  # 下单时指定要购买哪些学期
```
需要 `from sqlalchemy.dialects.postgresql import JSONB`（确认已 import）。

- [ ] **Step 3: 创建迁移 0008**

```python
"""v2_user_order_extensions: users +preferred_*; orders +semester_count, purchased_semester_ids; system_configs seed pricing

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import json
import uuid

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— users +preferred_* ——
    op.add_column("users", sa.Column("preferred_textbook_version", sa.String, nullable=True))
    op.add_column("users", sa.Column("preferred_grade", sa.String, nullable=True))
    op.add_column("users", sa.Column("preferred_semester", sa.Enum(name="semester", create_type=False), nullable=True))

    # —— orders +V2 ——
    op.add_column("orders", sa.Column("semester_count", sa.SmallInteger, nullable=True))
    op.add_column("orders", sa.Column("purchased_semester_ids", JSONB, nullable=True))

    # —— system_configs 插入价格种子 ——
    # 需要某个 admin user_id；用 NULL 不行（updated_by NOT NULL），所以这里写一个固定占位
    # 实际：检查 system_configs 表是否允许 updated_by null；当前定义是 NOT NULL
    # 改用：插入时找一个已存在的 user（platform_admin 优先），没有就跳过 seed，让运营手动添加
    conn = op.get_bind()
    # 找 platform_admin；没有就找最早的 user；都没就跳过
    admin = conn.execute(sa.text(
        "SELECT id FROM users WHERE role='platform_admin' ORDER BY created_at LIMIT 1"
    )).fetchone()
    if not admin:
        admin = conn.execute(sa.text(
            "SELECT id FROM users ORDER BY created_at LIMIT 1"
        )).fetchone()
    if admin:
        conn.execute(sa.text("""
            INSERT INTO system_configs (id, key, value, description, updated_by, created_at, updated_at)
            VALUES (:id, 'semester_pricing', :val, '学期会员定价（单位：元/学期）', :admin, now(), now())
            ON CONFLICT (key) DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "val": json.dumps({"basic": 39, "pro": 79, "promax": 159}),
            "admin": str(admin[0]),
        })


def downgrade() -> None:
    op.execute("DELETE FROM system_configs WHERE key='semester_pricing'")
    op.drop_column("orders", "purchased_semester_ids")
    op.drop_column("orders", "semester_count")
    op.drop_column("users", "preferred_semester")
    op.drop_column("users", "preferred_grade")
    op.drop_column("users", "preferred_textbook_version")
```

- [ ] **Step 4: 跑迁移 + 测试**

```bash
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer" alembic upgrade head
/opt/anaconda3/bin/python -m pytest ../tests/ -q
```

- [ ] **Step 5: 提交**

```bash
git add backend/alembic/versions/0008_v2_user_order_extensions.py \
        backend/app/models/d1_users.py backend/app/models/d2_payments.py
git commit -m "feat(db): migration 0008 — V2 user/order extensions + pricing seed"
```

---

## Task 2: pricing_service + semester_service + 鉴权 helper + 测试

**Files:**
- Create: `backend/app/services/pricing_service.py`
- Create: `backend/app/services/semester_service.py`
- Create: `backend/app/schemas/semesters.py`
- Create: `tests/api/test_m1_semesters.py`

- [ ] **Step 1: 创建 schemas/semesters.py**

```python
"""V2 学期相关 Schemas（D-079 / M1）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SemesterPricing(BaseModel):
    basic: int   # 元/学期
    pro: int
    promax: int


class SemesterIdentity(BaseModel):
    """一个学期的标识（教材+年级+上/下）。"""
    textbook_version: str
    grade: str
    semester: Literal["上", "下"]


class PurchaseSemestersRequest(BaseModel):
    tier: Literal["basic", "pro", "promax"]
    semesters: list[SemesterIdentity] = Field(..., min_length=1, max_length=12)
    target_student_id: uuid.UUID | None = None  # 复用现有代付逻辑


class PurchasedSemesterOut(BaseModel):
    id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    tier: str
    started_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class SemesterAccessOut(BaseModel):
    """查询某教材-年级-学期 的会员可访问性。"""
    textbook_version: str
    grade: str
    semester: str
    accessible: bool
    tier: str | None       # 用户已购最高档；None=未购
    expires_at: datetime | None
```

- [ ] **Step 2: 创建 pricing_service.py**

```python
"""V2 学期定价（从 system_configs 读，运营可改 SQL）。"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig
from app.schemas.semesters import SemesterPricing

DEFAULT_PRICING = SemesterPricing(basic=39, pro=79, promax=159)


async def get_semester_pricing(db: AsyncSession) -> SemesterPricing:
    """读 system_configs.semester_pricing。缺失则返回默认值。"""
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == "semester_pricing"))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        return DEFAULT_PRICING
    data = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    return SemesterPricing(**data)


def calc_total_fen(
    pricing: SemesterPricing, *, tier: str, semester_count: int,
) -> int:
    """计算总金额（分）。tier×单价×学期数。"""
    unit_yuan = {"basic": pricing.basic, "pro": pricing.pro, "promax": pricing.promax}[tier]
    return unit_yuan * semester_count * 100
```

- [ ] **Step 3: 创建 semester_service.py**

```python
"""V2 学期会员服务（D-079 / M1）。

- 鉴权：assert_can_access(user, textbook, grade, semester, required_tier='basic')
- 列出：list_my_semesters
- 创建（订单支付成功后调用）：create_purchased_semesters
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d14_v2_semesters import PurchasedSemester

SEMESTER_DURATION_DAYS = 180  # 6 个月 = 180 天（D-079）
TIER_RANK = {"basic": 1, "pro": 2, "promax": 3}


async def list_my_semesters(
    db: AsyncSession, *, user_id: uuid.UUID,
) -> list[PurchasedSemester]:
    r = await db.execute(
        select(PurchasedSemester)
        .where(PurchasedSemester.user_id == user_id)
        .order_by(PurchasedSemester.expires_at.desc())
    )
    return list(r.scalars().all())


async def query_access(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
) -> tuple[bool, str | None, datetime | None]:
    """返回 (是否可访问, 最高已购 tier, expires_at)。
    
    可访问 = 存在 active(expires_at > now) 的 purchased_semester 覆盖该 (教材,年级,学期)。
    """
    now = datetime.now(timezone.utc)
    r = await db.execute(
        select(PurchasedSemester).where(
            PurchasedSemester.user_id == user_id,
            PurchasedSemester.textbook_version == textbook_version,
            PurchasedSemester.grade == grade,
            PurchasedSemester.semester == semester,
            PurchasedSemester.expires_at > now,
        )
    )
    items = list(r.scalars().all())
    if not items:
        return False, None, None
    # 取 tier 最高 + expires_at 最晚
    best = max(items, key=lambda p: (TIER_RANK[str(p.tier)], p.expires_at))
    return True, str(best.tier), best.expires_at


async def assert_can_access(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
    required_tier: str = "basic",
) -> None:
    """权限 helper。覆盖且 tier ≥ required_tier → 通过；否则 403。"""
    ok, tier, _ = await query_access(
        db, user_id=user_id, textbook_version=textbook_version,
        grade=grade, semester=semester,
    )
    if not ok:
        raise AppError(code=403, message="未购买该学期会员")
    if TIER_RANK[tier] < TIER_RANK[required_tier]:
        raise AppError(code=403, message=f"需要 {required_tier} 及以上档位")


async def create_purchased_semesters(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tier: str,
    semesters: list[dict],  # [{textbook_version, grade, semester}]
    order_id: uuid.UUID,
) -> list[PurchasedSemester]:
    """订单支付成功后调用，为每个学期创建一行 PurchasedSemester。"""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SEMESTER_DURATION_DAYS)

    # 算 semester_no（用户累计第几个学期，1 起算）
    existing = await db.execute(
        select(PurchasedSemester).where(PurchasedSemester.user_id == user_id)
    )
    base_no = len(list(existing.scalars().all()))

    created: list[PurchasedSemester] = []
    for i, s in enumerate(semesters, start=1):
        ps = PurchasedSemester(
            id=uuid.uuid4(),
            user_id=user_id,
            textbook_version=s["textbook_version"],
            grade=s["grade"],
            semester=s["semester"],  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            semester_no=base_no + i,
            started_at=now,
            expires_at=expires,
            order_id=order_id,
        )
        db.add(ps)
        created.append(ps)
    await db.flush()
    return created
```

- [ ] **Step 4: 创建 tests/api/test_m1_semesters.py（6 个测试）**

```python
"""M1 学期会员测试（D-079）。"""
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services.auth_service import upsert_user
from app.services.pricing_service import (
    get_semester_pricing, calc_total_fen, DEFAULT_PRICING,
)
from app.services.semester_service import (
    create_purchased_semesters, query_access, assert_can_access,
    SEMESTER_DURATION_DAYS,
)
from app.core.exceptions import AppError
from datetime import datetime, timezone, timedelta


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student(db_session):
    u = await upsert_user(db_session, openid=f"m1_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_pricing_from_config_or_default(db_session):
    p = await get_semester_pricing(db_session)
    # 迁移 0008 已 seed，或返回 DEFAULT
    assert p.basic in (39, DEFAULT_PRICING.basic)
    assert p.pro in (79, DEFAULT_PRICING.pro)
    assert p.promax in (159, DEFAULT_PRICING.promax)


def test_calc_total_fen():
    p = DEFAULT_PRICING
    assert calc_total_fen(p, tier="basic", semester_count=1) == 3900
    assert calc_total_fen(p, tier="pro", semester_count=2) == 79 * 2 * 100
    assert calc_total_fen(p, tier="promax", semester_count=3) == 159 * 3 * 100


@pytest.mark.asyncio
async def test_create_and_query_access(db_session, student):
    # 模拟 Order（用任意 uuid 占位，外键不强制本测试范围）
    fake_order_id = uuid.uuid4()
    # 直接插一行 order（最小字段）
    from app.models.d2_payments import Order
    db_session.add(Order(
        id=fake_order_id, order_no=f"TEST-{uuid.uuid4().hex[:8]}",
        payer_id=student.id, beneficiary_id=student.id,
        order_type="new", tier="basic", duration_months=6, amount_fen=3900,
        status="paid",
    ))
    await db_session.flush()

    ps_list = await create_purchased_semesters(
        db_session, user_id=student.id, tier="basic",
        semesters=[{"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"}],
        order_id=fake_order_id,
    )
    assert len(ps_list) == 1
    ps = ps_list[0]
    assert ps.semester_no == 1
    assert (ps.expires_at - ps.started_at).days == SEMESTER_DURATION_DAYS

    ok, tier, _ = await query_access(
        db_session, user_id=student.id,
        textbook_version="译林版", grade="小学5年级", semester="上",
    )
    assert ok is True
    assert tier == "basic"


@pytest.mark.asyncio
async def test_query_access_no_purchase(db_session, student):
    ok, tier, _ = await query_access(
        db_session, user_id=student.id,
        textbook_version="译林版", grade="小学5年级", semester="上",
    )
    assert ok is False
    assert tier is None


@pytest.mark.asyncio
async def test_assert_can_access_403_no_purchase(db_session, student):
    with pytest.raises(AppError) as exc:
        await assert_can_access(
            db_session, user_id=student.id,
            textbook_version="译林版", grade="小学5年级", semester="上",
        )
    assert exc.value.code == 403


@pytest.mark.asyncio
async def test_assert_can_access_403_tier_too_low(db_session, student):
    """basic 用户访问 pro 内容应 403。"""
    fake_order_id = uuid.uuid4()
    from app.models.d2_payments import Order
    db_session.add(Order(
        id=fake_order_id, order_no=f"TEST-{uuid.uuid4().hex[:8]}",
        payer_id=student.id, beneficiary_id=student.id,
        order_type="new", tier="basic", duration_months=6, amount_fen=3900,
        status="paid",
    ))
    await db_session.flush()
    await create_purchased_semesters(
        db_session, user_id=student.id, tier="basic",
        semesters=[{"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"}],
        order_id=fake_order_id,
    )

    with pytest.raises(AppError) as exc:
        await assert_can_access(
            db_session, user_id=student.id,
            textbook_version="译林版", grade="小学5年级", semester="上",
            required_tier="pro",
        )
    assert exc.value.code == 403
```

- [ ] **Step 5: 跑测试**

```bash
/opt/anaconda3/bin/python -m pytest ../tests/api/test_m1_semesters.py -v
/opt/anaconda3/bin/python -m pytest ../tests/ -q
```
Expected: 6 PASS；全量 229 (223+6)

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/semesters.py \
        backend/app/services/pricing_service.py \
        backend/app/services/semester_service.py \
        tests/api/test_m1_semesters.py
git commit -m "feat(v2): pricing + semester service (purchased_semesters + access check)"
```

---

## Task 3: order_service 改造 + orders.py 端点 + complete-profile 加字段 + 集成测试

**Files:**
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/services/membership_service.py` (打 deprecated 标 + 新增 activate_semesters)
- Modify: `backend/app/api/v1/orders.py`
- Modify: `backend/app/schemas/payments.py`
- Modify: `backend/app/api/v1/webhooks.py` (支付成功回调改走学期激活)
- Modify: `backend/app/schemas/compliance.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/v1/auth.py`
- Modify: `tests/api/test_m1_semesters.py` (追加 API 测试)

- [ ] **Step 1: payments.py 改 OrderCreate**

OrderCreate 加可选字段：
```python
    # V2 学期会员（D-079）。若提供 semesters 走学期模式；否则按旧 duration_months 兼容
    semesters: list["SemesterIdentity"] | None = Field(None, description="V2：要购买的学期列表")
```
（顶部 `from app.schemas.semesters import SemesterIdentity` 注意循环引用——若有，改用 forward ref 或定义在同一文件）

- [ ] **Step 2: order_service.create_order 改造**

加分支：
```python
async def create_order(
    db, *, payer_id, beneficiary_id, tier, duration_months=None,
    order_type, semesters: list[dict] | None = None,
):
    """V1（duration_months）和 V2（semesters）双模式共存。
    semesters 非空 → V2 计价；否则 V1 旧逻辑。
    """
    from app.services.pricing_service import get_semester_pricing, calc_total_fen
    if semesters:
        pricing = await get_semester_pricing(db)
        semester_count = len(semesters)
        amount_fen = calc_total_fen(pricing, tier=tier, semester_count=semester_count)
        order = Order(
            id=uuid.uuid4(),
            order_no=f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
            payer_id=payer_id, beneficiary_id=beneficiary_id,
            order_type=order_type, tier=tier,
            duration_months=0,  # V2 不用，0 占位
            amount_fen=amount_fen,
            status="pending",
            semester_count=semester_count,
            purchased_semester_ids=semesters,  # 存原始入参 JSON，支付成功后据此创建 PurchasedSemester
        )
    else:
        # V1 兼容
        # ...（保留原代码）
    db.add(order)
    await db.flush()
    return order
```

- [ ] **Step 3: membership_service.activate_membership 加分支**

```python
async def activate_membership(db, *, order: Order):
    """支付成功回调：V2 走学期激活；V1 走旧 membership。"""
    if order.semester_count and order.purchased_semester_ids:
        from app.services.semester_service import create_purchased_semesters
        await create_purchased_semesters(
            db, user_id=order.beneficiary_id, tier=str(order.tier),
            semesters=order.purchased_semester_ids,
            order_id=order.id,
        )
        # 发通知
        from app.services.notification_service import emit_membership
        try:
            await emit_membership(
                db, user_id=order.beneficiary_id,
                title="学期会员开通成功",
                content=f"已开通 {order.semester_count} 个学期，6 个月有效。",
                order_id=order.id,
            )
        except Exception:
            pass
        return None  # V2 不返回 Membership 对象
    # V1 旧逻辑
    # ...保留原代码
```

- [ ] **Step 4: orders.py 端点不变（OrderCreate 多字段自动透传）**

确认 endpoint 把 `body.semesters` 转 list[dict] 传给 service。

- [ ] **Step 5: complete-profile 加字段**

`schemas/compliance.py` 的 `CompleteProfileRequest` 加：
```python
    preferred_textbook_version: str | None = Field(None, description="V2: 教材版本")
    preferred_grade: str | None = Field(None, description="V2: 年级")
    preferred_semester: Literal["上", "下"] | None = Field(None, description="V2: 学期上/下")
```

`auth_service.complete_profile` 写入这三个字段。

`api/v1/auth.py` 的 `complete_profile_api` endpoint 把字段传下去。

- [ ] **Step 6: 追加 API 测试**

```python


# ── API 测试 ──────────────────────────────────────────────────────────────────
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, suffix):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"m1_api_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_complete_profile_with_textbook_preference(client):
    h = await _login(client, f"pref_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/auth/complete-profile",
        json={
            "birth_year": 1990, "agreement_version": "v1.0",
            "preferred_textbook_version": "译林版",
            "preferred_grade": "小学5年级",
            "preferred_semester": "上",
        }, headers=h,
    )
    assert r.status_code == 200
    # 验证字段写入数据库
    from app.core.database import _async_session_factory
    from sqlalchemy import select
    from app.models.d1_users import User
    async with _async_session_factory() as s:
        user = (await s.execute(select(User).where(User.openid.like("m1_api_pref_%")).order_by(User.created_at.desc()).limit(1))).scalar_one()
        assert user.preferred_textbook_version == "译林版"
        assert user.preferred_grade == "小学5年级"
        assert str(user.preferred_semester) == "上"


@pytest.mark.asyncio
async def test_v2_order_creation_calculates_correct_amount(client):
    """V2 下单（指定 semesters）金额 = tier×单价×数量"""
    h = await _login(client, f"order_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=h,
    )
    r = await client.post(
        "/api/v1/orders/",
        json={
            "tier": "pro",
            "order_type": "new",
            "semesters": [
                {"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"},
                {"textbook_version": "译林版", "grade": "小学5年级", "semester": "下"},
            ],
        }, headers=h,
    )
    assert r.status_code == 200
    # 79 * 2 学期 * 100 分 = 15800
    assert r.json()["data"]["amount_fen"] == 15800
```

- [ ] **Step 7: 跑测试**

```bash
/opt/anaconda3/bin/python -m pytest ../tests/api/test_m1_semesters.py -v
/opt/anaconda3/bin/python -m pytest ../tests/ -q
```
Expected: 8 PASS（6+2）；全量 231（223+8）

- [ ] **Step 8: 提交**

```bash
git add backend/app/services/order_service.py backend/app/services/membership_service.py \
        backend/app/api/v1/orders.py backend/app/api/v1/auth.py \
        backend/app/schemas/payments.py backend/app/schemas/compliance.py \
        backend/app/services/auth_service.py \
        tests/api/test_m1_semesters.py
git commit -m "feat(v2): order_service V2 semester calc + complete-profile textbook preference"
```

---

## Task 4: 前端 onboarding 加教材偏好 + profile 旧购买区改占位

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/pages/auth/complete-profile.vue`
- Modify: `frontend/miniprogram/src/pages/profile/index.vue`

- [ ] **Step 1: types/api.ts 加 SemesterIdentity 类型**

```typescript
export type Semester = '上' | '下'
export interface SemesterIdentity {
  textbook_version: string
  grade: string
  semester: Semester
}
```

`CompleteProfileRequest` 类型扩展（如已声明）加 preferred_* 字段。

- [ ] **Step 2: complete-profile.vue 加教材选择 picker**

加 3 个 picker（教材版本 / 年级 / 学期）：
```vue
      <view class="row col">
        <text class="label">教材版本</text>
        <picker :range="textbookOptions" @change="(e) => textbook = textbookOptions[e.detail.value]">
          <view class="picker-val">{{ textbook || '请选择' }}</view>
        </picker>
      </view>
      <view class="row col">
        <text class="label">年级</text>
        <picker :range="gradeOptions" @change="(e) => grade = gradeOptions[e.detail.value]">
          <view class="picker-val">{{ grade || '请选择' }}</view>
        </picker>
      </view>
      <view class="row col">
        <text class="label">学期</text>
        <picker :range="['上', '下']" @change="(e) => semester = (['上','下'][e.detail.value])">
          <view class="picker-val">{{ semester || '请选择' }}</view>
        </picker>
      </view>
```

script 加：
```typescript
const textbookOptions = ['译林版', '人教PEP', '外研版']  // M1 提供这 3 个
const gradeOptions = ['小学5年级', '小学6年级', '初中7年级', '初中8年级', '初中9年级']
const textbook = ref('')
const grade = ref('')
const semester = ref<'上' | '下' | ''>('')
```

提交时把这 3 个字段一起传：
```typescript
await completeProfile({
  birth_year: ..., guardian_phone: ..., user_phone: ..., agreement_version: 'v1.0',
  preferred_textbook_version: textbook.value || undefined,
  preferred_grade: grade.value || undefined,
  preferred_semester: semester.value || undefined,
})
```

`canSubmit` 加 `&& textbook.value && grade.value && semester.value`（强制 V2 onboarding 填 3 项）。

`picker-val` 样式：
```css
.picker-val { padding: 16rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 28rpx; color: var(--c-text-body); }
```

- [ ] **Step 3: profile/index.vue 旧购买区改占位**

把整个"会员状态 + 升级"卡片改为：
```vue
    <view class="card">
      <view class="card-title">学期会员（V2）</view>
      <text class="menu-desc">按学期购买课程内容（基础 ¥39 / Pro ¥79 / ProMax ¥159 / 学期）。完整购买流程将在 M3 学期详情页推出。</text>
      <view v-if="mySemesters.length" class="sem-list">
        <view v-for="s in mySemesters" :key="s.id" class="sem-item">
          <text>{{ s.textbook_version }} {{ s.grade }} {{ s.semester }} · {{ tierLabel(s.tier) }}</text>
          <text class="sem-expires">至 {{ s.expires_at.slice(0,10) }}</text>
        </view>
      </view>
      <view v-else>
        <text class="menu-desc" style="color:var(--c-text-hint)">尚未购买任何学期</text>
      </view>
    </view>
```

script 删除旧 selectedPlan/selectedDuration/onPay/memberPlans 等，加：
```typescript
import { listMySemesters } from '@/api/semesters'  // M1 创建
const mySemesters = ref<any[]>([])
onMounted(async () => {
  if (auth.isLoggedIn()) {
    try { mySemesters.value = (await listMySemesters()) || [] } catch {}
  }
})
```

- [ ] **Step 4: 创建 api/semesters.ts**

```typescript
import { request } from '@/utils/request'
export function listMySemesters() {
  return request('/api/v1/semesters/mine', { method: 'GET' })
}
```

后端对应端点先简单加：`GET /semesters/mine` 调用 semester_service.list_my_semesters。

> 注意：本 Task 不要求完整学期购买 UI（M3 做学期详情页），M1 只要后端能算价 + 鉴权 + 用户能看自己已购的清单。

- [ ] **Step 5: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/pages/auth/complete-profile.vue \
        frontend/miniprogram/src/pages/profile/index.vue \
        frontend/miniprogram/src/api/semesters.ts
git commit -m "feat(v2): onboarding textbook preference + profile V2 placeholder + semester list"
```

---

## Task 5: 集成验证 + 归档 D-080 + push

- [ ] **Step 1: 全量后端测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
/opt/anaconda3/bin/python -m pytest ../tests/ -q
```
Expected: ≥ 231 PASS

- [ ] **Step 2: live server 冒烟**

```bash
/opt/anaconda3/bin/uvicorn app.main:app --port 8031 --log-level warning &
UVICORN_PID=$!
sleep 3
curl -s http://localhost:8031/openapi.json | python3 -c "
import json, sys
spec = json.load(sys.stdin)
paths = sorted([p for p in spec['paths'].keys() if 'semester' in p])
print('M1 端点:')
for p in paths: print('  ', p)
"
kill $UVICORN_PID 2>/dev/null
```

- [ ] **Step 3: 归档 D-080 到 `docs/决策归档.md`（插入 D-079 之前）**

```markdown
## D-080｜V2 M1 完成：数据模型基础 + 学期会员重构

**日期：** 2026-05-30
**背景：** D-079 启动的 V2 演进第一里程碑 M1。目标是把 V2 9 张新表 + 学期会员模型落地，让后续 M2-M4 内容/题库/上传功能能有数据骨架挂载。
**结论：**
1. **迁移 0007（9 张新表）：** knowledge_point_contents / exam_papers / exam_questions / exam_question_knowledge_points / simulated_questions / user_uploaded_papers / user_paper_questions / user_paper_question_knowledge_points / purchased_semesters。复用现有 semester_enum / ai_question_type_enum / order_tier_enum 避免 enum 重复。
2. **迁移 0008（3 项扩展 + 种子）：** users 加 preferred_textbook_version/grade/semester；orders 加 semester_count/purchased_semester_ids；system_configs seed 价格 `{basic:39,pro:79,promax:159}`。
3. **新 service：** `pricing_service.get_semester_pricing` 从 system_configs 读价格（缺失走默认）+ `calc_total_fen` 按 tier×学期数算分；`semester_service.create_purchased_semesters/list_my_semesters/query_access/assert_can_access` 管已购学期 + 鉴权（access = 覆盖该 (教材,年级,学期) 且 tier ≥ required + expires_at>now）。
4. **新旧并存：** order_service.create_order 加 `semesters` 参数走 V2 计价；不传则走 V1 旧 duration_months 兼容；membership_service.activate_membership 检测 order.semester_count 走 V2 create_purchased_semesters，否则 V1 旧 Membership 激活。旧 wrong_questions/memberships 表只读保留。
5. **complete-profile 加教材偏好：** 注册完善资料强制选 textbook/grade/semester（M1 提供译林版/人教PEP/外研版 3 选项 + 5 个年级）。
6. **前端最简过渡：** profile 页旧"档位×月数"购买 UI 作废，改"V2 学期会员"占位卡 + 已购学期列表（完整购买流程 M3 学期详情页做）。
7. **测试：** 8 个新测试（6 service + 2 API），全量 231 PASS。
**未做（明确归 M2-M5）：** 教材内容种子（M2）；仿真题预生成（M3）；学期详情页 + 完整购买 UI（M3）；整卷上传 OCR 拆题（M4）；运营 Web 后台（M5）；老师上传真题入 exam_papers（M2+）。
**影响范围：** 迁移 0007+0008；2 个新 service；4 个新模型文件（d11-d14）；2 个 service 改造（order/membership）；2 个 API 端点改字段（orders/auth）+ 1 个新端点（/semesters/mine）；3 个前端文件改动；测试 +8；已推送 GitHub main 分支。

---
```

- [ ] **Step 4: 提交 + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-080 — V2 M1 complete (data model + semester membership)"
git push
```

---

## Self-Review

### Spec 覆盖
| 评估文档 M1 要求 | 实现位置 |
|---|---|
| 迁移 0007 9 张新表 | Task 0 |
| 迁移 0008 users/orders 扩展 + 价格 seed | Task 1 |
| pricing_service（system_configs 读价）| Task 2 |
| semester_service（create/list/access）| Task 2 |
| order_service 按学期计价 | Task 3 |
| membership_service 改走 create_purchased_semesters | Task 3 |
| complete-profile 加教材偏好 | Task 3 + 前端 Task 4 |
| profile 旧购买 UI 退场（M3 后做新的）| Task 4 |
| 价格运营可配 | system_configs seed + pricing_service 读 |

### 类型一致性
- `SemesterIdentity` 在 schema/service/前端 statement 一致使用 (textbook_version, grade, semester)
- `tier` 复用 `order_tier_enum`（basic/pro/promax/free），不新建
- `semester` 复用 `semester_enum`（上/下），不新建

### 未做明确归档
- M2-M5 范围在 D-080 第 7 条明列
- 真实 SMS / 运营 UI / 多教材种子全部归 M2+
