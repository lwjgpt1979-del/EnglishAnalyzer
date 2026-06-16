import { request } from '@/utils/request'

export interface MyCoupon {
  grant_id: string; coupon_id: string; name: string; desc: string
  scope: string; status: string; min_amount_fen: number; expired: boolean; valid_until: string | null
}
export interface ApplicableCoupon { grant_id: string; coupon_id: string; name: string; desc: string; discount_fen: number }

export function myCoupons(status = 'unused'): Promise<{ items: MyCoupon[] }> {
  return request(`/api/v1/coupons/mine?status=${status}`, { method: 'GET' })
}
export function redeemCoupon(code: string): Promise<{ desc: string }> {
  return request('/api/v1/coupons/redeem', { method: 'POST', data: { code } })
}
export function applicableCoupons(amount_fen: number, scope = 'all'): Promise<{ items: ApplicableCoupon[] }> {
  return request(`/api/v1/coupons/applicable?amount_fen=${amount_fen}&scope=${scope}`, { method: 'GET' })
}
