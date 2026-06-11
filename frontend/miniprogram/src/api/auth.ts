import { request } from '@/utils/request'
import type { TokenResponse } from '@/types/api'

export function wxLogin(code: string): Promise<TokenResponse> {
  return request<TokenResponse>('/api/v1/auth/wx-login', {
    method: 'POST',
    data: { code },
  })
}

/** 微信一键获取手机号：getPhoneNumber 按钮回调的 code → 换取并写入手机号 */
export function wxBindPhone(code: string): Promise<{ phone: string }> {
  return request<{ phone: string }>('/api/v1/auth/wx-phone', {
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
