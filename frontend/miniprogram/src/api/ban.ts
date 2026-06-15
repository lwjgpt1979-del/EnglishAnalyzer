import { request } from '@/utils/request'

export interface BanStatus {
  banned: boolean
  ban_type: string | null   // permanent | temporary | null
  reason: string | null
  banned_until: string | null
}
export interface MyBanAppeal { id: string; reason: string; status: string; note: string | null; created_at: string | null }

/** 封禁状态（被封用户也可调）*/
export function getBanStatus(): Promise<BanStatus> {
  return request<BanStatus>('/api/v1/users/me/ban-status', { method: 'GET' })
}
/** 提交封禁申诉 */
export function submitBanAppeal(reason: string, evidence_urls?: string[]): Promise<{ id: string; status: string }> {
  return request('/api/v1/users/me/ban-appeal', { method: 'POST', data: { reason, evidence_urls } })
}
/** 我的封禁申诉记录 */
export function getMyBanAppeals(): Promise<MyBanAppeal[]> {
  return request<MyBanAppeal[]>('/api/v1/users/me/ban-appeals', { method: 'GET' })
}
