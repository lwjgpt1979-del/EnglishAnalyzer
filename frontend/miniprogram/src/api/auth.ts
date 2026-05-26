import { request } from '@/utils/request'
import type { TokenResponse } from '@/types/api'

export function wxLogin(code: string): Promise<TokenResponse> {
  return request<TokenResponse>('/api/v1/auth/wx-login', {
    method: 'POST',
    data: { code },
  })
}
