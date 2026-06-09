import { request } from '@/utils/request'
import type {
  AssignmentOut, AssignmentListItem, TeacherAssignmentDetail,
  StudentAssignmentItem, StudentAssignmentDetail, AssignmentQuestion,
} from '@/types/api'

// 老师端
export function createAssignment(payload: { class_id: string; title: string; questions: AssignmentQuestion[]; due_at?: string }): Promise<AssignmentOut> {
  return request<AssignmentOut>('/api/v1/teacher/assignments', { method: 'POST', data: payload })
}
export function listAssignments(classId?: string): Promise<AssignmentListItem[]> {
  const data: Record<string, string> = {}
  if (classId) data.class_id = classId
  return request<AssignmentListItem[]>('/api/v1/teacher/assignments', { method: 'GET', data })
}
export function getAssignmentDetail(id: string): Promise<TeacherAssignmentDetail> {
  return request<TeacherAssignmentDetail>(`/api/v1/teacher/assignments/${id}`, { method: 'GET' })
}
export function publishAssignment(id: string): Promise<AssignmentOut> {
  return request<AssignmentOut>(`/api/v1/teacher/assignments/${id}/publish`, { method: 'POST' })
}
export function closeAssignment(id: string): Promise<AssignmentOut> {
  return request<AssignmentOut>(`/api/v1/teacher/assignments/${id}/close`, { method: 'POST' })
}
export function gradeSubmission(submissionId: string, score: number): Promise<{ id: string; score: number }> {
  return request(`/api/v1/teacher/submissions/${submissionId}/grade`, { method: 'POST', data: { score } })
}

// 学生端
export function getReceivedAssignments(): Promise<StudentAssignmentItem[]> {
  return request<StudentAssignmentItem[]>('/api/v1/assignments', { method: 'GET' })
}
export function getStudentAssignment(id: string): Promise<StudentAssignmentDetail> {
  return request<StudentAssignmentDetail>(`/api/v1/assignments/${id}`, { method: 'GET' })
}
export function submitAssignment(id: string, answers: unknown): Promise<{ id: string; submitted_at: string }> {
  return request(`/api/v1/assignments/${id}/submit`, { method: 'POST', data: { answers } })
}

export function getAssignmentStats(id: string): Promise<import('@/types/api').AssignmentStats> {
  return request(`/api/v1/teacher/assignments/${id}/stats`, { method: 'GET' })
}

export function suggestAssignmentQuestions(studentId: string, count = 5): Promise<import('@/types/api').AssignmentSuggest> {
  return request('/api/v1/teacher/assignments/suggest', { method: 'GET', data: { student_id: studentId, count } })
}

/** M47 — 按指定 KP 直接生成出题建议（班级弱项推荐专用）*/
export function suggestByKp(kpKey: string, count = 5): Promise<import('@/types/api').AssignmentSuggest> {
  return request('/api/v1/teacher/assignments/suggest-by-kp', {
    method: 'GET',
    data: { kp_key: kpKey, count },
  })
}
