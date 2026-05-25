"""
统一导入所有 SQLAlchemy 模型，确保 Base.metadata 中注册全部 37 张表。
Alembic env.py 中 `import app.models` 即可获取完整元数据。
"""

from .base import Base  # noqa: F401

# 域1: 用户与租户 (8 张表)
from .d1_users import (  # noqa: F401
    User,
    Institution,
    Student,
    Teacher,
    Relative,
    StudentRelative,
    TeacherStudent,
    InviteCode,
)

# 域2: 会员与支付 (3 张表)
from .d2_payments import Order, Membership, RefundRecord  # noqa: F401

# 域3: 错题与 AI 诊断 (3 张表)
from .d3_wrong_questions import WrongQuestion, OcrTask, AiAnalysis  # noqa: F401

# 域4: 知识体系 (5 张表)
from .d4_knowledge import (  # noqa: F401
    KnowledgePoint,
    CurriculumUnit,
    UnitKnowledgePoint,
    CurriculumWord,
    WrongQuestionKnowledgePoint,
)

# 域5: 学习功能 (5 张表)
from .d5_learning import (  # noqa: F401
    VocabularyWord,
    VocabularyLearning,
    Essay,
    ListeningRecord,
    StudyCheckin,
)

# 域6: AI 题库与练习 (2 张表)
from .d6_ai_questions import AiQuestion, PracticeRecord  # noqa: F401

# 域7: 老师端 (4 张表)
from .d7_teacher import (  # noqa: F401
    Class,
    ClassStudent,
    Assignment,
    AssignmentSubmission,
)

# 域8: 用量与报告 (2 张表)
from .d8_usage import DailyUsage, LearningReportSnapshot  # noqa: F401

# 域9: 系统配置与通知 (2 张表)
from .d9_system import SystemConfig, Notification  # noqa: F401

# 域10: 分公司扩展 (3 张表)
from .d10_branch import BranchCompany, BranchCompanyCity, BranchSettlement  # noqa: F401

__all__ = ["Base"]
