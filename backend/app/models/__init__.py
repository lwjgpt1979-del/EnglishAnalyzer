"""
统一导入所有 SQLAlchemy 模型，确保 Base.metadata 中注册全部 47 张表。
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

# 域3: 错题与 AI 诊断 (4 张表)
from .d3_wrong_questions import WrongQuestion, OcrTask, AiAnalysis, TeacherComment  # noqa: F401

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

# 域11: V2 教材深度内容 (1 张表)
from .d11_v2_curriculum import KnowledgePointContent  # noqa: F401

# 域12: V2 真题与仿真题 (4 张表)
from .d12_v2_exams import (  # noqa: F401
    ExamPaper, ExamQuestion, ExamQuestionKnowledgePoint, SimulatedQuestion,
    SimPracticeRecord,
)

# 域13: V2 学生整卷上传 (3 张表)
from .d13_v2_user_papers import (  # noqa: F401
    UserUploadedPaper, UserPaperQuestion, UserPaperQuestionKnowledgePoint,
)

# 域14: V2 学期会员 (1 张表)
from .d14_v2_semesters import PurchasedSemester  # noqa: F401

__all__ = ["Base"]
