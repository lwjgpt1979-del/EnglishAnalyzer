"""
统一导入所有 SQLAlchemy 模型，确保 Base.metadata 中注册全部 47 张表。
Alembic env.py 中 `import app.models` 即可获取完整元数据。
"""

from .base import Base  # noqa: F401

# 域1: 用户与租户 (8 张表)
from .d1_users import (  # noqa: F401
    User,
    BanAppeal,
    Institution,
    Student,
    Teacher,
    Relative,
    StudentRelative,
    TeacherStudent,
    InviteCode,
)

# 域2: 会员与支付 (3 张表)
from .d2_payments import (  # noqa: F401
    Order, Membership, RefundRecord, InstitutionPurchase, ActivationCode,
    PaymentConfirmLog, InvoiceRequest,
)

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
    ListeningWrongQuestion,
    ListeningShadowWeak,
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
from .d9_system import SystemConfig, Notification, UserActivity, ContentFeedback  # noqa: F401

# 域10: 分公司扩展 (3 张表)
from .d10_branch import (  # noqa: F401
    BranchCompany, BranchCompanyCity, BranchSettlement, PaymentAccount,
)

# 域11: V2 教材深度内容 (1 张表)
from .d11_v2_curriculum import KnowledgePointContent, PendingKpContent, CurriculumGenJob  # noqa: F401

# 域12: V2 真题与仿真题 (4 张表)
from .d12_v2_exams import (  # noqa: F401
    ExamPaper, ExamQuestion, ExamQuestionKnowledgePoint, SimulatedQuestion,
    SimPracticeRecord, SimExamSession,
)

# 域13: V2 学生整卷上传 (3 张表)
from .d13_v2_user_papers import (  # noqa: F401
    UserUploadedPaper, UserPaperQuestion, UserPaperQuestionKnowledgePoint,
)

# 域14: V2 学期会员 (1 张表)
from .d14_v2_semesters import PurchasedSemester  # noqa: F401

# 域15: 知识图谱骨架 (KP-First 重构 R0, 4 张表)
from .d15_knowledge_graph import (  # noqa: F401
    KnowledgeNode, NodeAlias, NodeRelation, KpCandidate,
)

# 域16: 题分域 + 个人窄表骨架 (KP-First 重构 R0.5, 8 张表)
from .d16_question_domain import (  # noqa: F401
    PlatformQuestion, PlatformPaper, UploadedQuestion, Passage,
    PlatformQuestionKp, UploadedQuestionKp,
    StudentKp, AnswerLog, WrongRecord, RealExtractJob,
)

# 域17: 教材接入 KP-First (R1, 1 张表)
from .d17_curriculum_kg import UnitNode  # noqa: F401

# 域18: 词汇接入 KP-First (R5, 5 张表)
from .d18_vocab_kg import (  # noqa: F401
    VocabNode, VocabQuestion, VocabWrong, VocabList, VocabListItem,
)

# 域19: 知识节点资源 KP-First (R6, 1 张表)
from .d19_node_resource import NodeResource  # noqa: F401

# 域20: 长难句解析 KP-First (2 张表)
from .d20_long_sentence import LongSentence, LongSentenceNode  # noqa: F401

# 域21: 行政区划地区表(唯一数据源)
from .d21_region import Region  # noqa: F401

# 域22: 单元结构化解析(语法点+分级句 / 听力考点+句组 / 作文要求+正文)
from .d22_unit_structured import UnitSection, UnitSectionSentence  # noqa: F401

# 域23: 电销 CRM(线索池 + 跟进记录 + 企微会话存档;平台自用,预留机构维度)
from .d23_sales_crm import SalesLead, SalesLeadActivity, WecomChatArchive  # noqa: F401

__all__ = ["Base"]
