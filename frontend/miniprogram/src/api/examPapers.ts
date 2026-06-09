import { request } from '@/utils/request'
import type {
  BaseResponse,
  SimQuestionListOut,
  ClassPaperItem,
  ClassPaperDetailOut,
  ClassPaperCreate,
} from '@/types/api'

// ── 教师：仿真题浏览 ───────────────────────────────────────────────
export function listSimQuestions(params?: {
  kp_id?: string
  question_type?: string
  difficulty?: number
  skip?: number
  limit?: number
}): Promise<BaseResponse<SimQuestionListOut>> {
  return request('/api/v1/teacher/sim-questions', { method: 'GET', data: params })
}

// ── 教师：班级试卷 CRUD ───────────────────────────────────────────
export function createClassPaper(
  classId: string,
  body: ClassPaperCreate,
): Promise<BaseResponse<{ paper_id: string }>> {
  return request(`/api/v1/teacher/classes/${classId}/papers`, { method: 'POST', data: body })
}

export function listClassPapers(classId: string): Promise<BaseResponse<ClassPaperItem[]>> {
  return request(`/api/v1/teacher/classes/${classId}/papers`, { method: 'GET' })
}

export function getClassPaperDetail(paperId: string): Promise<BaseResponse<ClassPaperDetailOut>> {
  return request(`/api/v1/teacher/papers/${paperId}`, { method: 'GET' })
}

export function deleteClassPaper(paperId: string): Promise<BaseResponse<{ deleted: boolean }>> {
  return request(`/api/v1/teacher/papers/${paperId}`, { method: 'DELETE' })
}

// ── 学生：查看班级试卷 ────────────────────────────────────────────
export function listStudentClassPapers(classId: string): Promise<BaseResponse<ClassPaperItem[]>> {
  return request(`/api/v1/student/classes/${classId}/papers`, { method: 'GET' })
}

export function getStudentPaperDetail(paperId: string): Promise<BaseResponse<ClassPaperDetailOut>> {
  return request(`/api/v1/student/papers/${paperId}`, { method: 'GET' })
}
