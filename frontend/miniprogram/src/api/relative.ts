import { request } from '@/utils/request'
import type { RelativeInviteCodeOut, BoundStudent, RelativeCheckinCalendar } from '@/types/api'

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

export function relativeInviteQrcode() {
  return request('/api/v1/relative/invite-code/qrcode', { method: 'POST' })
}

export function relativeInviteSms(phone: string) {
  return request('/api/v1/relative/invite-code/sms', { method: 'POST', data: { phone } })
}

export function getStudentCheckinCalendar(studentId: string, year?: number, month?: number) {
  const data: Record<string, number> = {}
  if (year) data.year = year
  if (month) data.month = month
  return request<RelativeCheckinCalendar>(
    `/api/v1/relative/students/${studentId}/checkin-calendar`,
    { method: 'GET', data },
  )
}
