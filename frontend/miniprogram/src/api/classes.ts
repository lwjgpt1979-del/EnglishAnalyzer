import { request } from '@/utils/request'
import type { BaseResponse, ClassOut, ClassStudentOut, ClassReport } from '@/types/api'

export function listClasses(): Promise<BaseResponse<ClassOut[]>> {
  return request('/api/v1/teacher/classes', { method: 'GET' })
}
export function createClass(name: string): Promise<BaseResponse<ClassOut>> {
  return request('/api/v1/teacher/classes', { method: 'POST', data: { name } })
}
export function deleteClass(classId: string): Promise<BaseResponse<{ deleted: boolean }>> {
  return request(`/api/v1/teacher/classes/${classId}`, { method: 'DELETE' })
}
export function listClassStudents(classId: string): Promise<BaseResponse<ClassStudentOut[]>> {
  return request(`/api/v1/teacher/classes/${classId}/students`, { method: 'GET' })
}
export function addClassStudents(classId: string, studentIds: string[]): Promise<BaseResponse<{ added: number }>> {
  return request(`/api/v1/teacher/classes/${classId}/students`, { method: 'POST', data: { student_ids: studentIds } })
}
export function removeClassStudent(classId: string, studentId: string): Promise<BaseResponse<{ removed: boolean }>> {
  return request(`/api/v1/teacher/classes/${classId}/students/${studentId}`, { method: 'DELETE' })
}
export function getClassReport(classId: string): Promise<BaseResponse<ClassReport>> {
  return request(`/api/v1/teacher/classes/${classId}/report`, { method: 'GET' })
}
