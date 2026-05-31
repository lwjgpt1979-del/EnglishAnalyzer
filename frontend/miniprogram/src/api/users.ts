import { request } from '@/utils/request'
import type { UserProfileOut } from '@/types/api'

export function getMyProfile(): Promise<UserProfileOut> {
  return request<UserProfileOut>('/api/v1/users/me', { method: 'GET' })
}
