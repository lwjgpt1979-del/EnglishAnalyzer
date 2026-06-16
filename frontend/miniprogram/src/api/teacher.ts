import { request } from '@/utils/request'
import type {
  TeacherProfileOut,
  InviteCodeOut,
  TeacherStudentOut,
  TeacherCommentOut,
  WrongQuestionOut,
  MyTeacherOut,
} from '@/types/api'

export function becomeTeacher(subject?: string): Promise<TeacherProfileOut> {
  return request<TeacherProfileOut>('/api/v1/teacher/profile', {
    method: 'POST',
    data: { subject: subject || null },
  })
}

export function createInviteCode(): Promise<InviteCodeOut> {
  return request<InviteCodeOut>('/api/v1/teacher/invite-code', { method: 'POST' })
}

export function bindTeacher(code: string): Promise<TeacherStudentOut> {
  return request<TeacherStudentOut>('/api/v1/teacher/bind', {
    method: 'POST',
    data: { code },
  })
}

export function getMyStudents(): Promise<TeacherStudentOut[]> {
  return request<TeacherStudentOut[]>('/api/v1/teacher/students')
}

export function getStudentWrongQuestions(studentId: string): Promise<WrongQuestionOut[]> {
  return request<WrongQuestionOut[]>(`/api/v1/teacher/students/${studentId}/wrong-questions`)
}

export function addComment(wqId: string, commentText: string): Promise<TeacherCommentOut> {
  return request<TeacherCommentOut>(`/api/v1/teacher/wrong-questions/${wqId}/comments`, {
    method: 'POST',
    data: { comment_text: commentText },
  })
}

export function getComments(wqId: string): Promise<TeacherCommentOut[]> {
  return request<TeacherCommentOut[]>(`/api/v1/teacher/wrong-questions/${wqId}/comments`)
}

export function submitCert(certDocUrl: string) {
  return request('/api/v1/teacher/cert/submit', { method: 'POST', data: { cert_doc_url: certDocUrl } })
}

export function getStudentDiagnosis(studentId: string) {
  return request(`/api/v1/teacher/students/${studentId}/diagnosis-report`, { method: 'GET' })
}

export interface SpeakStats {
  total_sessions: number; week_sessions: number; avg_score: number
  last_score: number; speaking_streak: number; last_practiced_at: string | null
}
export interface StudentVocabOverview {
  mastered: number; review: number; learning: number; new_learned: number
  learned_total: number; wrong_total: number; due_total: number; remaining_new: number
  current_streak: number; longest_streak: number
  pron: { count: number; avg: number | null; trend: 'up' | 'flat' | 'down'; weak_words: string[] } | null
}
export function getStudentVocabOverview(studentId: string): Promise<StudentVocabOverview> {
  return request<StudentVocabOverview>(`/api/v1/teacher/students/${studentId}/vocab-overview`, { method: 'GET' })
}

export function getStudentSpeakingStats(studentId: string): Promise<SpeakStats> {
  return request<SpeakStats>(`/api/v1/teacher/students/${studentId}/speaking-stats`, { method: 'GET' })
}

// ── M44 KP 接口 ────────────────────────────────────────────────────────────

export interface TeacherKpMasteryItem {
  kp_key: string
  kp_id: string | null
  kp_description: string | null
  correct_count: number
  wrong_count: number
  total: number
  accuracy: number
  level: 'weak' | 'medium' | 'good'
  suggestion: string
  sources: string[]
  last_activity_at: string | null
  days_since_last: number | null
}

export interface ClassKpWeakItem {
  kp_key: string
  avg_accuracy: number
  student_count: number
  weak_count: number
  mastered_count: number
}

export interface ClassStudentAttention {
  student_id: string
  nickname: string | null
  avg_accuracy: number
  weak_kp_count: number
  total_kp_count: number
}

export interface ClassKpStats {
  class_id: string
  class_name: string
  student_count: number
  top_weak_kps: ClassKpWeakItem[]
  students_attention: ClassStudentAttention[]
}

/** 教师查看绑定学生的知识点台账（M44） */
export function getStudentKpMastery(studentId: string): Promise<TeacherKpMasteryItem[]> {
  return request<TeacherKpMasteryItem[]>(`/api/v1/teacher/students/${studentId}/kp-mastery`)
}

/** 班级 KP 薄弱统计（M44） */
export function getClassKpStats(classId: string): Promise<ClassKpStats> {
  return request<ClassKpStats>(`/api/v1/teacher/classes/${classId}/kp-stats`)
}

export interface ClassVocabStudent {
  student_id: string; nickname: string
  learned: number; mastered: number; wrong: number; pron_avg: number | null
}
export interface ClassVocabStats {
  student_count: number
  total_learned: number; total_mastered: number
  avg_learned: number; avg_mastered: number
  wrong_total: number; active_count: number
  pron: { tested_students: number; avg: number | null } | null
  class_weak_words: string[]
  students: ClassVocabStudent[]
}
/** 班级词力通统计 */
export function getClassVocabStats(classId: string): Promise<ClassVocabStats> {
  return request<ClassVocabStats>(`/api/v1/teacher/classes/${classId}/vocab-stats`)
}

export function teacherInviteQrcode() {
  return request('/api/v1/teacher/invite-code/qrcode', { method: 'POST' })
}

export function teacherInviteSms(phone: string) {
  return request('/api/v1/teacher/invite-code/sms', { method: 'POST', data: { phone } })
}

/** 老师输码加入机构（D-121） */
export function joinInstitution(code: string) {
  return request('/api/v1/teacher/join-institution', { method: 'POST', data: { code } })
}

/** 教师移除学生（V2 M18） */
export function removeStudent(studentId: string): Promise<{ removed: boolean }> {
  return request<{ removed: boolean }>(`/api/v1/teacher/students/${studentId}`, { method: 'DELETE' })
}

/** 学生查看已绑定老师列表（V2 M19） */
export function getMyTeachers(): Promise<MyTeacherOut[]> {
  return request<MyTeacherOut[]>('/api/v1/teacher/my-teachers')
}

// 老师月度额度自查（§5.6）
export interface QuotaBlock { used: number; limit: number; remaining: number; remaining_pct: number }
export interface TeacherQuota {
  warn_threshold_pct: number; reset_day: number
  students: QuotaBlock; paper: QuotaBlock; grading: QuotaBlock
}
export function getMyQuota(): Promise<TeacherQuota> {
  return request<TeacherQuota>('/api/v1/teacher/quota', { method: 'GET' })
}
