import { request } from './request'
import type {
  BaseResponse,
  TeacherProfileOut,
  InviteCodeOut,
  TeacherStudentOut,
  TeacherCommentOut,
  WrongQuestionOut,
} from '../types/api'

export function becomeTeacher(subject?: string): Promise<BaseResponse<TeacherProfileOut>> {
  return request('/teacher/profile', { method: 'POST', data: { subject: subject || null } })
}

export function createInviteCode(): Promise<BaseResponse<InviteCodeOut>> {
  return request('/teacher/invite-code', { method: 'POST' })
}

export function bindTeacher(code: string): Promise<BaseResponse<TeacherStudentOut>> {
  return request('/teacher/bind', { method: 'POST', data: { code } })
}

export function getMyStudents(): Promise<BaseResponse<TeacherStudentOut[]>> {
  return request('/teacher/students', { method: 'GET' })
}

export function getStudentWrongQuestions(studentId: string): Promise<BaseResponse<WrongQuestionOut[]>> {
  return request(`/teacher/students/${studentId}/wrong-questions`, { method: 'GET' })
}

export function addComment(wqId: string, commentText: string): Promise<BaseResponse<TeacherCommentOut>> {
  return request(`/teacher/wrong-questions/${wqId}/comments`, {
    method: 'POST',
    data: { comment_text: commentText },
  })
}

export function getComments(wqId: string): Promise<BaseResponse<TeacherCommentOut[]>> {
  return request(`/teacher/wrong-questions/${wqId}/comments`, { method: 'GET' })
}
