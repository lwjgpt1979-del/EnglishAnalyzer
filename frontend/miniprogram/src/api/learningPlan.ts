import { request } from '@/utils/request'
import type { TodayPlanOut } from '@/types/api'

/** 获取今日个性化学习计划 */
export function getTodayPlan(): Promise<TodayPlanOut> {
  return request<TodayPlanOut>('/api/v1/learning-plan/today', { method: 'GET' })
}
