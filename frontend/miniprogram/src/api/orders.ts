import { request } from '@/utils/request'
import type { OrderCreate, OrderOut, PayParamsOut } from '@/types/api'

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

export interface TierPricing {
  unit_months: number
  tiers: { key: string; name: string; unit_price_fen: number }[]
}
export function getTierPricing(): Promise<TierPricing> {
  return request<TierPricing>('/api/v1/orders/tier-pricing', { method: 'GET' })
}
