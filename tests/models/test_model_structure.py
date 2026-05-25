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
