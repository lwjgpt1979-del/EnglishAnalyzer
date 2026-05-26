import { request } from '@/utils/request'
import type { CurrentMembershipOut } from '@/types/api'

export function getMyMembership(): Promise<CurrentMembershipOut> {
  return request<CurrentMembershipOut>('/api/v1/memberships/me')
}
