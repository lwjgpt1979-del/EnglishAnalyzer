import { request } from '@/utils/request'
import type {
  TeacherProfileOut,
  InviteCodeOut,
  TeacherStudentOut,
  TeacherCommentOut,
  WrongQuestionOut,
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
