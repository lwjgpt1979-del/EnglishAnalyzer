import { request } from '@/utils/request'
import type { CurrentMembershipOut } from '@/types/api'

export function getMyMembership(): Promise<CurrentMembershipOut> {
  return request<CurrentMembershipOut>('/api/v1/memberships/me')
}

/** 学生输机构激活码兑换会员（D-122） */
export function activateCode(code: string) {
  return request('/api/v1/memberships/activate-code', { method: 'POST', data: { code } })
}
