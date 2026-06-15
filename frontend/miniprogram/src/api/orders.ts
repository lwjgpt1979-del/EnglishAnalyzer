import { request } from '@/utils/request'
import type {
  AppealCreate, OrderCreate, OrderOut, PayParamsOut,
  PaymentConfirmCreate, PaymentConfirmOut, RefundOut,
} from '@/types/api'

export function createOrder(data: OrderCreate): Promise<OrderOut> {
  return request<OrderOut>('/api/v1/orders/', {
    method: 'POST',
    data,
  })
}

export function getOrder(id: string): Promise<OrderOut> {
  return request<OrderOut>(`/api/v1/orders/${id}`)
}

export function payOrder(id: string): Promise<PayParamsOut> {
  return request<PayParamsOut>(`/api/v1/orders/${id}/pay`, { method: 'POST' })
}

/** 我的订单列表（含退款/申诉状态）*/
export function getMyOrders(): Promise<OrderOut[]> {
  return request<OrderOut[]>('/api/v1/orders/', { method: 'GET' })
}

/** 支付前合规确认留存，返回 log_id（§4.6.3）*/
export function paymentConfirm(data: PaymentConfirmCreate): Promise<PaymentConfirmOut> {
  return request<PaymentConfirmOut>('/api/v1/orders/payment-confirm', {
    method: 'POST', data,
  })
}

/** 申请退款（7天内规则引擎自动判定）*/
export function requestRefund(id: string): Promise<RefundOut> {
  return request<RefundOut>(`/api/v1/orders/${id}/refund`, { method: 'POST' })
}

/** 超7天有理由申诉 */
export function submitAppeal(id: string, data: AppealCreate): Promise<RefundOut> {
  return request<RefundOut>(`/api/v1/orders/${id}/appeal`, { method: 'POST', data })
}

export interface TierPricing {
  unit_months: number
  tiers: { key: string; name: string; unit_price_fen: number }[]
}
export function getTierPricing(): Promise<TierPricing> {
  return request<TierPricing>('/api/v1/orders/tier-pricing', { method: 'GET' })
}

export interface SemesterPricing { basic: number; pro: number; promax: number }
/** 学期会员定价（元/学期），运营后台可改 */
export function getSemesterPricing(): Promise<SemesterPricing> {
  return request<SemesterPricing>('/api/v1/orders/semester-pricing', { method: 'GET' })
}
