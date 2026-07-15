from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.diagnosis import router as diagnosis_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.orders import router as orders_router
from app.api.v1.invoices import router as invoices_router
from app.api.v1.upload import router as upload_router
from app.api.v1.users import router as users_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.practice import router as practice_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.wrong_questions import router as wrong_questions_router
from app.api.v1.wrong_center import router as wrong_center_router
from app.api.v1.student_graph import router as student_graph_router
from app.api.v1.long_sentence import router as long_sentence_router
from app.api.v1.checkin import router as checkin_router
from app.api.v1.regions import router as regions_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.relative import router as relative_router
from app.api.v1.semesters import router as semesters_router
from app.api.v1.curriculum import router as curriculum_router
from app.api.v1.questions import router as questions_router
from app.api.v1.user_papers import router as user_papers_router
from app.api.v1.vocabulary import router as vocabulary_router
from app.api.v1.essay import router as essay_router
from app.api.v1.reading_expression import router as reading_expression_router
from app.api.v1.writing_practice import router as writing_practice_router
from app.api.v1.admin_analysis import router as admin_analysis_router
from app.api.v1.admin_curriculum import router as admin_curriculum_router
from app.api.v1.admin_kp_lecture import router as admin_kp_lecture_router
from app.api.v1.admin_approval import router as admin_approval_router
from app.api.v1.assignments import router as assignments_router
from app.api.v1.institution import router as institution_router
from app.api.v1.student_papers import router as student_papers_router
from app.api.v1.kp_mastery import router as kp_mastery_router
from app.api.v1.learning_plan import router as learning_plan_router
from app.api.v1.incentive import router as incentive_router
from app.api.v1.config import router as config_router
from app.api.v1.tts import router as tts_router
from app.api.v1.listening import router as listening_router
from app.api.v1.self_exam import router as self_exam_router
from app.api.v1.speaking import router as speaking_router
from app.api.v1.entitlements import router as entitlements_router
from app.api.v1.entitlements import admin_router as entitlements_admin_router
from app.api.v1.support import router as support_router
from app.api.v1.coupons import router as coupons_router
from app.api.v1.grammar import router as grammar_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(wrong_questions_router)
v1_router.include_router(wrong_center_router)
v1_router.include_router(student_graph_router)
v1_router.include_router(long_sentence_router)
v1_router.include_router(grammar_router)
v1_router.include_router(checkin_router)
v1_router.include_router(regions_router)
v1_router.include_router(memberships_router)
v1_router.include_router(orders_router)
v1_router.include_router(invoices_router)
v1_router.include_router(webhooks_router)
v1_router.include_router(diagnosis_router)
v1_router.include_router(upload_router)
v1_router.include_router(teacher_router)
v1_router.include_router(practice_router)
v1_router.include_router(notifications_router)
v1_router.include_router(relative_router)
v1_router.include_router(semesters_router)
v1_router.include_router(curriculum_router)
v1_router.include_router(questions_router)
v1_router.include_router(user_papers_router)
v1_router.include_router(vocabulary_router)
v1_router.include_router(essay_router)
v1_router.include_router(reading_expression_router)
v1_router.include_router(writing_practice_router)
v1_router.include_router(admin_analysis_router)
v1_router.include_router(admin_curriculum_router)
v1_router.include_router(admin_kp_lecture_router)
v1_router.include_router(admin_approval_router)
v1_router.include_router(assignments_router)
v1_router.include_router(institution_router)
v1_router.include_router(student_papers_router)
v1_router.include_router(kp_mastery_router)
v1_router.include_router(learning_plan_router)
v1_router.include_router(incentive_router)
v1_router.include_router(config_router)
v1_router.include_router(tts_router)
v1_router.include_router(listening_router)
v1_router.include_router(self_exam_router)
v1_router.include_router(speaking_router)
v1_router.include_router(admin_router)
v1_router.include_router(entitlements_router)
v1_router.include_router(entitlements_admin_router)
v1_router.include_router(support_router)
v1_router.include_router(coupons_router)
