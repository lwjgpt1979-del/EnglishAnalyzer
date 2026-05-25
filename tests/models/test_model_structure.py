"""
Model structure tests — no live database required.
Tests run by importing models and inspecting SQLAlchemy Table objects.
"""

def test_sqlalchemy_importable():
    import sqlalchemy as sa
    assert sa.__version__.startswith("2.")


def test_alembic_importable():
    import alembic
    assert alembic.__version__ >= "1.13"


def test_base_importable():
    from app.models.base import Base
    import sqlalchemy as sa
    # Base.metadata is a SQLAlchemy MetaData object
    assert isinstance(Base.metadata, sa.MetaData)


def test_database_engine_config():
    from app.core.database import get_engine_url
    # reads DATABASE_URL env var (returns None if not set, never crashes)
    url = get_engine_url()
    assert url is None or url.startswith("postgresql")


def test_d1_users_tables():
    from app.models.d1_users import (
        User, Institution, Student, Teacher,
        Relative, StudentRelative, TeacherStudent, InviteCode,
    )
    assert User.__tablename__ == "users"
    assert Institution.__tablename__ == "institutions"
    assert Student.__tablename__ == "students"
    assert Teacher.__tablename__ == "teachers"
    assert Relative.__tablename__ == "relatives"
    assert StudentRelative.__tablename__ == "student_relatives"
    assert TeacherStudent.__tablename__ == "teacher_students"
    assert InviteCode.__tablename__ == "invite_codes"


def test_user_columns():
    from app.models.d1_users import User
    cols = {c.name for c in User.__table__.columns}
    required = {
        "id", "openid", "phone", "nickname", "avatar_url",
        "role", "is_active", "city_code", "city_source",
        "ip_at_registration", "created_at", "updated_at",
    }
    assert required <= cols, f"缺失字段: {required - cols}"


def test_teacher_student_status_has_inactive():
    """G17: teacher_students.status 必须包含 inactive。"""
    from app.models.d1_users import TeacherStudent
    status_col = TeacherStudent.__table__.c["status"]
    enum_values = set(status_col.type.enums)
    assert "inactive" in enum_values, "G17 修复未应用: 缺少 inactive"


def test_teacher_students_partial_unique_index():
    from app.models.d1_users import TeacherStudent
    indexes = TeacherStudent.__table__.indexes
    partial = [i for i in indexes if i.unique and "active" in str(getattr(i, "dialect_kwargs", {}).get("postgresql_where", ""))]
    assert len(partial) == 1, "缺少 UNIQUE WHERE status='active' 部分唯一索引"


def test_d2_payment_tables():
    from app.models.d2_payments import Membership, Order, RefundRecord
    assert Membership.__tablename__ == "memberships"
    assert Order.__tablename__ == "orders"
    assert RefundRecord.__tablename__ == "refund_records"


def test_membership_has_order_id():
    """G19: memberships 必须有 order_id 字段。"""
    from app.models.d2_payments import Membership
    cols = {c.name for c in Membership.__table__.columns}
    assert "order_id" in cols, "G19 修复未应用: memberships 缺少 order_id"


def test_memberships_partial_unique_index():
    from app.models.d2_payments import Membership
    indexes = Membership.__table__.indexes
    partial = [
        i for i in indexes
        if i.unique and "is_active" in str(getattr(i, "dialect_kwargs", {}).get("postgresql_where", ""))
    ]
    assert len(partial) == 1, "缺少 UNIQUE WHERE is_active=true 部分唯一索引"


def test_refund_record_has_reviewed_by():
    """G22: refund_records 必须有 reviewed_by 字段。"""
    from app.models.d2_payments import RefundRecord
    cols = {c.name for c in RefundRecord.__table__.columns}
    assert "reviewed_by" in cols, "G22 修复未应用: refund_records 缺少 reviewed_by"


def test_d3_wrong_question_tables():
    from app.models.d3_wrong_questions import (
        WrongQuestion, OcrTask, AiAnalysis,
    )
    assert WrongQuestion.__tablename__ == "wrong_questions"
    assert OcrTask.__tablename__ == "ocr_tasks"
    assert AiAnalysis.__tablename__ == "ai_analyses"


def test_wrong_question_columns():
    from app.models.d3_wrong_questions import WrongQuestion
    cols = {c.name for c in WrongQuestion.__table__.columns}
    required = {
        "id", "student_id", "institution_id", "source_image_url",
        "question_text", "student_answer", "correct_answer",
        "question_type", "difficulty", "tags", "is_mastered",
        "mastered_at", "updated_at", "created_at",
    }
    assert required <= cols, f"缺失: {required - cols}"


def test_d4_knowledge_tables():
    from app.models.d4_knowledge import (
        KnowledgePoint, CurriculumUnit, UnitKnowledgePoint,
        CurriculumWord, WrongQuestionKnowledgePoint,
    )
    assert KnowledgePoint.__tablename__ == "knowledge_points"
    assert CurriculumUnit.__tablename__ == "curriculum_units"
    assert UnitKnowledgePoint.__tablename__ == "unit_knowledge_points"
    assert CurriculumWord.__tablename__ == "curriculum_words"
    assert WrongQuestionKnowledgePoint.__tablename__ == "wrong_question_knowledge_points"


def test_knowledge_point_self_fk():
    from app.models.d4_knowledge import KnowledgePoint
    cols = {c.name for c in KnowledgePoint.__table__.columns}
    assert "parent_id" in cols, "knowledge_points 缺少 parent_id 自引用 FK"
    assert "applicable_grades" in cols
    assert "applicable_textbooks" in cols


def test_curriculum_unit_unique_constraint():
    from app.models.d4_knowledge import CurriculumUnit
    unique_constraints = [
        c for c in CurriculumUnit.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) > 1
    ]
    assert len(unique_constraints) >= 1, "curriculum_units 缺少复合唯一约束"


def test_d5_learning_tables():
    from app.models.d5_learning import (
        VocabularyWord, VocabularyLearning, Essay,
        ListeningRecord, StudyCheckin,
    )
    assert VocabularyWord.__tablename__ == "vocabulary_words"
    assert VocabularyLearning.__tablename__ == "vocabulary_learning"
    assert Essay.__tablename__ == "essays"
    assert ListeningRecord.__tablename__ == "listening_records"
    assert StudyCheckin.__tablename__ == "study_checkins"


def test_vocabulary_learning_has_created_at():
    """G14: vocabulary_learning 必须有 created_at 字段。"""
    from app.models.d5_learning import VocabularyLearning
    cols = {c.name for c in VocabularyLearning.__table__.columns}
    assert "created_at" in cols, "G14 修复未应用: vocabulary_learning 缺少 created_at"


def test_vocabulary_learning_unique_constraint():
    from app.models.d5_learning import VocabularyLearning
    unique_constraints = [
        c for c in VocabularyLearning.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    assert len(unique_constraints) >= 1, "vocabulary_learning 缺少 (student_id, word_id) 唯一约束"


def test_study_checkin_unique_constraint():
    from app.models.d5_learning import StudyCheckin
    unique_constraints = [
        c for c in StudyCheckin.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    assert len(unique_constraints) >= 1, "study_checkins 缺少 (student_id, checkin_date) 唯一约束"
