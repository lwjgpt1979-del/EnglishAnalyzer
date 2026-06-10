import { request } from '@/utils/request'
import type { IncentiveSummary } from '@/types/api'

/** 学习激励中心总览（等级/经验值 + 连续打卡 + 勋章 + 成就） */
export function getIncentiveSummary(): Promise<IncentiveSummary> {
  return request<IncentiveSummary>('/api/v1/incentive/summary', { method: 'GET' })
}
