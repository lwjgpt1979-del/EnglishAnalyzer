from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.diagnosis import router as diagnosis_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.orders import router as orders_router
from app.api.v1.upload import router as upload_router
from app.api.v1.users import router as users_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.practice import router as practice_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.wrong_questions import router as wrong_questions_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.relative import router as relative_router
from app.api.v1.semesters import router as semesters_router
from app.api.v1.curriculum import router as curriculum_router
from app.api.v1.questions import router as questions_router
from app.api.v1.user_papers import router as user_papers_router
from app.api.v1.vocabulary import router as vocabulary_router
from app.api.v1.essay import router as essay_router
from app.api.v1.assignments import router as assignments_router
from app.api.v1.institution import router as institution_router
from app.api.v1.student_papers import router as student_papers_router
from app.api.v1.kp_mastery import router as kp_mastery_router
from app.api.v1.learning_plan import router as learning_plan_router
from app.api.v1.incentive import router as incentive_router
from app.api.v1.config import router as config_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(wrong_questions_router)
v1_router.include_router(memberships_router)
v1_router.include_router(orders_router)
v1_router.include_router(webhooks_router)
v1_router.include_router(diagnosis_router)
v1_router.include_router(upload_router)
v1_router.include_router(ocr_router)
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
v1_router.include_router(assignments_router)
v1_router.include_router(institution_router)
v1_router.include_router(student_papers_router)
v1_router.include_router(kp_mastery_router)
v1_router.include_router(learning_plan_router)
v1_router.include_router(incentive_router)
v1_router.include_router(config_router)
v1_router.include_router(admin_router)
