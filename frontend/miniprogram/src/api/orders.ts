import { request } from '@/utils/request'
import type { OrderCreate, OrderOut, PayParamsOut } from '@/types/api'

export function createOrder(data: OrderCreate): Promise<OrderOut> {
  return request<OrderOut>('/api/v1/orders/', {
    method: 'POST',
    data: data as unknown as Record<string, unknown>,
  })
}

export function getOrder(id: string): Promise<OrderOut> {
  return request<OrderOut>(`/api/v1/orders/${id}`)
}

export function payOrder(id: string): Promise<PayParamsOut> {
  return request<PayParamsOut>(`/api/v1/orders/${id}/pay`, { method: 'POST' })
}
