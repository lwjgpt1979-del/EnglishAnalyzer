import { request } from '@/utils/request'
import type { RelativeInviteCodeOut, BoundStudent } from '@/types/api'

export function generateRelativeInviteCode(): Promise<RelativeInviteCodeOut> {
  return request<RelativeInviteCodeOut>('/api/v1/relative/invite-code', { method: 'POST' })
}
export function bindRelative(code: string, relationship: string): Promise<any> {
  return request<any>('/api/v1/relative/bind', { method: 'POST', data: { code, relationship } })
}
export function getMyStudentsAsRelative(): Promise<BoundStudent[]> {
  return request<BoundStudent[]>('/api/v1/relative/students', { method: 'GET' })
}
export function getMyRelatives(): Promise<BoundStudent[]> {
  return request<BoundStudent[]>('/api/v1/relative/my-relatives', { method: 'GET' })
}
export function unbindRelative(relativeId: string): Promise<{ unbound: boolean }> {
  return request<{ unbound: boolean }>(`/api/v1/relative/relatives/${relativeId}`, { method: 'DELETE' })
}
export function getStudentDiagnosisAsRelative(studentId: string): Promise<any> {
  return request<any>(`/api/v1/relative/students/${studentId}/diagnosis-report`, { method: 'GET' })
}
