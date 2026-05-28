import { request } from '@/utils/request'
import type { CompleteProfileResponse, CancellationStatus } from '../types/api'

export function completeProfile(data: {
  birth_year: number
  guardian_phone?: string
  user_phone?: string
  agreement_version: string
}): Promise<CompleteProfileResponse> {
  return request<CompleteProfileResponse>('/api/v1/auth/complete-profile', { method: 'POST', data })
}

export function guardianVerify(code: string): Promise<{ profile_completed: boolean }> {
  return request<{ profile_completed: boolean }>('/api/v1/auth/guardian-verify', { method: 'POST', data: { code } })
}

export function requestCancel(): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>('/api/v1/auth/cancel-account/request', { method: 'POST' })
}

export function confirmCancel(code: string): Promise<CancellationStatus> {
  return request<CancellationStatus>('/api/v1/auth/cancel-account/confirm', { method: 'POST', data: { code } })
}

export function revokeCancel(): Promise<{ revoked: boolean }> {
  return request<{ revoked: boolean }>('/api/v1/auth/cancel-account/revoke', { method: 'POST' })
}
