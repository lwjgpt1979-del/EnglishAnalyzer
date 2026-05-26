from app.schemas.diagnosis import (
    DailyActivity,
    DiagnosisReport,
    ErrorTypeCount,
    KnowledgePointCount,
)


def test_error_type_count_schema():
    etc = ErrorTypeCount(error_type="语法错误", count=5)
    assert etc.error_type == "语法错误"
    assert etc.count == 5


def test_knowledge_point_count_schema():
    kpc = KnowledgePointCount(knowledge_point="现在完成时", count=3)
    assert kpc.knowledge_point == "现在完成时"
    assert kpc.count == 3


def test_daily_activity_schema():
    da = DailyActivity(date="2026-05-26", count=3)
    assert da.date == "2026-05-26"
    assert da.count == 3


def test_diagnosis_report_schema_empty():
    report = DiagnosisReport(
        total_questions=0,
        total_analyzed=0,
        mastered_count=0,
        mastery_rate=0.0,
        top_error_types=[],
        top_weak_knowledge_points=[],
        question_type_distribution={},
        difficulty_distribution={},
        recent_daily_activity=[],
        top_suggestions=[],
    )
    assert report.total_questions == 0
    assert report.mastery_rate == 0.0
    assert report.top_error_types == []


def test_diagnosis_report_schema_with_data():
    report = DiagnosisReport(
        total_questions=10,
        total_analyzed=8,
        mastered_count=3,
        mastery_rate=0.3,
        top_error_types=[ErrorTypeCount(error_type="语法错误", count=4)],
        top_weak_knowledge_points=[KnowledgePointCount(knowledge_point="现在完成时", count=3)],
        question_type_distribution={"单选": 5, "完型": 3, "阅读": 2},
        difficulty_distribution={3: 6, 4: 4},
        recent_daily_activity=[DailyActivity(date="2026-05-26", count=2)],
        top_suggestions=["建议多练习时态题"],
    )
    assert report.total_analyzed == 8
    assert report.mastery_rate == 0.3
    assert report.top_error_types[0].error_type == "语法错误"
