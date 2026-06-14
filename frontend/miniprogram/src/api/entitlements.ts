import { request } from '@/utils/request'

export interface FeatureEntitlement {
  key: string
  title?: string
  module?: string
  allowed: boolean
  mode: 'allow' | 'deny' | 'quota'
  quota_limit?: number | null
  quota_left?: number | null
  required_tiers?: string[]
  condition?: string | null
  reason?: string
}
export interface MyEntitlements {
  tier: string
  features: Record<string, FeatureEntitlement>
}
export function getMyEntitlements(): Promise<MyEntitlements> {
  return request<MyEntitlements>('/api/v1/me/entitlements', { method: 'GET' })
}
