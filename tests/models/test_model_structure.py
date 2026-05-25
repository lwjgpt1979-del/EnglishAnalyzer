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


def test_d6_ai_question_tables():
    from app.models.d6_ai_questions import AiQuestion, PracticeRecord
    assert AiQuestion.__tablename__ == "ai_questions"
    assert PracticeRecord.__tablename__ == "practice_records"


def test_ai_question_has_updated_at():
    """G20: ai_questions 必须有 updated_at 字段。"""
    from app.models.d6_ai_questions import AiQuestion
    cols = {c.name for c in AiQuestion.__table__.columns}
    assert "updated_at" in cols, "G20 修复未应用: ai_questions 缺少 updated_at"


def test_d7_teacher_tables():
    from app.models.d7_teacher import (
        Class, ClassStudent, Assignment, AssignmentSubmission,
    )
    assert Class.__tablename__ == "classes"
    assert ClassStudent.__tablename__ == "class_students"
    assert Assignment.__tablename__ == "assignments"
    assert AssignmentSubmission.__tablename__ == "assignment_submissions"


def test_assignment_has_published_at():
    """G21: assignments 必须有 published_at 字段。"""
    from app.models.d7_teacher import Assignment
    cols = {c.name for c in Assignment.__table__.columns}
    assert "published_at" in cols, "G21 修复未应用: assignments 缺少 published_at"


def test_assignment_submission_unique_constraint():
    from app.models.d7_teacher import AssignmentSubmission
    unique_constraints = [
        c for c in AssignmentSubmission.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    assert len(unique_constraints) >= 1, "assignment_submissions 缺少复合唯一约束"


def test_d8_usage_tables():
    from app.models.d8_usage import DailyUsage, LearningReportSnapshot
    assert DailyUsage.__tablename__ == "daily_usage"
    assert LearningReportSnapshot.__tablename__ == "learning_report_snapshots"


def test_d9_system_tables():
    from app.models.d9_system import SystemConfig, Notification
    assert SystemConfig.__tablename__ == "system_configs"
    assert Notification.__tablename__ == "notifications"


def test_notification_has_read_at():
    """G15: notifications 必须有 read_at 字段。"""
    from app.models.d9_system import Notification
    cols = {c.name for c in Notification.__table__.columns}
    assert "read_at" in cols, "G15 修复未应用: notifications 缺少 read_at"


def test_d10_branch_tables():
    from app.models.d10_branch import (
        BranchCompany, BranchCompanyCity, BranchSettlement,
    )
    assert BranchCompany.__tablename__ == "branch_companies"
    assert BranchCompanyCity.__tablename__ == "branch_company_cities"
    assert BranchSettlement.__tablename__ == "branch_settlements"


def test_branch_company_city_has_created_at():
    """G16: branch_company_cities 必须有 created_at 字段。"""
    from app.models.d10_branch import BranchCompanyCity
    cols = {c.name for c in BranchCompanyCity.__table__.columns}
    assert "created_at" in cols, "G16 修复未应用: branch_company_cities 缺少 created_at"


def test_branch_settlement_has_updated_at():
    """G18: branch_settlements 必须有 updated_at 字段。"""
    from app.models.d10_branch import BranchSettlement
    cols = {c.name for c in BranchSettlement.__table__.columns}
    assert "updated_at" in cols, "G18 修复未应用: branch_settlements 缺少 updated_at"


def test_branch_company_city_partial_unique_index():
    from app.models.d10_branch import BranchCompanyCity
    indexes = BranchCompanyCity.__table__.indexes
    partial = [
        i for i in indexes
        if i.unique and "effective_to" in str(getattr(i, "dialect_kwargs", {}).get("postgresql_where", ""))
    ]
    assert len(partial) == 1, "branch_company_cities 缺少 UNIQUE WHERE effective_to IS NULL 部分索引"


def test_all_37_tables_in_metadata():
    """确保 Base.metadata 包含全部 37 张表。"""
    # 导入 __init__ 触发所有模型注册
    import app.models  # noqa: F401
    from app.models.base import Base

    expected_tables = {
        # 域1
        "users", "institutions", "students", "teachers",
        "relatives", "student_relatives", "teacher_students", "invite_codes",
        # 域2
        "memberships", "orders", "refund_records",
        # 域3
        "wrong_questions", "ocr_tasks", "ai_analyses",
        # 域4
        "knowledge_points", "curriculum_units", "unit_knowledge_points",
        "curriculum_words", "wrong_question_knowledge_points",
        # 域5
        "vocabulary_words", "vocabulary_learning", "essays",
        "listening_records", "study_checkins",
        # 域6
        "ai_questions", "practice_records",
        # 域7
        "classes", "class_students", "assignments", "assignment_submissions",
        # 域8
        "daily_usage", "learning_report_snapshots",
        # 域9
        "system_configs", "notifications",
        # 域10
        "branch_companies", "branch_company_cities", "branch_settlements",
    }
    actual_tables = set(Base.metadata.tables.keys())
    missing = expected_tables - actual_tables
    assert not missing, f"Base.metadata 缺少以下表: {sorted(missing)}"
    assert len(actual_tables) == 37, f"期望 37 张表，实际 {len(actual_tables)} 张: {sorted(actual_tables)}"


def test_migration_file_exists():
    """初始迁移文件必须存在（文件名含 initial_schema）。"""
    import os
    versions_dir = os.path.join(
        os.path.dirname(__file__), "../../backend/alembic/versions"
    )
    files = os.listdir(versions_dir)
    migration_files = [f for f in files if "initial_schema" in f and f.endswith(".py")]
    assert len(migration_files) == 1, (
        f"期望 1 个 initial_schema 迁移文件，实际找到: {migration_files}"
    )
