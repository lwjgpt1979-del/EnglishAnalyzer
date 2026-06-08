import { request } from '@/utils/request'
import type { TokenResponse } from '@/types/api'

export function wxLogin(code: string): Promise<TokenResponse> {
  return request<TokenResponse>('/api/v1/auth/wx-login', {
    method: 'POST',
    data: { code },
  })
}

export interface UpdateProfileData {
  preferred_textbook_version?: string | null
  preferred_grade?: string | null
  preferred_semester?: string | null
  city_code?: string | null
}

export function updateProfile(data: UpdateProfileData): Promise<{
  preferred_textbook_version: string | null
  preferred_grade: string | null
  preferred_semester: string | null
  city_code: string | null
}> {
  return request('/api/v1/auth/profile', {
    method: 'PATCH',
    data,
  })
}
